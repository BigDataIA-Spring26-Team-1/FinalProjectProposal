from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from .config import Settings
from .models import ChatRequest, ChatResponse, DashboardPayload, SourceSnapshot
from .rag import RagService
from .sources import DashboardAggregator

PROJECT_FACTS = [
    "The project is called Industrial Digital Twin: Big Data-Driven Factory Simulation & LLM-Powered Predictive Analytics.",
    "The frontend has four views: Factory Floor, Simulation, Scenarios, and AI Advisor.",
    "The backend is a Poetry-managed FastAPI service that aggregates live public and API-backed sources.",
    "The UI still uses local simulation logic for line editing and KPI calculations, while the backend supplies live source intelligence and advisor context.",
    "Configured live source adapters include SEC EDGAR, OSHA, ITAC/DOE, EPA TRI, NASA POWER, FRED, EIA, SerpAPI, Glassdoor, Stack Exchange, Reddit, and equipment catalog pages.",
]

BACKEND_FACTS = [
    "Backend endpoints: GET /api/health, GET /api/dashboard, GET /api/sources, and POST /api/chat.",
    "The frontend fetches the dashboard payload from /api/dashboard and uses it to populate stack status, live feed, source cards, and proposal highlights.",
    "The AI Advisor is a free-form chatbot and does not rely on hardcoded question categories or canned answers.",
    "RAG retrieval can index the proposal PDF, the local codebase, and live source snapshots with Voyage embeddings stored in Pinecone.",
    "Anthropic is the primary chat provider, with OpenAI and Gemini available as fallback model providers when configured.",
]

MARKET_RESEARCH_KEYWORDS = {
    "invest",
    "investment",
    "stock",
    "stocks",
    "buy",
    "company",
    "companies",
    "market",
    "markets",
    "semiconductor",
    "chip",
    "chips",
    "earnings",
    "valuation",
}

RESEARCH_COMPANY_HINTS = {
    "nvidia": ("NVDA", "NVIDIA"),
    "nvda": ("NVDA", "NVIDIA"),
    "amd": ("AMD", "AMD"),
    "broadcom": ("AVGO", "Broadcom"),
    "avgo": ("AVGO", "Broadcom"),
    "micron": ("MU", "Micron"),
    "mu": ("MU", "Micron"),
    "tsmc": ("TSM", "TSMC"),
    "taiwan semiconductor": ("TSM", "TSMC"),
    "qualcomm": ("QCOM", "Qualcomm"),
    "qcom": ("QCOM", "Qualcomm"),
    "asml": ("ASML", "ASML"),
    "applied materials": ("AMAT", "Applied Materials"),
    "amat": ("AMAT", "Applied Materials"),
    "lam research": ("LRCX", "Lam Research"),
    "lrcx": ("LRCX", "Lam Research"),
    "kla": ("KLAC", "KLA"),
    "klac": ("KLAC", "KLA"),
    "intel": ("INTC", "Intel"),
    "intc": ("INTC", "Intel"),
}


def _stringify_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


