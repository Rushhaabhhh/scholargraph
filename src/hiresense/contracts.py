"""Shared offline contracts for the batch command and future API.

SQLite is the system of record. Derived graph snapshots and indexes bind to a
source digest and cutoff. Python owns data, retrieval, and assistant tools; the
TypeScript browser client will communicate only through the FastAPI boundary.
"""

from dataclasses import asdict, dataclass
from pathlib import Path

CONTRACT_VERSION = 1
DEFAULT_DATABASE = Path("data/hiresense.sqlite3")


@dataclass(frozen=True)
class SplitConfig:
    graph_cutoff_year: int
    train_end_year: int
    validation_end_year: int
    test_end_year: int

    def __post_init__(self):
        years = tuple(asdict(self).values())
        if any(type(year) is not int or not 1 <= year <= 9999 for year in years):
            raise ValueError("Split years must be integers from 1 through 9999")
        if not all(left < right for left, right in zip(years, years[1:])):
            raise ValueError("Require graph cutoff < train end < validation end < test end")


def validate_batch_results(payload: list[dict]) -> None:
    """Validate the shared search response before writing user-visible output."""
    import math

    if not isinstance(payload, list):
        raise ValueError('Batch output must be a list')
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError('Each search must be an object')
        if not isinstance(item.get("query"), str) or not isinstance(item.get("results"), list):
            raise ValueError("Each search needs a query and results list")
        seen = set()
        previous = math.inf
        for person in item["results"]:
            if (not isinstance(person, dict) or type(person.get("person_id")) is not int
                    or not 0 <= person["person_id"] <= 9007199254740991 or person["person_id"] in seen):
                raise ValueError("Results must contain unique integer person IDs")
            seen.add(person["person_id"])
            score = person.get("score")
            if type(score) not in (int, float) or not math.isfinite(score) or score > previous:
                raise ValueError("Scores must be finite and sorted descending")
            previous = score
            if (any(not isinstance(person.get(field), str) or not person[field] for field in ("name", "explanation"))
                    or not isinstance(person.get("evidence"), list) or not person["evidence"]):
                raise ValueError("Each result needs a name, explanation and evidence")
            paper_ids = set()
            for paper in person["evidence"]:
                if (not isinstance(paper, dict) or any(not isinstance(paper.get(field), str) or not paper[field] for field in ("paper_id", "title"))
                        or paper.get("source") != "dblp" or paper["paper_id"] in paper_ids):
                    raise ValueError("Paper evidence needs its DBLP key, title and source")
                paper_ids.add(paper["paper_id"])
                if paper.get("year") is not None and (type(paper["year"]) is not int or not 1 <= paper["year"] <= 9999):
                    raise ValueError("Paper years must be integers or null")
                if not isinstance(paper.get("collaborators"), list):
                    raise ValueError("Paper evidence needs a collaborators list")
                collaborator_ids = set()
                for collaborator in paper["collaborators"]:
                    if (not isinstance(collaborator, dict) or type(collaborator.get("person_id")) is not int
                            or not 0 <= collaborator["person_id"] <= 9007199254740991
                            or collaborator["person_id"] == person["person_id"]
                            or collaborator["person_id"] in collaborator_ids
                            or not isinstance(collaborator.get("name"), str) or not collaborator["name"]):
                        raise ValueError("Invalid or duplicate collaborator")
                    collaborator_ids.add(collaborator["person_id"])
