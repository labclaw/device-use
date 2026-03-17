"""Document retriever for device knowledge bases.

Loads a YAML index of device documentation and performs keyword+tag matching
to find relevant pages for a given task description.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class DocPage(BaseModel):
    """A single documentation page entry."""

    path: str
    title: str
    tags: list[str] = Field(default_factory=list)
    summary: str = ""
    category: str | None = None


class DocIndex(BaseModel):
    """Index of all documentation pages for a device/software."""

    version: str
    software: str
    pages: list[DocPage] = Field(default_factory=list)


def load_index(docs_dir: Path) -> DocIndex:
    """Load a documentation index from index.yaml in the given directory."""
    index_path = docs_dir / "index.yaml"
    if not index_path.exists():
        raise FileNotFoundError(f"No index.yaml found in {docs_dir}")
    with open(index_path) as f:
        data = yaml.safe_load(f)
    return DocIndex(**data)


class DocRetriever:
    """Retrieves relevant documentation pages for a given task.

    Uses keyword and tag matching against the documentation index to find
    the most relevant pages, then returns their content as formatted markdown.
    """

    def __init__(self, docs_dir: Path) -> None:
        self.docs_dir = docs_dir
        self.index = load_index(docs_dir)

    def query(self, task: str, max_results: int = 5, max_chars: int = 6000) -> str:
        """Find and return relevant documentation for a task.

        Scoring:
            - Tag match: 2.0 per matching keyword
            - Title match: 1.0 per matching keyword
            - Summary match: 0.5 per matching keyword

        Args:
            task: Natural language description of the task.
            max_results: Maximum number of pages to return.
            max_chars: Maximum total characters in the result.

        Returns:
            Formatted markdown string with relevant doc sections.
        """
        keywords = _extract_keywords(task)
        if not keywords:
            return ""

        scored: list[tuple[float, DocPage]] = []
        for page in self.index.pages:
            score = _score_page(page, keywords)
            if score > 0:
                scored.append((score, page))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:max_results]

        if not top:
            return ""

        parts: list[str] = []
        total = 0
        for _score, page in top:
            doc_path = self.docs_dir / page.path
            if doc_path.exists():
                content = doc_path.read_text(encoding="utf-8")
            else:
                content = f"*File not found: {page.path}*"

            section = f"## {page.title}\n\n{content}"
            if total + len(section) > max_chars and parts:
                break
            parts.append(section)
            total += len(section)

        header = f"# {self.index.software} v{self.index.version} — Relevant Documentation\n\n"
        return header + "\n\n---\n\n".join(parts)


def _extract_keywords(text: str) -> list[str]:
    """Extract lowercase keywords from text, filtering out stopwords."""
    stopwords = {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "can",
        "shall",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "out",
        "off",
        "over",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "every",
        "both",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "and",
        "but",
        "or",
        "if",
        "it",
        "its",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "he",
        "she",
        "they",
        "them",
        "this",
        "that",
        "these",
        "those",
        "what",
        "which",
    }
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in stopwords and len(w) > 1]


def _score_page(page: DocPage, keywords: list[str]) -> float:
    """Score a page against a list of keywords."""
    score = 0.0
    tags_lower = [t.lower() for t in page.tags]
    title_lower = page.title.lower()
    summary_lower = page.summary.lower()

    for kw in keywords:
        if any(kw in tag for tag in tags_lower):
            score += 2.0
        if kw in title_lower:
            score += 1.0
        if kw in summary_lower:
            score += 0.5
    return score


def retrieve_docs(
    device_name: str,
    task: str,
    skills_dir: Path | None = None,
) -> str:
    """Convenience function to retrieve docs for a named device.

    Looks for docs in ``{skills_dir}/devices/{device_name}/docs/``.

    Args:
        device_name: Device identifier (e.g. ``bruker-topspin``).
        task: Natural language task description.
        skills_dir: Path to the device-skills root. Defaults to
            ``../../device-skills`` relative to this file.

    Returns:
        Formatted markdown with relevant documentation, or empty string
        if no docs are found.
    """
    if skills_dir is None:
        # Default: assume monorepo layout
        skills_dir = Path(__file__).resolve().parents[4] / "device-skills"

    docs_dir = skills_dir / "devices" / device_name / "docs"
    if not docs_dir.exists():
        return ""

    retriever = DocRetriever(docs_dir)
    return retriever.query(task)
