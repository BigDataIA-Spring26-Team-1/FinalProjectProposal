from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pypdf import PdfReader

from .config import Settings
from .models import DashboardPayload, RagStatusResponse

CODE_FILE_SUFFIXES = {".py", ".js", ".jsx", ".css", ".md", ".toml", ".html", ".json"}
CODE_FILE_EXCLUDES = {
    "poetry.lock",
    "package-lock.json",
}
CODE_DIRECTORY_EXCLUDES = {
    ".git",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clean_text(text: str) -> str:
    cleaned = text.replace("\x00", " ")
    cleaned = re.sub(r"\r\n?", "\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []

    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    step = max(chunk_size - overlap, 1)
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        start += step
    return chunks


def _normalize_host(host: str) -> str:
    return host.removeprefix("https://").removesuffix("/")


@dataclass(slots=True)
class RagChunk:
    id: str
    text: str
    citation: str
    source_type: str
    metadata: dict[str, str | int]


class RagService:
    def __init__(self, settings: Settings, repo_root: Path | None = None) -> None:
        self.settings = settings
        self.repo_root = repo_root or Path(__file__).resolve().parent.parent
        self.cache_dir = self.repo_root / ".rag_cache"
        self.cache_dir.mkdir(exist_ok=True)
        self.manifest_path = self.cache_dir / "manifest.json"
        self._status_cache: RagStatusResponse | None = None

    async def get_status(
        self,
        dashboard: DashboardPayload,
        force_refresh: bool = False,
    ) -> RagStatusResponse:
        if not force_refresh and self._status_cache is not None:
            return self._status_cache

        chunks, warnings, proposal_path = await asyncio.to_thread(self._build_corpus, dashboard)
        manifest = self._load_manifest()
        fingerprint = self._fingerprint(chunks)
        ready = bool(
            manifest
            and manifest.get("fingerprint") == fingerprint
            and manifest.get("namespace")
            and manifest.get("document_count") == len(chunks)
        )

        detail = "RAG index is ready."
        if not self.settings.voyage_api_key or not self.settings.pinecone_api_key:
            detail = "Set VOYAGE_API_KEY and PINECONE_API_KEY in .env to enable vector retrieval."
        elif not proposal_path:
            detail = "Proposal PDF not found. RAG will still use codebase and live-source content."
        elif not ready:
            detail = "RAG corpus is available, but the Pinecone index needs a fresh sync."

        status = RagStatusResponse(
            configured=bool(self.settings.voyage_api_key and self.settings.pinecone_api_key),
            ready=ready,
            detail=detail,
            index_name=self.settings.pinecone_index_name,
            namespace=manifest.get("namespace") if manifest else None,
            document_count=len(chunks),
            source_breakdown=self._source_breakdown(chunks),
            proposal_path=str(proposal_path) if proposal_path else None,
            indexed_at=manifest.get("indexed_at") if manifest else None,
            warnings=warnings,
        )
        self._status_cache = status
        return status

    async def ensure_index(
        self,
        dashboard: DashboardPayload,
        force_reindex: bool = False,
    ) -> RagStatusResponse:
        if (
            not force_reindex
            and self._status_cache is not None
            and self._status_cache.ready
            and self._status_cache.indexed_at
            and dashboard.fetched_at <= self._status_cache.indexed_at
        ):
            return self._status_cache

        chunks, warnings, proposal_path = await asyncio.to_thread(self._build_corpus, dashboard)
        if not self.settings.voyage_api_key or not self.settings.pinecone_api_key:
            status = RagStatusResponse(
                configured=False,
                ready=False,
                detail="Set VOYAGE_API_KEY and PINECONE_API_KEY in .env to enable vector retrieval.",
                index_name=self.settings.pinecone_index_name,
                document_count=len(chunks),
                source_breakdown=self._source_breakdown(chunks),
                proposal_path=str(proposal_path) if proposal_path else None,
                warnings=warnings,
            )
            self._status_cache = status
            return status

        fingerprint = self._fingerprint(chunks)
        namespace = self._namespace_for_fingerprint(fingerprint)
        manifest = self._load_manifest()
        if (
            not force_reindex
            and manifest
            and manifest.get("fingerprint") == fingerprint
            and manifest.get("namespace") == namespace
            and manifest.get("document_count") == len(chunks)
        ):
            status = RagStatusResponse(
                configured=True,
                ready=True,
                detail="RAG index is ready.",
                index_name=self.settings.pinecone_index_name,
                namespace=namespace,
                document_count=len(chunks),
                source_breakdown=self._source_breakdown(chunks),
                proposal_path=str(proposal_path) if proposal_path else None,
                indexed_at=manifest.get("indexed_at"),
                warnings=warnings,
            )
            self._status_cache = status
            return status

        if not chunks:
            status = RagStatusResponse(
                configured=True,
                ready=False,
                detail="No retrievable content was found to index.",
                index_name=self.settings.pinecone_index_name,
                namespace=namespace,
                document_count=0,
                source_breakdown={},
                proposal_path=str(proposal_path) if proposal_path else None,
                warnings=warnings,
            )
            self._status_cache = status
            return status

        async with httpx.AsyncClient(timeout=90.0) as client:
            host = await self._ensure_pinecone_index(client)
            embeddings = await self._embed_documents(client, chunks)
            await self._upsert_vectors(client, host, namespace, chunks, embeddings)

        manifest_payload = {
            "fingerprint": fingerprint,
            "namespace": namespace,
            "index_name": self.settings.pinecone_index_name,
            "host": host,
            "document_count": len(chunks),
            "source_breakdown": self._source_breakdown(chunks),
            "proposal_path": str(proposal_path) if proposal_path else None,
            "indexed_at": _now_iso(),
            "warnings": warnings,
        }
        self.manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

        status = RagStatusResponse(
            configured=True,
            ready=True,
            detail="RAG index is ready.",
            index_name=self.settings.pinecone_index_name,
            namespace=namespace,
            document_count=len(chunks),
            source_breakdown=self._source_breakdown(chunks),
            proposal_path=str(proposal_path) if proposal_path else None,
            indexed_at=manifest_payload["indexed_at"],
            warnings=warnings,
        )
        self._status_cache = status
        return status

    async def retrieve(
        self,
        question: str,
        dashboard: DashboardPayload,
        allow_index_build: bool = False,
    ) -> tuple[list[dict[str, Any]], RagStatusResponse]:
        if allow_index_build:
            status = await self.ensure_index(dashboard)
        else:
            manifest = self._load_manifest()
            if manifest and manifest.get("namespace") and manifest.get("host"):
                status = RagStatusResponse(
                    configured=bool(self.settings.voyage_api_key and self.settings.pinecone_api_key),
                    ready=True,
                    detail="RAG index is ready.",
                    index_name=manifest.get("index_name", self.settings.pinecone_index_name),
                    namespace=manifest.get("namespace"),
                    document_count=int(manifest.get("document_count", 0)),
                    source_breakdown=dict(manifest.get("source_breakdown", {})),
                    proposal_path=manifest.get("proposal_path"),
                    indexed_at=manifest.get("indexed_at"),
                    warnings=list(manifest.get("warnings", [])),
                )
                self._status_cache = status
            else:
                status = await self.get_status(dashboard)
        if not status.ready:
            return [], status

        manifest = self._load_manifest()
        host = manifest.get("host") if manifest else None
        namespace = manifest.get("namespace") if manifest else None
        if not host or not namespace:
            return [], RagStatusResponse(
                configured=True,
                ready=False,
                detail="Pinecone host information is missing. Reindex the corpus.",
                index_name=self.settings.pinecone_index_name,
                namespace=namespace,
                document_count=status.document_count,
                source_breakdown=status.source_breakdown,
                proposal_path=status.proposal_path,
                indexed_at=status.indexed_at,
                warnings=status.warnings,
            )

        async with httpx.AsyncClient(timeout=60.0) as client:
            query_vector = await self._embed_query(client, question)
            response = await client.post(
                f"https://{_normalize_host(host)}/query",
                headers=self._pinecone_headers(),
                json={
                    "namespace": namespace,
                    "vector": query_vector,
                    "topK": self.settings.rag_top_k,
                    "includeMetadata": True,
                    "includeValues": False,
                },
            )
            response.raise_for_status()
            matches = response.json().get("matches", [])

        retrieved = []
        for match in matches:
            metadata = match.get("metadata", {})
            if not metadata:
                continue
            retrieved.append(
                {
                    "citation": metadata.get("citation", "RAG document"),
                    "source_type": metadata.get("source_type", "unknown"),
                    "path": metadata.get("path"),
                    "location": metadata.get("location"),
                    "score": round(match.get("score", 0.0), 4),
                    "text": str(metadata.get("text", ""))[: self.settings.rag_max_snippet_chars],
                }
            )

        return retrieved, status

    def _build_corpus(
        self,
        dashboard: DashboardPayload,
    ) -> tuple[list[RagChunk], list[str], Path | None]:
        warnings: list[str] = []
        chunks: list[RagChunk] = []

        proposal_path = self._discover_proposal_pdf_path()
        if proposal_path is not None:
            proposal_chunks = self._build_proposal_chunks(proposal_path)
            chunks.extend(proposal_chunks)
            if not proposal_chunks:
                warnings.append("Proposal PDF was found but yielded no extractable text.")
        else:
            warnings.append("Proposal PDF could not be found automatically.")

        code_chunks = self._build_codebase_chunks()
        if code_chunks:
            chunks.extend(code_chunks)
        else:
            warnings.append("No codebase files were selected for indexing.")

        live_chunks = self._build_live_source_chunks(dashboard)
        if live_chunks:
            chunks.extend(live_chunks)
        else:
            warnings.append("Live source snapshots yielded no retrievable documents.")

        return chunks, warnings, proposal_path

    def _discover_proposal_pdf_path(self) -> Path | None:
        configured_path = (self.settings.proposal_pdf_path or "").strip()
        if configured_path:
            candidate = Path(configured_path).expanduser()
            if candidate.exists():
                return candidate

        search_roots = [self.repo_root, Path.home() / "Downloads"]
        patterns = (
            "*Digital_Twin_Proposal*.pdf",
            "*Digital Twin Proposal*.pdf",
            "*Twin*Proposal*.pdf",
        )
        for root in search_roots:
            if not root.exists():
                continue
            for pattern in patterns:
                for candidate in sorted(root.glob(pattern)):
                    if candidate.is_file():
                        return candidate
        return None

    def _build_proposal_chunks(self, proposal_path: Path) -> list[RagChunk]:
        reader = PdfReader(str(proposal_path))
        chunks: list[RagChunk] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = _clean_text(page.extract_text() or "")
            if not text:
                continue
            for chunk_index, chunk_text in enumerate(
                _chunk_text(
                    text,
                    chunk_size=self.settings.rag_chunk_chars,
                    overlap=self.settings.rag_chunk_overlap_chars,
                ),
                start=1,
            ):
                citation = (
                    f"Proposal PDF page {page_number}"
                    if chunk_index == 1
                    else f"Proposal PDF page {page_number} chunk {chunk_index}"
                )
                chunks.append(
                    self._make_chunk(
                        text=chunk_text,
                        citation=citation,
                        source_type="proposal",
                        metadata={
                            "path": str(proposal_path),
                            "location": f"page {page_number}",
                            "title": proposal_path.name,
                        },
                    )
                )
        return chunks

    def _build_codebase_chunks(self) -> list[RagChunk]:
        chunks: list[RagChunk] = []
        for path in sorted(self.repo_root.rglob("*")):
            if not path.is_file():
                continue
            if any(part in CODE_DIRECTORY_EXCLUDES for part in path.parts):
                continue
            if path.name in CODE_FILE_EXCLUDES or path.suffix.lower() not in CODE_FILE_SUFFIXES:
                continue
            if path.relative_to(self.repo_root).parts[:1] == (".rag_cache",):
                continue

            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = path.read_text(encoding="utf-8", errors="ignore")
            text = text.strip()
            if not text:
                continue

            relative_path = str(path.relative_to(self.repo_root)).replace("\\", "/")
            lines = text.splitlines()
            start = 0
            chunk_size = self.settings.rag_code_lines_per_chunk
            overlap = self.settings.rag_code_overlap_lines
            step = max(chunk_size - overlap, 1)
            while start < len(lines):
                end = min(start + chunk_size, len(lines))
                chunk_text = "\n".join(lines[start:end]).strip()
                if chunk_text:
                    citation = f"{relative_path} lines {start + 1}-{end}"
                    chunks.append(
                        self._make_chunk(
                            text=chunk_text,
                            citation=citation,
                            source_type="code",
                            metadata={
                                "path": relative_path,
                                "location": f"lines {start + 1}-{end}",
                                "title": path.name,
                            },
                        )
                    )
                if end >= len(lines):
                    break
                start += step
        return chunks

    def _build_live_source_chunks(self, dashboard: DashboardPayload) -> list[RagChunk]:
        chunks: list[RagChunk] = []
        for snapshot in dashboard.sourceSnapshots:
            summary_lines = [
                f"Source: {snapshot.name}",
                f"State: {snapshot.state}",
                f"Summary: {snapshot.summary}",
            ]
            if snapshot.warning:
                summary_lines.append(f"Warning: {snapshot.warning}")

            chunks.append(
                self._make_chunk(
                    text="\n".join(summary_lines),
                    citation=f"Live source {snapshot.name}",
                    source_type="live_source",
                    metadata={
                        "path": snapshot.key,
                        "location": "summary",
                        "title": snapshot.name,
                    },
                )
            )

            if snapshot.records:
                serialized_records = [
                    json.dumps(record, ensure_ascii=True, sort_keys=True)
                    for record in snapshot.records
                ]
                joined_records = "\n".join(serialized_records)
                for chunk_index, chunk_text in enumerate(
                    _chunk_text(
                        joined_records,
                        chunk_size=self.settings.rag_chunk_chars,
                        overlap=self.settings.rag_chunk_overlap_chars,
                    ),
                    start=1,
                ):
                    chunks.append(
                        self._make_chunk(
                            text=chunk_text,
                            citation=f"{snapshot.name} records chunk {chunk_index}",
                            source_type="live_source",
                            metadata={
                                "path": snapshot.key,
                                "location": f"records {chunk_index}",
                                "title": snapshot.name,
                            },
                        )
                    )
        return chunks

    def _make_chunk(
        self,
        *,
        text: str,
        citation: str,
        source_type: str,
        metadata: dict[str, str | int],
    ) -> RagChunk:
        cleaned_text = _clean_text(text)
        digest = hashlib.sha256(f"{source_type}:{citation}:{cleaned_text}".encode("utf-8")).hexdigest()
        return RagChunk(
            id=digest[:32],
            text=cleaned_text,
            citation=citation,
            source_type=source_type,
            metadata=metadata,
        )

    def _fingerprint(self, chunks: list[RagChunk]) -> str:
        digest = hashlib.sha256()
        for chunk in chunks:
            digest.update(chunk.id.encode("utf-8"))
            digest.update(chunk.citation.encode("utf-8"))
        return digest.hexdigest()

    def _namespace_for_fingerprint(self, fingerprint: str) -> str:
        prefix = re.sub(r"[^a-z0-9-]", "-", self.settings.rag_namespace_prefix.lower()).strip("-")
        prefix = prefix or "industrial-digital-twin"
        return f"{prefix}-{fingerprint[:12]}"

    def _source_breakdown(self, chunks: list[RagChunk]) -> dict[str, int]:
        breakdown: dict[str, int] = {}
        for chunk in chunks:
            breakdown[chunk.source_type] = breakdown.get(chunk.source_type, 0) + 1
        return breakdown

    def _load_manifest(self) -> dict[str, Any] | None:
        if not self.manifest_path.exists():
            return None
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def _pinecone_headers(self) -> dict[str, str]:
        return {
            "Api-Key": self.settings.pinecone_api_key or "",
            "X-Pinecone-API-Version": self.settings.pinecone_api_version,
            "content-type": "application/json",
        }

    async def _ensure_pinecone_index(self, client: httpx.AsyncClient) -> str:
        describe_response = await client.get(
            f"{self.settings.pinecone_control_api_url}/indexes/{self.settings.pinecone_index_name}",
            headers=self._pinecone_headers(),
        )
        if describe_response.status_code == 404:
            create_response = await client.post(
                f"{self.settings.pinecone_control_api_url}/indexes",
                headers=self._pinecone_headers(),
                json={
                    "name": self.settings.pinecone_index_name,
                    "vector_type": "dense",
                    "dimension": self.settings.voyage_output_dimension,
                    "metric": self.settings.pinecone_metric,
                    "spec": {
                        "serverless": {
                            "cloud": self.settings.pinecone_cloud,
                            "region": self.settings.pinecone_region,
                        }
                    },
                    "deletion_protection": "disabled",
                },
            )
            create_response.raise_for_status()

            for _ in range(30):
                await asyncio.sleep(2)
                describe_response = await client.get(
                    f"{self.settings.pinecone_control_api_url}/indexes/{self.settings.pinecone_index_name}",
                    headers=self._pinecone_headers(),
                )
                describe_response.raise_for_status()
                payload = describe_response.json()
                if payload.get("status", {}).get("ready"):
                    host = payload.get("host")
                    if host:
                        return _normalize_host(host)
            raise RuntimeError("Timed out waiting for Pinecone index to become ready.")

        describe_response.raise_for_status()
        payload = describe_response.json()
        dimension = payload.get("dimension")
        if dimension not in (None, self.settings.voyage_output_dimension):
            raise RuntimeError(
                f"Pinecone index '{self.settings.pinecone_index_name}' uses dimension {dimension}, "
                f"but Voyage embeddings are configured for {self.settings.voyage_output_dimension}.",
            )
        host = payload.get("host")
        if not host:
            raise RuntimeError("Pinecone index host is missing from the describe response.")
        return _normalize_host(host)

    async def _embed_documents(
        self,
        client: httpx.AsyncClient,
        chunks: list[RagChunk],
    ) -> list[list[float]]:
        embeddings: list[list[float]] = []
        batch_size = max(self.settings.voyage_batch_size, 1)
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            payload = await self._request_voyage_embeddings(
                client,
                {
                    "model": self.settings.voyage_model,
                    "input": [chunk.text for chunk in batch],
                    "input_type": "document",
                    "output_dimension": self.settings.voyage_output_dimension,
                },
            )
            embeddings.extend(item.get("embedding", []) for item in payload.get("data", []))
            if start + batch_size < len(chunks):
                await asyncio.sleep(self.settings.voyage_inter_batch_delay_seconds)

        if len(embeddings) != len(chunks):
            raise RuntimeError("Voyage returned an unexpected number of embeddings for the RAG corpus.")
        return embeddings

    async def _embed_query(self, client: httpx.AsyncClient, question: str) -> list[float]:
        payload = await self._request_voyage_embeddings(
            client,
            {
                "model": self.settings.voyage_model,
                "input": [question],
                "input_type": "query",
                "output_dimension": self.settings.voyage_output_dimension,
            },
        )
        data = payload.get("data", [])
        if not data:
            raise RuntimeError("Voyage returned no embedding for the query.")
        return data[0].get("embedding", [])

    async def _request_voyage_embeddings(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        last_response: httpx.Response | None = None
        for attempt in range(1, self.settings.voyage_retry_attempts + 1):
            response = await client.post(
                self.settings.voyage_api_url,
                headers={
                    "Authorization": f"Bearer {self.settings.voyage_api_key}",
                    "content-type": "application/json",
                },
                json=payload,
            )
            if response.status_code not in {429, 500, 502, 503, 504}:
                response.raise_for_status()
                return response.json()

            last_response = response
            retry_after = response.headers.get("retry-after")
            if retry_after:
                delay = float(retry_after)
            else:
                delay = self.settings.voyage_retry_base_seconds * attempt
            await asyncio.sleep(delay)

        if last_response is not None:
            last_response.raise_for_status()
        raise RuntimeError("Voyage embedding request failed after retries.")

    async def _upsert_vectors(
        self,
        client: httpx.AsyncClient,
        host: str,
        namespace: str,
        chunks: list[RagChunk],
        embeddings: list[list[float]],
    ) -> None:
        batch_size = 64
        for start in range(0, len(chunks), batch_size):
            batch_chunks = chunks[start : start + batch_size]
            batch_embeddings = embeddings[start : start + batch_size]
            response = await client.post(
                f"https://{_normalize_host(host)}/vectors/upsert",
                headers=self._pinecone_headers(),
                json={
                    "namespace": namespace,
                    "vectors": [
                        {
                            "id": chunk.id,
                            "values": values,
                            "metadata": {
                                "citation": chunk.citation,
                                "source_type": chunk.source_type,
                                "path": str(chunk.metadata.get("path", "")),
                                "location": str(chunk.metadata.get("location", "")),
                                "title": str(chunk.metadata.get("title", "")),
                                "text": chunk.text[: self.settings.rag_max_snippet_chars],
                            },
                        }
                        for chunk, values in zip(batch_chunks, batch_embeddings, strict=True)
                    ],
                },
            )
            response.raise_for_status()
