"""Compact identity strings for award-selection display. No matching logic."""

from __future__ import annotations


def format_work_identity(title: str, author: str) -> str:
    """Return a compact visible identity: '<title> | <author>'."""
    return f'{title.strip()} | {author.strip()}'


def source_identity_if_different(
    lookup_title: str,
    lookup_author: str,
    source_title: str,
    source_author: str,
) -> str | None:
    """Return the compact source identity only when it visibly differs.

    Comparison strips leading/trailing whitespace and otherwise requires an
    exact visible-string match. Matching-engine normalization is not applied.
    """
    if (
        lookup_title.strip() == source_title.strip()
        and lookup_author.strip() == source_author.strip()
    ):
        return None
    return format_work_identity(source_title, source_author)
