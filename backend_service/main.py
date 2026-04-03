from __future__ import annotations

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .chat import ProjectChatbot
from .config import Settings
from .models import (
    CapabilitiesResponse,
    ChatRequest,
    DashboardPayload,
    DatasetProfile,
    EndpointDescriptor,
    IntegrationStatus,
    PipelineStageStatus,
    PipelineStatusResponse,
    RagStatusResponse,
    SourceSnapshot,
)
from .rag import RagService
from .sources import DashboardAggregator

settings = Settings()
aggregator = DashboardAggregator(settings)
rag_service = RagService(settings)
chatbot = ProjectChatbot(settings, aggregator, rag_service=rag_service)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _endpoint_catalog() -> list[EndpointDescriptor]:
    return [
        EndpointDescriptor(method="GET", path="/api/health", purpose="Basic service health check."),
        EndpointDescriptor(
            method="GET",
            path="/api/dashboard",
            purpose="Aggregated dashboard payload used by the React UI.",
        ),
        EndpointDescriptor(
            method="GET",
            path="/api/sources",
            purpose="All current source snapshots without the full dashboard wrapper.",
        ),
        EndpointDescriptor(
            method="GET",
            path="/api/sources/{source_key}",
            purpose="Inspect one source snapshot by key.",
        ),
        EndpointDescriptor(
            method="GET",
            path="/api/dataset-profile",
            purpose="Dataset size, source-universe, and join-key evidence.",
        ),
        EndpointDescriptor(
            method="GET",
            path="/api/pipeline/status",
            purpose="Pipeline-oriented summary of source, platform, and RAG readiness.",
        ),
        EndpointDescriptor(
            method="GET",
            path="/api/capabilities",
            purpose="Configured providers, integrations, and API surface overview.",
        ),
        EndpointDescriptor(
            method="POST",
            path="/api/chat",
            purpose="Project and operations advisor chat endpoint.",
        ),
        EndpointDescriptor(
            method="GET",
            path="/api/rag/status",
            purpose="Current RAG index readiness and metadata.",
        ),
        EndpointDescriptor(
            method="POST",
            path="/api/rag/reindex",
            purpose="Force a full RAG reindex using the latest dashboard payload.",
        ),
    ]


async def _build_dashboard_and_rag(
    force_refresh: bool = False,
) -> tuple[DashboardPayload, RagStatusResponse]:
    dashboard_payload = await aggregator.build_dashboard(force_refresh=force_refresh)
    rag_response = await rag_service.get_status(
        dashboard_payload,
        force_refresh=force_refresh,
    )
    return dashboard_payload, rag_response


def _build_capabilities_response() -> CapabilitiesResponse:
    return CapabilitiesResponse(
        environment=settings.app_env,
        endpoints=_endpoint_catalog(),
        ai_providers=[
            IntegrationStatus(
                name="Anthropic",
                configured=bool(settings.anthropic_api_key),
                active=bool(settings.anthropic_api_key),
                detail="Primary reasoning model for chat answers.",
            ),
            IntegrationStatus(
                name="OpenAI",
                configured=bool(settings.openai_api_key),
                active=bool(settings.openai_api_key),
                detail="Chat fallback path when Anthropic is unavailable.",
            ),
            IntegrationStatus(
                name="Gemini",
                configured=bool(settings.gemini_api_key),
                active=bool(settings.gemini_api_key),
                detail="Additional chat fallback path for advisor resilience.",
            ),
        ],
        vector_stack=[
            IntegrationStatus(
                name="Voyage",
                configured=bool(settings.voyage_api_key),
                active=bool(settings.voyage_api_key),
                detail="Embedding provider for semantic retrieval.",
            ),
            IntegrationStatus(
                name="Pinecone",
                configured=bool(settings.pinecone_api_key),
                active=bool(settings.pinecone_api_key),
                detail="Managed vector index for RAG retrieval.",
            ),
        ],
        data_integrations=[
            IntegrationStatus(
                name="SEC EDGAR",
                configured=True,
                active=True,
                detail="Public filings access through SEC fair-access headers.",
            ),
            IntegrationStatus(
                name="OSHA",
                configured=True,
                active=True,
                detail=(
                    "Uses the DOL API when credentials are present and falls back to "
                    "public OSHA.gov cited-standards scraping for manufacturing coverage."
                ),
            ),
            IntegrationStatus(
                name="ITAC / DOE",
                configured=True,
                active=True,
                detail="Bulk workbook ingestion for industrial audit context.",
            ),
            IntegrationStatus(
                name="EPA TRI",
                configured=True,
                active=True,
                detail="Public environmental compliance and facility records.",
            ),
            IntegrationStatus(
                name="NASA POWER",
                configured=True,
                active=True,
                detail="Public plant-site weather and solar context.",
            ),
            IntegrationStatus(
                name="FRED",
                configured=bool(settings.fred_api_key),
                active=bool(settings.fred_api_key),
                detail="Economic indicators for demand and cost sensitivity.",
            ),
            IntegrationStatus(
                name="EIA",
                configured=bool(settings.eia_api_key),
                active=bool(settings.eia_api_key),
                detail="Industrial electricity pricing and energy context.",
            ),
            IntegrationStatus(
                name="Stack Exchange",
                configured=True,
                active=True,
                detail="Engineering forum context via the Stack Exchange API.",
            ),
            IntegrationStatus(
                name="Reddit",
                configured=True,
                active=True,
                detail="Community signal for manufacturing and PLC topics.",
            ),
            IntegrationStatus(
                name="Catalog Scrapers",
                configured=True,
                active=True,
                detail="Vendor catalogs and equipment pages for retrieval context.",
            ),
            IntegrationStatus(
                name="SerpAPI",
                configured=bool(settings.serpapi_key),
                active=bool(settings.serpapi_key),
                detail="Live market and company search expansion for advisor queries.",
            ),
            IntegrationStatus(
                name="Glassdoor",
                configured=bool(settings.rapidapi_key),
                active=bool(settings.rapidapi_key),
                detail="Company context via RapidAPI-backed Glassdoor results.",
            ),
        ],
    )


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}


