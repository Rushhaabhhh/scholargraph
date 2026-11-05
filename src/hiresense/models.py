from dataclasses import dataclass, field


@dataclass(frozen=True)
class Publication:
    key: str
    title: str
    year: int | None
    venue: str | None
    authors: tuple[str, ...]
    record_type: str = "article"
    author_pids: tuple[str | None, ...] = ()


@dataclass(frozen=True)
class GroundTruthQuery:
    query_id: str
    text: str
    source_paper_id: str
    year: int
    relevant_author_ids: tuple[int, ...]


@dataclass(frozen=True)
class NoisyAuthorRecord:
    record_id: str
    noisy_name: str
    observed_years: tuple[int, ...] = field(default_factory=tuple)
    observed_coauthors: tuple[str, ...] = field(default_factory=tuple)
    observed_venues: tuple[str, ...] = field(default_factory=tuple)
    corruptions: tuple[str, ...] = field(default_factory=tuple)
