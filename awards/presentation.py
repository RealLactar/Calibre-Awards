"""Compact identity strings for award-selection display. No matching logic."""

from __future__ import annotations


def format_work_identity(title: str, author: str) -> str:
    """Return a compact visible identity: '<title> | <author>'."""
    return f'{title.strip()} | {author.strip()}'


def format_book_line(title: str, author: str) -> str:
    """Return the Book header line for the award-selection dialog."""
    return f'Book: {format_work_identity(title, author)}'


def format_series_line(series: str) -> str | None:
    """Return the Series header line, or None when series context is empty."""
    text = series.strip()
    if not text:
        return None
    return f'Series: {text}'


def lookup_has_series_award(lookup_series: str, assessments) -> bool:
    """True when series context is present and a series award is displayed."""
    if not lookup_series.strip():
        return False
    return any(
        getattr(item.result, 'identity_kind', 'work') == 'series'
        for item in assessments
    )


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