class ProjectChatbot:
    def __init__(
        self,
        settings: Settings,
        aggregator: DashboardAggregator,
        rag_service: RagService | None = None,
    ) -> None:
        self.settings = settings
        self.aggregator = aggregator
        self.rag_service = rag_service
        self._anthropic_client = httpx.AsyncClient(timeout=60.0)
        self._response_cache: dict[str, tuple[datetime, ChatResponse]] = {}
        self._dashboard_warmup_task: asyncio.Task[Any] | None = None

    async def answer(self, request: ChatRequest) -> ChatResponse:
        dashboard = self.aggregator.get_cached_dashboard()
        if dashboard is None:
            dashboard = self.aggregator.build_placeholder_dashboard()
            self._ensure_dashboard_warmup()
        cache_key = self._build_cache_key(request, dashboard)
        cached_response = self._get_cached_response(cache_key)
        if cached_response is not None:
            return cached_response

        retrieved_context: list[dict[str, Any]] = []
        rag_detail = "RAG is disabled."
        if self.rag_service is not None:
            try:
                retrieved_context, rag_status = await self.rag_service.retrieve(
                    request.question,
                    dashboard,
                    allow_index_build=self.settings.rag_build_on_chat,
                )
                rag_detail = rag_status.detail
            except Exception as exc:
                rag_detail = f"RAG retrieval is temporarily unavailable: {exc}"

        question_research = await self._collect_question_scoped_research(request.question)

        if not any(
            [
                self.settings.anthropic_api_key,
                self.settings.openai_api_key,
                self.settings.gemini_api_key,
            ]
        ):
            response = ChatResponse(
                answer=(
                    "No chat model provider is configured in .env, so live chat is unavailable. "
                    "Add ANTHROPIC_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY and restart the backend."
                ),
                model="fallback",
                citations=self._build_citations(
                    request,
                    dashboard,
                    retrieved_context,
                    question_research,
                ),
                used_live_data=True,
            )
            self._store_cached_response(cache_key, response)
            return response

        prompt = self._build_prompt(
            request,
            dashboard,
            retrieved_context,
            rag_detail,
            question_research,
        )
        try:
            answer, model_name = await self._generate_answer(prompt)
        except Exception as exc:
            answer = (
                "The AI advisor is temporarily unavailable across the configured model providers. "
                f"Last error: {exc}"
            )
            model_name = "fallback"
        chat_response = ChatResponse(
            answer=answer,
            model=model_name,
            citations=self._build_citations(
                request,
                dashboard,
                retrieved_context,
                question_research,
            ),
            used_live_data=True,
        )
        self._store_cached_response(cache_key, chat_response)
        return chat_response

    async def _generate_answer(self, prompt: str) -> tuple[str, str]:
        errors: list[str] = []
        providers = [
            ("anthropic", self.settings.anthropic_api_key, self._call_anthropic),
            ("openai", self.settings.openai_api_key, self._call_openai),
            ("gemini", self.settings.gemini_api_key, self._call_gemini),
        ]

        for provider_name, api_key, handler in providers:
            if not api_key:
                continue
            try:
                return await handler(prompt)
            except Exception as exc:
                errors.append(f"{provider_name}: {exc}")

        raise RuntimeError("All configured chat providers failed. " + " | ".join(errors))

    def _system_prompt(self) -> str:
        return (
            "You are the embedded AI advisor for the Industrial Digital Twin platform. "
            "Your primary role is to answer questions about the platform, its architecture, codebase, UI, "
            "setup, live data sources, and factory operations. You may also answer broader questions about "
            "manufacturing, industrial systems, public companies, and market context when they can be supported "
            "by the provided live sources, retrieved context, or your general domain knowledge. "
            "When CLIENT UI FACTORY STATE is present, treat it as the authoritative current factory configuration. "
            "For questions about station counts, worker counts, machine counts, staffing, bottlenecks, or line composition, "
            "prefer the client UI state over RAG, code snippets, proposal text, or demo data. "
            "If those sources conflict, explicitly say the static or retrieved context may reflect a template or stale example, "
            "and use the client UI numbers. "
            "Be concrete. If a source is offline, stale, or credentials are missing, say so plainly. "
            "Keep answers concise by default unless the user asks for depth. "
            "Do not invent capabilities or claim live evidence that is not in the provided context. "
            "Use the retrieved RAG context when it is available, and cite the evidence naturally in prose. "
            "When question-scoped live research is available, use it instead of overemphasizing generic dashboard limitations. "
            "If the user asks for investing or other high-stakes financial guidance, do not refuse outright. "
            "Instead, provide non-personalized informational analysis, note important uncertainty, and state "
            "clearly when current price, news, or analyst-consensus data is not available in the live sources."
        )

    async def _call_anthropic(self, prompt: str) -> tuple[str, str]:
        response = await self._anthropic_client.post(
            self.settings.anthropic_api_url,
            headers={
                "x-api-key": self.settings.anthropic_api_key or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.settings.anthropic_model,
                "max_tokens": self.settings.anthropic_max_tokens,
                "system": self._system_prompt(),
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response.raise_for_status()
        body = response.json()
        return self._extract_anthropic_answer(body), body.get("model", self.settings.anthropic_model)

    async def _call_openai(self, prompt: str) -> tuple[str, str]:
        response = await self._anthropic_client.post(
            self.settings.openai_api_url,
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key or ''}",
                "content-type": "application/json",
            },
            json={
                "model": self.settings.normalized_openai_model,
                "messages": [
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": self.settings.anthropic_max_tokens,
            },
        )
        response.raise_for_status()
        body = response.json()
        return self._extract_openai_answer(body), body.get("model", self.settings.normalized_openai_model)

    async def _call_gemini(self, prompt: str) -> tuple[str, str]:
        response = await self._anthropic_client.post(
            f"{self.settings.gemini_api_url}/{self.settings.normalized_gemini_model}:generateContent",
            params={"key": self.settings.gemini_api_key or ""},
            headers={"content-type": "application/json"},
            json={
                "systemInstruction": {
                    "parts": [{"text": self._system_prompt()}],
                },
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}],
                    }
                ],
                "generationConfig": {
                    "maxOutputTokens": self.settings.anthropic_max_tokens,
                },
            },
        )
        response.raise_for_status()
        body = response.json()
        return self._extract_gemini_answer(body), self.settings.normalized_gemini_model

    def _build_selected_line_fact_block(self, selected_line: dict[str, Any]) -> str:
        if not selected_line:
            return "CURRENT FOCUSED LINE FACTS:\nNo focused line details were provided from the client UI."

        facts: list[str] = []
        if selected_line.get("name"):
            facts.append(f"Focused line: {selected_line['name']}")
        if selected_line.get("stations") is not None:
            facts.append(f"Stations: {selected_line['stations']}")
        if selected_line.get("workers") is not None:
            facts.append(f"Workers: {selected_line['workers']}")
        if selected_line.get("machines") is not None:
            facts.append(f"Machines: {selected_line['machines']}")
        if selected_line.get("output") is not None:
            facts.append(f"Simulated output: {selected_line['output']}")
        if selected_line.get("defects") is not None:
            facts.append(f"Simulated defects: {selected_line['defects']}")
        if selected_line.get("downtime") is not None:
            facts.append(f"Simulated downtime: {selected_line['downtime']}")

        station_summaries: list[str] = []
        for station in selected_line.get("station_details") or []:
            label = station.get("label") or station.get("type") or "Station"
            machines = station.get("machines")
            workers = station.get("workers")
            ratio = station.get("worker_to_machine_ratio")
            summary = f"{label} ({machines} machines, {workers} workers)"
            if ratio is not None:
                summary += f", {ratio} workers per machine"
            station_summaries.append(summary)
        if station_summaries:
            facts.append("Station breakdown: " + "; ".join(station_summaries))

        if not facts:
            return "CURRENT FOCUSED LINE FACTS:\nFocused line context was provided, but it did not include numeric layout details."
        return "CURRENT FOCUSED LINE FACTS:\n- " + "\n- ".join(facts)

    def _build_prompt(
        self,
        request: ChatRequest,
        dashboard: DashboardPayload,
        retrieved_context: list[dict[str, Any]],
        rag_detail: str,
        question_research: list[SourceSnapshot],
    ) -> str:
        trimmed_history = request.history[-self.settings.chat_history_turn_limit :]
        history_text = "\n".join(
            f"{message.role.upper()}: {message.content}" for message in trimmed_history
        )
        snapshots_for_prompt = sorted(
            [*question_research, *dashboard.sourceSnapshots],
            key=lambda snapshot: (
                snapshot.state == "offline",
                snapshot.state == "partial",
                snapshot.key not in {"sec", "fred", "eia", "nasa", "serpapi", "glassdoor", "sec_research", "serpapi_research", "glassdoor_research"},
            ),
        )
        source_summaries = [
            {
                "name": snapshot.name,
                "state": snapshot.state,
                "summary": snapshot.summary,
                "warning": snapshot.warning,
                "sample_record": snapshot.records[0] if snapshot.records else None,
            }
            for snapshot in snapshots_for_prompt[: self.settings.chat_source_summary_limit]
        ]
        selected_line = request.selected_line or {}
        factory_state = request.factory_state or {}
        retrieval_block = (
            "RAG RETRIEVAL:\n"
            + _stringify_json(
                {
                    "detail": rag_detail,
                    "usage_rule": (
                        "RAG can include bundled code, proposal text, and demo examples. "
                        "Use it for architecture, implementation details, and background context, "
                        "but do not let it override the live client UI factory state for current "
                        "line layout, station counts, worker counts, or staffing recommendations."
                    ),
                    "matches": [
                        {
                            "citation": match.get("citation"),
                            "source_type": match.get("source_type"),
                            "text": match.get("text"),
                        }
                        for match in retrieved_context[: self.settings.chat_rag_match_limit]
                    ],
                }
            )
        )
        question_research_block = _stringify_json(
            [
                {
                    "name": snapshot.name,
                    "state": snapshot.state,
                    "summary": snapshot.summary,
                    "sample_record": snapshot.records[0] if snapshot.records else None,
                }
                for snapshot in question_research
            ]
        )

        return "\n\n".join(
            [
                "PROJECT FACTS:\n- " + "\n- ".join(PROJECT_FACTS),
                "BACKEND FACTS:\n- " + "\n- ".join(BACKEND_FACTS),
                self._build_selected_line_fact_block(selected_line),
                (
                    "AUTHORITATIVE LIVE CLIENT FACTORY STATE:\n"
                    + _stringify_json(
                        {
                            "authority": "Use this as the source of truth for the current factory layout and staffing.",
                            "precedence_rule": (
                                "If this conflicts with RAG, proposal text, or code snippets, use the client UI values."
                            ),
                            "active_view": request.active_view,
                            "selected_line": selected_line,
                            "factory_state": factory_state,
                        }
                    )
                ),
                "PROPOSAL HIGHLIGHTS:\n- " + "\n- ".join(dashboard.proposalHighlights),
                "DATASET PROFILE:\n"
                + _stringify_json(
                    {
                        "total_estimated_size": dashboard.datasetProfile.total_estimated_size,
                        "source_count": dashboard.datasetProfile.source_count,
                        "join_keys": dashboard.datasetProfile.join_keys,
                        "engineering_note": dashboard.datasetProfile.engineering_note,
                        "sources": [source.model_dump() for source in dashboard.datasetProfile.sources],
                    }
                ),
                "QUESTION-SCOPED LIVE RESEARCH:\n" + question_research_block,
                "LIVE SOURCE SNAPSHOTS:\n" + _stringify_json(source_summaries),
                retrieval_block,
                "RECENT CONVERSATION:\n" + (history_text if history_text else "No previous chat history."),
                "USER QUESTION:\n" + request.question,
            ]
        )

    def _build_cache_key(self, request: ChatRequest, dashboard: DashboardPayload) -> str:
        selected_line = request.selected_line or {}
        factory_state = request.factory_state or {}
        trimmed_history = request.history[-self.settings.chat_history_turn_limit :]
        history_text = "|".join(
            f"{message.role}:{message.content.strip()}" for message in trimmed_history
        )
        return json.dumps(
            {
                "question": request.question.strip().lower(),
                "active_view": request.active_view or "",
                "selected_line": selected_line,
                "factory_state": factory_state,
                "history": history_text,
                "dashboard_fetched_at": (
                    dashboard.fetched_at if dashboard.sourceSnapshots else "placeholder"
                ),
            },
            sort_keys=True,
            ensure_ascii=True,
        )

    def _get_cached_response(self, cache_key: str) -> ChatResponse | None:
        cached = self._response_cache.get(cache_key)
        if cached is None:
            return None

        expires_at, response = cached
        if datetime.now(UTC) >= expires_at:
            self._response_cache.pop(cache_key, None)
            return None
        return response

    def _store_cached_response(self, cache_key: str, response: ChatResponse) -> None:
        expires_at = datetime.now(UTC) + timedelta(
            seconds=self.settings.chat_answer_cache_ttl_seconds,
        )
        self._response_cache[cache_key] = (expires_at, response)
        if len(self._response_cache) > 64:
            oldest_key = min(
                self._response_cache,
                key=lambda key: self._response_cache[key][0],
            )
            self._response_cache.pop(oldest_key, None)

    def _ensure_dashboard_warmup(self) -> None:
        if self._dashboard_warmup_task is not None and not self._dashboard_warmup_task.done():
            return
        self._dashboard_warmup_task = asyncio.create_task(
            self.aggregator.build_dashboard(force_refresh=False),
        )

    def _extract_anthropic_answer(self, body: dict[str, Any]) -> str:
        content = body.get("content", [])
        text_parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        answer = "\n\n".join(part.strip() for part in text_parts if part.strip()).strip()
        return answer or "I could not produce a response from the current project context."

    def _extract_openai_answer(self, body: dict[str, Any]) -> str:
        choices = body.get("choices", [])
        if not choices:
            return "I could not produce a response from the current project context."
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            text_parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") in {"text", "output_text"}
            ]
            answer = "\n\n".join(part.strip() for part in text_parts if part.strip()).strip()
            return answer or "I could not produce a response from the current project context."
        if isinstance(content, str):
            return content.strip() or "I could not produce a response from the current project context."
        return "I could not produce a response from the current project context."

    def _extract_gemini_answer(self, body: dict[str, Any]) -> str:
        candidates = body.get("candidates", [])
        if not candidates:
            return "I could not produce a response from the current project context."
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [
            part.get("text", "")
            for part in parts
            if isinstance(part, dict) and part.get("text")
        ]
        answer = "\n\n".join(part.strip() for part in text_parts if part.strip()).strip()
        return answer or "I could not produce a response from the current project context."

    def _build_citations(
        self,
        request: ChatRequest,
        dashboard: DashboardPayload,
        retrieved_context: list[dict[str, Any]],
        question_research: list[SourceSnapshot] | None = None,
    ) -> list[str]:
        question_research = question_research or []
        citations = []
        for match in retrieved_context:
            citation = match.get("citation")
            if citation and citation not in citations:
                citations.append(str(citation))

        for snapshot in question_research:
            if snapshot.name not in citations and snapshot.state != "offline":
                citations.append(snapshot.name)

        if (request.factory_state or request.selected_line) and "Live client UI factory state" not in citations:
            citations.append("Live client UI factory state")

        if not citations:
            citations.extend(
                snapshot.name for snapshot in dashboard.sourceSnapshots if snapshot.state != "offline"
            )
        if "Live dashboard source snapshots" not in citations:
            citations.append("Live dashboard source snapshots")
        return citations[:8]

    async def _collect_question_scoped_research(self, question: str) -> list[SourceSnapshot]:
        if not self._should_run_market_research(question):
            return []

        query = self._build_market_query(question)
        sec_tickers = self._extract_research_tickers(question)
        glassdoor_query = self._build_glassdoor_query(question)

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            tasks: list[asyncio.Task[SourceSnapshot | None]] = []

            if self.settings.serpapi_key:
                tasks.append(
                    asyncio.create_task(
                        self._safe_snapshot(
                            self.aggregator.fetch_serpapi(
                                client,
                                query=query,
                                snapshot_key="serpapi_research",
                                snapshot_name="SerpAPI Research",
                            ),
                        ),
                    ),
                )

            if sec_tickers:
                tasks.append(
                    asyncio.create_task(
                        self._safe_snapshot(
                            self.aggregator.fetch_sec(
                                client,
                                tickers=sec_tickers,
                                snapshot_key="sec_research",
                                snapshot_name="SEC EDGAR Research",
                            ),
                        ),
                    ),
                )

            if self.settings.rapidapi_key:
                tasks.append(
                    asyncio.create_task(
                        self._safe_snapshot(
                            self.aggregator.fetch_glassdoor(
                                client,
                                query=glassdoor_query,
                                snapshot_key="glassdoor_research",
                                snapshot_name="Glassdoor Research",
                            ),
                        ),
                    ),
                )

            if not tasks:
                return []

            snapshots = [result for result in await asyncio.gather(*tasks) if result is not None]
            return snapshots

    async def _safe_snapshot(self, coro: Any) -> SourceSnapshot | None:
        try:
            return await coro
        except Exception:
            return None

    def _should_run_market_research(self, question: str) -> bool:
        lowered = question.lower()
        return any(keyword in lowered for keyword in MARKET_RESEARCH_KEYWORDS)

    def _extract_research_tickers(self, question: str) -> list[str]:
        lowered = question.lower()
        tickers: list[str] = []

        for pattern, (ticker, _) in RESEARCH_COMPANY_HINTS.items():
            if pattern in lowered and ticker not in tickers:
                tickers.append(ticker)

        if not tickers and any(token in lowered for token in ("semiconductor", "chip", "chips")):
            tickers.extend(self.settings.market_research_ticker_list[: self.settings.chat_market_research_limit])

        return tickers[: self.settings.chat_market_research_limit]

    def _extract_company_labels(self, question: str) -> list[str]:
        lowered = question.lower()
        labels: list[str] = []
        for pattern, (_, label) in RESEARCH_COMPANY_HINTS.items():
            if pattern in lowered and label not in labels:
                labels.append(label)
        return labels

    def _build_market_query(self, question: str) -> str:
        compact_question = re.sub(r"\s+", " ", question).strip()
        company_labels = self._extract_company_labels(question)
        if company_labels:
            joined = ", ".join(company_labels[:3])
            return f"{compact_question} {joined} earnings guidance demand outlook semiconductor news"
        if any(token in question.lower() for token in ("semiconductor", "chip", "chips")):
            return f"{compact_question} semiconductor earnings guidance demand outlook industry news"
        return compact_question

    def _build_glassdoor_query(self, question: str) -> str:
        company_labels = self._extract_company_labels(question)
        if company_labels:
            return company_labels[0]
        if any(token in question.lower() for token in ("semiconductor", "chip", "chips")):
            return "semiconductor"
        return self.settings.glassdoor_query
