"""HTTP response contracts, generated into OpenAPI from the running application."""

from typing import Literal
from pydantic import Field
from ..assistant.schemas import PersonId, QueryIntent, StrictModel


class Person(StrictModel):
    person_id: PersonId
    name: str


class Source(StrictModel):
    paper_id: str
    year: int | None
    source: Literal['dblp']
    edge_id: str | None = None


class Claim(StrictModel):
    kind: str
    person_id: PersonId
    paper_id: str
    year: int | None
    text: str
    collaborator_id: PersonId | None = None
    term: str | None = None
    supported: bool
    reason: str | None
    sources: list[Source]
    data_warnings: list[str] = Field(default_factory=list)


class PaperEvidence(StrictModel):
    paper_id: str
    title: str
    year: int | None
    source: Literal['dblp']
    collaborators: list[Person]


class GroundingCounts(StrictModel):
    claims: int
    unsupported: int


class ExpertResult(Person):
    score: float
    explanation: str
    evidence: list[PaperEvidence]
    claims: list[Claim]
    grounding: GroundingCounts
    shortlisted: bool = False


class Understanding(StrictModel):
    intent: QueryIntent
    provider: Literal['recorded', 'local_llm', 'fallback']
    used_fallback: bool
    fallback_reason: str | None
    prompt_version: str


class Filters(StrictModel):
    since_year: int | None
    graph_cutoff_year: int


class AppliedDecisions(StrictModel):
    rejected_people_filtered: list[PersonId]
    shortlisted_people_marked: list[PersonId]


class Memory(StrictModel):
    version: int
    shortlisted_person_ids: list[PersonId]
    rejected_person_ids: list[PersonId]
    last_query: str | None
    last_intent: QueryIntent | None
    last_result_ids: list[PersonId]


class SearchResponse(StrictModel):
    query: str
    retrieval_query: str
    results: list[ExpertResult]
    understanding: Understanding
    effective_filters: Filters
    applied_decisions: AppliedDecisions
    memory_applied: Memory | None = None
    memory: Memory | None = None
    request_id: str | None = None


class Publication(StrictModel):
    paper_id: str
    title: str
    year: int | None
    venue: str | None
    source: Literal['dblp']


class Topic(StrictModel):
    topic: str
    source_paper_ids: list[str]
    supported: bool


class ProfileResponse(Person):
    publications: list[Publication]
    name_sources: list[str]
    topics: list[Topic]
    topic_method: str
    claims: list[Claim]


class PathEdge(StrictModel):
    from_: PersonId = Field(alias='from')
    to: PersonId
    type: Literal['coauthorship']
    evidence: list[Publication]


class PathResponse(StrictModel):
    person_ids: list[PersonId]
    edges: list[PathEdge]
    truncated: bool
    claims: list[Claim]


class ToolCall(StrictModel):
    tool: Literal['search_experts', 'get_profile', 'find_collaboration_path']
    arguments: dict
    outcome: Literal['success', 'error', 'blocked']
    error_code: str | None = None


class Safety(StrictModel):
    blocked: bool


class MessageResponse(StrictModel):
    message: str
    tool_calls: list[ToolCall]
    memory_applied: Memory
    memory: Memory
    request_id: str
    provider: Literal['none', 'recorded', 'local_llm', 'fallback']
    safety: Safety
    results: list[ExpertResult]
    claims: list[Claim]
    profile: ProfileResponse | None = None
    profiles: list[ProfileResponse] | None = None
    path: PathResponse | None = None
    query: str | None = None
    retrieval_query: str | None = None
    understanding: Understanding | None = None
    effective_filters: Filters | None = None
    applied_decisions: AppliedDecisions | None = None


class SessionResponse(StrictModel):
    session_id: str
    memory: Memory


class MutationResponse(StrictModel):
    memory: Memory
    request_id: str


class HealthResponse(StrictModel):
    status: Literal['ok', 'degraded']
    papers: int
    authors: int
    model_version: str
    query_provider: str


class ErrorResponse(StrictModel):
    code: str
    message: str
