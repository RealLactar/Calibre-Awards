"""Plain-text award values for display and write-back.

This layer formats a result; it does not explain GUI identity scope.
Series and author awards annotate the category so a stored value is not
mistaken for a book-level award.
"""

from __future__ import annotations

import re

DEFAULT_AWARD_OUTPUT_TEMPLATE = '<placement> - <year> <award> - <category>'

_PLACEHOLDER_PATTERN = re.compile(
    '|'.join(
        re.escape(name)
        for name in ('<placement>', '<year>', '<award>', '<category>')
    )
)

_MISSING_PLACEMENT = '<placement missing>'
_MISSING_YEAR = '<year missing>'
_MISSING_AWARD = '<award missing>'
_MISSING_CATEGORY = '<category missing>'


def _ordinal(rank: int) -> str:
    if 11 <= rank % 100 <= 13:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(rank % 10, 'th')
    return f'{rank}{suffix}'


def _nonempty_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_placement(result) -> str:
    # Rank is the stored ordinal; status is used only when rank is absent.
    rank = getattr(result, 'rank', None)
    if rank is not None:
        return _ordinal(rank)
    status = _nonempty_text(getattr(result, 'status', None))
    if status is not None:
        return status
    return _MISSING_PLACEMENT


def _format_year(result) -> str:
    year = getattr(result, 'award_year', None)
    if year is None:
        return _MISSING_YEAR
    return str(year)


def _format_award(result) -> str:
    award = _nonempty_text(getattr(result, 'award_name', None))
    if award is not None:
        return award
    return _MISSING_AWARD


def _format_category(result) -> str:
    category = _nonempty_text(getattr(result, 'category', None))
    identity_kind = getattr(result, 'identity_kind', 'work')
    if identity_kind == 'series':
        series_name = _nonempty_text(getattr(result, 'work_title', None))
        if category is None:
            return _MISSING_CATEGORY
        if series_name is None:
            return category
        return f'{category} [{series_name}]'
    if identity_kind == 'author':
        author_name = _nonempty_text(getattr(result, 'work_author', None))
        if category is None:
            return _MISSING_CATEGORY
        if author_name is None:
            return category
        return f'{category} [Author: {author_name}]'
    if category is not None:
        return category
    return _MISSING_CATEGORY


def format_award_result(
    result,
    template: str = DEFAULT_AWARD_OUTPUT_TEMPLATE,
) -> str:
    """Format one AwardResult using a placeholder template.

    Known placeholders in the original template are substituted exactly once.
    Placeholder-looking text inside substituted values is left unchanged.
    """
    values = {
        '<placement>': _format_placement(result),
        '<year>': _format_year(result),
        '<award>': _format_award(result),
        '<category>': _format_category(result),
    }
    return _PLACEHOLDER_PATTERN.sub(lambda match: values[match.group(0)], template)


def _format_failure_block(failures) -> str:
    failure_lines = ['Source problems:', '']
    for failure in failures:
        failure_lines.append(
            f'{failure.source_name} — {failure.error_type} — {failure.message}'
        )
    return '\n'.join(failure_lines).strip()


def format_lookup_report(
    report,
    template: str = DEFAULT_AWARD_OUTPUT_TEMPLATE,
) -> str:
    """Format an AwardLookupReport as plain text for display."""
    if not report.assessments and not report.failures:
        return 'No award results found.'

    body = '\n'.join(
        format_award_result(item.result, template)
        for item in report.assessments
    )

    if report.failures:
        failure_block = _format_failure_block(report.failures)
        if body:
            return f'{body}\n\n{failure_block}'
        return failure_block

    return body
