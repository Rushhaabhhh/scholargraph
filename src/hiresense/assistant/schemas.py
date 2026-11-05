"""Strict boundaries for untrusted inputs, provider outputs, and graph tools."""

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .safety import normalized_text

PersonId = Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]
Text = Annotated[str, Field(strict=True, min_length=1, max_length=4000)]
RequestId = Annotated[str, Field(strict=True, pattern=r'^[A-Za-z0-9_-]{8,80}$')]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', allow_inf_nan=False)


class QueryIntent(StrictModel):
    topics: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(min_length=1, max_length=8)
    recency_preference: Literal['any', 'recent'] = 'any'
    since_year: Annotated[int, Field(ge=1, le=9999)] | None = None

    @field_validator('topics')
    @classmethod
    def clean_topics(cls, value):
        value = [' '.join(topic.split()) for topic in value]
        if any(not topic for topic in value):
            raise ValueError('Topics must contain visible text')
        value = list(dict.fromkeys(value))
        if len(' '.join(value)) > 4000:
            raise ValueError('Combined topics exceed the query limit')
        return value


class SearchExpertsArgs(StrictModel):
    query: Text
    limit: Annotated[int, Field(ge=1, le=100)] = 10
    recency_preference: Literal['any', 'recent'] | None = None
    since_year: Annotated[int, Field(ge=1, le=9999)] | None = None

    @field_validator('query')
    @classmethod
    def nonblank_query(cls, value):
        if not normalized_text(value).strip():
            raise ValueError('Query must contain visible text')
        return value


class ProfileArgs(StrictModel):
    person_id: PersonId


class PathArgs(StrictModel):
    source: PersonId
    target: PersonId
    max_hops: Annotated[int, Field(ge=0, le=6)] = 4


class DecisionRequest(StrictModel):
    decision: Literal['shortlist', 'reject', 'clear']
    expected_version: Annotated[int, Field(ge=0)]
    request_id: RequestId


class RevisionRequest(StrictModel):
    expected_version: Annotated[int, Field(ge=0)]
    request_id: RequestId


class MessageRequest(RevisionRequest):
    message: Text

    @field_validator('message')
    @classmethod
    def nonblank_message(cls, value):
        if not normalized_text(value).strip():
            raise ValueError('Message must contain visible text')
        return value


class SearchRequest(SearchExpertsArgs):
    session_id: Annotated[str, Field(pattern=r'^[a-f0-9]{32}$')] | None = None
    expected_version: Annotated[int, Field(ge=0)] | None = None
    request_id: RequestId | None = None

    @model_validator(mode='after')
    def require_session_revision(self):
        if self.session_id is not None and (self.expected_version is None or self.request_id is None):
            raise ValueError('Session searches require an expected version and request ID')
        if self.session_id is None and (self.expected_version is not None or self.request_id is not None):
            raise ValueError('Revision fields require a session')
        return self


class ClaimDraft(StrictModel):
    kind: Literal['authorship', 'coauthorship', 'title_term']
    person_id: PersonId
    paper_id: Annotated[str, Field(min_length=1, max_length=1000)]
    year: Annotated[int, Field(ge=1, le=9999)] | None = None
    collaborator_id: PersonId | None = None
    term: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    text: Annotated[str, Field(min_length=1, max_length=5000)]
