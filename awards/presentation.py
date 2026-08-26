"""GUI identity and scope captions. Separate from formatter write-back values.

These helpers explain whether a result is for the current book, a series, an
author, or a specifically cited work. They do not match titles or qualify
awards.
"""

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


def result_identity_kind(result) -> str:
    """Return identity_kind, defaulting to work when absent."""
    kind = getattr(result, 'identity_kind', 'work')
    if kind == 'series':
        return 'series'
    if kind == 'author':
        return 'author'
    return 'work'


def lookup_has_series_award(lookup_series: str, assessments) -> bool:
    """True when series context is present and a series award is displayed."""
    if not lookup_series.strip():
        return False
    return any(
        result_identity_kind(item.result) == 'series'
        for item in assessments
    )


def format_author_award_caption(author: str) -> str:
    """Return the quiet author-award scope caption."""
    return (
        f'AUTHOR AWARD - Awarded to {author.strip()}, '
        'not specifically to this book.'
    )


# Display prose only. Cited-work state lives on AwardResult.is_specifically_cited_work.
CITED_WORK_SCOPE_NOTE = (
    'This work was specifically cited in the Nobel Prize motivation.'
)


def format_cited_work_caption() -> str:
    """Return the quiet specifically-cited-work scope caption."""
    return f'WORK AWARD - {CITED_WORK_SCOPE_NOTE}'


def is_cited_work_result(result) -> bool:
    """True when the semantic cited-work flag is set on a work result.

    Caption text and notes are display only; they must not be used as the
    marker.
    """
    if result_identity_kind(result) != 'work':
        return False
    return getattr(result, 'is_specifically_cited_work', False) is True


def format_possible_author_match_warning(result, lookup_author: str) -> str | None:
    """Return a GUI warning when identity confirmation is required.

    Driven by identity_confirmation_required, not by matching note text.
    """
    if getattr(result, 'identity_confirmation_required', False) is not True:
        return None
    source_author = (getattr(result, 'work_author', '') or '').strip()
    calibre_author = lookup_author.strip()
    return (
        f'POSSIBLE AUTHOR MATCH - Source lists "{source_author}"; '
        f'Calibre lists "{calibre_author}". Confirm this result before including it.'
    )


def default_award_row_checked(
    *,
    qualifies: bool,
    identity_confirmation_required: bool,
) -> bool:
    """Return whether an award row should start checked.

    Qualification recommends a row. Identity confirmation withholds
    automatic selection even when the result QUALIFIES.
    """
    if identity_confirmation_required:
        return False
    return bool(qualifies)


def source_author_identity_if_different(
    lookup_author: str,
    source_author: str,
) -> str | None:
    """Return the official author spelling only when it visibly differs."""
    official = source_author.strip()
    if lookup_author.strip() == official:
        return None
    return official or None


def match_row_scope_lines(
    result,
    lookup_title: str,
    lookup_author: str,
    lookup_series: str = '',
) -> tuple[str, ...]:
    """Return extra award-row lines for identity scope.

    Author awards never compare the Calibre book title to work_title.
    Series awards compare Calibre series identity, not the book title.
    """
    warning = format_possible_author_match_warning(result, lookup_author)
    prefix = (warning,) if warning is not None else ()
    kind = result_identity_kind(result)
    work_title = getattr(result, 'work_title', '') or ''
    work_author = getattr(result, 'work_author', '') or ''
    if kind == 'author':
        lines = [format_author_award_caption(work_author)]
        source_author = source_author_identity_if_different(
            lookup_author,
            work_author,
        )
        if source_author is not None:
            lines.append(f'Source author: {source_author}')
        return prefix + tuple(lines)
    if kind == 'series':
        source_identity = source_identity_if_different(
            lookup_series,
            lookup_author,
            work_title,
            work_author,
        )
        if source_identity is None:
            return prefix
        return prefix + (f'Source series: {source_identity}',)
    lines: list[str] = []
    if is_cited_work_result(result):
        lines.append(format_cited_work_caption())
    source_identity = source_identity_if_different(
        lookup_title,
        lookup_author,
        work_title,
        work_author,
    )
    if source_identity is not None:
        lines.append(f'Source: {source_identity}')
    return prefix + tuple(lines)


def source_identity_if_different(
    lookup_title: str,
    lookup_author: str,
    source_title: str,
    source_author: str,
) -> str | None:
    """Return the compact source identity only when it visibly differs.

    Comparison strips surrounding whitespace and otherwise requires an exact
    visible-string match. Matching-engine normalization is not applied, so a
    spelling the matcher treated as equivalent can still be shown.
    """
    if (
        lookup_title.strip() == source_title.strip()
        and lookup_author.strip() == source_author.strip()
    ):
        return None
    return format_work_identity(source_title, source_author)