@app.get("/api/dashboard", response_model=DashboardPayload)
async def dashboard(force_refresh: bool = False) -> DashboardPayload:
    payload = await aggregator.build_dashboard(force_refresh=force_refresh)
    return payload


@app.get("/api/sources")
async def sources(force_refresh: bool = False) -> dict:
    payload = await aggregator.build_dashboard(force_refresh=force_refresh)
    return {
        "fetched_at": payload.fetched_at,
        "sourceSnapshots": [snapshot.model_dump() for snapshot in payload.sourceSnapshots],
    }


@app.get("/api/sources/{source_key}", response_model=SourceSnapshot)
async def source_by_key(source_key: str, force_refresh: bool = False) -> SourceSnapshot:
    payload = await aggregator.build_dashboard(force_refresh=force_refresh)
    for snapshot in payload.sourceSnapshots:
        if snapshot.key == source_key:
            return snapshot

    raise HTTPException(status_code=404, detail=f"Source '{source_key}' was not found.")


@app.get("/api/dataset-profile", response_model=DatasetProfile)
async def dataset_profile(force_refresh: bool = False) -> DatasetProfile:
    payload = await aggregator.build_dashboard(force_refresh=force_refresh)
    return payload.datasetProfile


@app.get("/api/pipeline/status", response_model=PipelineStatusResponse)
async def pipeline_status(force_refresh: bool = False) -> PipelineStatusResponse:
    dashboard_payload, rag_response = await _build_dashboard_and_rag(force_refresh=force_refresh)
    snapshots = dashboard_payload.sourceSnapshots
    online_sources = sum(1 for snapshot in snapshots if snapshot.state == "online")
    partial_sources = sum(1 for snapshot in snapshots if snapshot.state == "partial")
    offline_sources = sum(1 for snapshot in snapshots if snapshot.state == "offline")
    total_records = sum(snapshot.count for snapshot in snapshots)

    return PipelineStatusResponse(
        fetched_at=dashboard_payload.fetched_at,
        total_sources=len(snapshots),
        online_sources=online_sources,
        partial_sources=partial_sources,
        offline_sources=offline_sources,
        total_records=total_records,
        platform_services=dashboard_payload.stackStatus,
        stages=[
            PipelineStageStatus(
                name="Source refresh",
                status="ready" if online_sources or partial_sources else "waiting",
                detail=f"{online_sources} online, {partial_sources} partial, {offline_sources} offline.",
            ),
            PipelineStageStatus(
                name="Dashboard aggregation",
                status="ready",
                detail=f"Dashboard payload assembled at {dashboard_payload.fetched_at}.",
            ),
            PipelineStageStatus(
                name="RAG retrieval layer",
                status="ready" if rag_response.ready else "warming",
                detail=rag_response.detail,
            ),
            PipelineStageStatus(
                name="Advisor packaging",
                status="ready",
                detail="Chat context combines dashboard, source snapshots, and RAG retrieval.",
            ),
        ],
        rag=rag_response,
        dataset_profile=dashboard_payload.datasetProfile,
    )


@app.get("/api/capabilities", response_model=CapabilitiesResponse)
async def capabilities() -> CapabilitiesResponse:
    return _build_capabilities_response()


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict:
    response = await chatbot.answer(request)
    return response.model_dump()


@app.get("/api/rag/status")
async def rag_status(force_refresh: bool = False) -> dict:
    dashboard_payload = await aggregator.build_dashboard(force_refresh=force_refresh)
    response = await rag_service.get_status(dashboard_payload, force_refresh=force_refresh)
    return response.model_dump()


@app.post("/api/rag/reindex")
async def rag_reindex() -> dict:
    dashboard_payload = await aggregator.build_dashboard(force_refresh=True)
    response = await rag_service.ensure_index(dashboard_payload, force_reindex=True)
    return response.model_dump()


def run() -> None:
    uvicorn.run(
        "backend_service.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    run()
