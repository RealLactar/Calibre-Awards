"""Plain-text formatting for award lookup reports.

Temporary fixed layout; later this module will support a user-configurable
output template such as: <placement> - <year> <award> - <category>
"""


def _format_year_category(result):
    year_text = '' if result.award_year is None else str(result.award_year)
    category_text = result.category or ''
    if year_text and category_text:
        return f'{year_text} — {category_text}'
    return year_text or category_text


def _format_assessment(assessment):
    result = assessment.result
    lines = [
        f'{result.work_title} — {result.work_author}',
        '',
        result.award_name,
    ]
    year_category = _format_year_category(result)
    if year_category:
        lines.append(year_category)
    lines.extend([
        result.status,
        assessment.qualification.decision.name,
        '',
        f'Source: {result.source_name}',
    ])
    if result.source_url:
        lines.append(f'URL: {result.source_url}')
    return '\n'.join(lines)


def format_lookup_report(report) -> str:
    """Format an AwardLookupReport as plain text for temporary display."""
    if not report.assessments and not report.failures:
        return 'No award results found.'

    sections = [_format_assessment(item) for item in report.assessments]
    body = '\n\n'.join(sections)

    if report.failures:
        failure_lines = ['Source problems:', '']
        for failure in report.failures:
            failure_lines.append(
                f'{failure.source_name} — {failure.error_type} — {failure.message}'
            )
        failure_block = '\n'.join(failure_lines).strip()
        if body:
            return f'{body}\n\n{failure_block}'
        return failure_block

    return body
