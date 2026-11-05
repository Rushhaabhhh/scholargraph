"""Offline DBLP parsing. External DTDs are never fetched by ElementTree."""

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

from ..models import Publication
from .xml_stream import open_xml_stream

PUBLICATION_TAGS = frozenset({
    "article", "inproceedings", "proceedings", "book", "incollection",
    "phdthesis", "mastersthesis", "www", "data",
})
_WHITESPACE = re.compile(r"\s+")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def clean_text(value: str | None) -> str:
    return _WHITESPACE.sub(" ", value or "").strip()


def parse_publication(element: ET.Element) -> Publication | None:
    key = clean_text(element.get("key"))
    values = [(local_name(child.tag), clean_text("".join(child.itertext())), child)
              for child in element]
    title = next((text for tag, text, _ in values if tag == "title"), "")
    if not key or not title:
        return None
    raw_year = next((text for tag, text, _ in values if tag == "year"), "")
    if raw_year and (not raw_year.isdigit() or not 1 <= int(raw_year) <= 9999):
        raise ValueError(f"DBLP record {key} has invalid year {raw_year!r}")
    authors = [(text, child.get("pid")) for tag, text, child in values if tag == "author" and text]
    venue = next((text for tag, text, _ in values if tag in {"journal", "booktitle"} and text), None)
    return Publication(
        key=key, title=title, year=int(raw_year) if raw_year else None, venue=venue,
        authors=tuple(name for name, _ in authors), record_type=local_name(element.tag),
        author_pids=tuple(pid for _, pid in authors),
    )


def iter_publications(path: str | Path, stats: dict | None = None) -> Iterator[Publication]:
    """Release each root child, including unknown record types, to bound memory."""
    stats = stats if stats is not None else {}
    for key in ('input_records', 'yielded_records', 'skipped_unsupported', 'skipped_missing_key_or_title'):
        stats.setdefault(key, 0)
    with open_xml_stream(path) as stream:
        stack = []
        for event, element in ET.iterparse(stream, events=("start", "end")):
            if event == "start":
                stack.append(element)
                if len(stack) == 1 and local_name(element.tag) != "dblp":
                    raise ValueError("Expected a <dblp> root element")
                continue
            if len(stack) == 2:
                stats['input_records'] += 1
                supported = local_name(element.tag) in PUBLICATION_TAGS
                publication = parse_publication(element) if supported else None
                if not supported:
                    stats['skipped_unsupported'] += 1
                elif publication is None:
                    stats['skipped_missing_key_or_title'] += 1
                stack[0].remove(element)
                element.clear()
                if publication is not None:
                    stats['yielded_records'] += 1
                    yield publication
            stack.pop()
