from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SourceState = Literal["online", "partial", "offline"]
FeedTone = Literal["ok", "warn", "alert"]


class SourceSnapshot(BaseModel):
    key: str
    name: str
    state: SourceState
    summary: str
    count: int = 0
    records: list[dict[str, Any]] = Field(default_factory=list)
    warning: str | None = None
    updated_at: str | None = None


class SourceCard(BaseModel):
    name: str
    volume: str
    detail: str


class DatasetSourceProfile(BaseModel):
    name: str
    acquisition: str
    estimated_size: str
    challenge: str


class DatasetProfile(BaseModel):
    total_estimated_size: str
    source_count: int
    join_keys: list[str] = Field(default_factory=list)
    engineering_note: str
    sources: list[DatasetSourceProfile] = Field(default_factory=list)


class FeedEntry(BaseModel):
    source: str
    tone: FeedTone
    text: str


class StackStatusItem(BaseModel):
    name: str
    state: SourceState


class DashboardPayload(BaseModel):
    fetched_at: str
    stackStatus: list[StackStatusItem]
    liveFeed: list[FeedEntry]
    proposalHighlights: list[str]
    datasetProfile: DatasetProfile
    sourceCards: list[SourceCard]
    sourceSnapshots: list[SourceSnapshot]


ChatRole = Literal["user", "assistant"]


class ChatMessage(BaseModel):
    role: ChatRole
    content: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list)
    active_view: str | None = None
    selected_line: dict[str, Any] | None = None
    factory_state: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    answer: str
    model: str
    citations: list[str] = Field(default_factory=list)
    used_live_data: bool = True


class RagStatusResponse(BaseModel):
    configured: bool
    ready: bool
    detail: str
    index_name: str | None = None
    namespace: str | None = None
    document_count: int = 0
    source_breakdown: dict[str, int] = Field(default_factory=dict)
    proposal_path: str | None = None
    indexed_at: str | None = None
    warnings: list[str] = Field(default_factory=list)


class EndpointDescriptor(BaseModel):
    method: str
    path: str
    purpose: str


class IntegrationStatus(BaseModel):
    name: str
    configured: bool
    active: bool
    detail: str


class CapabilitiesResponse(BaseModel):
    environment: str
    endpoints: list[EndpointDescriptor] = Field(default_factory=list)
    ai_providers: list[IntegrationStatus] = Field(default_factory=list)
    vector_stack: list[IntegrationStatus] = Field(default_factory=list)
    data_integrations: list[IntegrationStatus] = Field(default_factory=list)


class PipelineStageStatus(BaseModel):
    name: str
    status: str
    detail: str


class PipelineStatusResponse(BaseModel):
    fetched_at: str
    total_sources: int
    online_sources: int
    partial_sources: int
    offline_sources: int
    total_records: int
    platform_services: list[StackStatusItem] = Field(default_factory=list)
    stages: list[PipelineStageStatus] = Field(default_factory=list)
    rag: RagStatusResponse
    dataset_profile: DatasetProfile
