"""Unit tests for award-result template formatting."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from awards.engine import AwardAssessment, AwardLookupReport, SourceFailure
from awards.formatter import (
    DEFAULT_AWARD_OUTPUT_TEMPLATE,
    format_award_result,
    format_lookup_report,
)
from awards.model import AwardResult
from awards.qualifier import QualificationDecision, QualificationResult


def _result(**overrides) -> AwardResult:
    values = {
        'work_title': 'Beloved',
        'work_author': 'Toni Morrison',
        'award_name': 'Pulitzer Prize',
        'award_year': 1988,
        'category': 'Fiction',
        'status': 'Winner',
        'rank': None,
        'source_name': 'Pulitzer Prizes',
        'source_url': 'https://www.pulitzer.org/prize-winners-by-category/219',
    }
    values.update(overrides)
    return AwardResult(**values)


def _assessment(result: AwardResult) -> AwardAssessment:
    return AwardAssessment(
        result=result,
        qualification=QualificationResult(
            QualificationDecision.QUALIFIES,
            'test',
        ),
    )


class AwardResultFormattingTests(unittest.TestCase):
    def test_winner_with_no_rank_uses_status(self):
        result = _result(status='Winner', rank=None)
        self.assertEqual(
            format_award_result(result),
            'Winner - 1988 Pulitzer Prize - Fiction',
        )

    def test_explicit_rank_1_is_ordinal_not_winner(self):
        result = _result(status='Winner', rank=1)
        self.assertEqual(
            format_award_result(result),
            '1st - 1988 Pulitzer Prize - Fiction',
        )

    def test_explicit_rank_2_is_ordinal(self):
        result = _result(status='Winner', rank=2)
        self.assertEqual(
            format_award_result(result),
            '2nd - 1988 Pulitzer Prize - Fiction',
        )

    def test_explicit_rank_3_is_ordinal(self):
        result = _result(rank=3)
        self.assertEqual(
            format_award_result(result),
            '3rd - 1988 Pulitzer Prize - Fiction',
        )

    def test_explicit_rank_4_is_ordinal(self):
        result = _result(rank=4)
        self.assertEqual(
            format_award_result(result),
            '4th - 1988 Pulitzer Prize - Fiction',
        )

    def test_explicit_rank_5_is_ordinal(self):
        result = _result(rank=5)
        self.assertEqual(
            format_award_result(result),
            '5th - 1988 Pulitzer Prize - Fiction',
        )

    def test_eleventh_twelfth_thirteenth_use_th(self):
        self.assertEqual(
            format_award_result(_result(rank=11)),
            '11th - 1988 Pulitzer Prize - Fiction',
        )
        self.assertEqual(
            format_award_result(_result(rank=12)),
            '12th - 1988 Pulitzer Prize - Fiction',
        )
        self.assertEqual(
            format_award_result(_result(rank=13)),
            '13th - 1988 Pulitzer Prize - Fiction',
        )

    def test_twenty_first_is_st(self):
        result = _result(rank=21)
        self.assertEqual(
            format_award_result(result),
            '21st - 1988 Pulitzer Prize - Fiction',
        )

    def test_twenty_second_and_twenty_third(self):
        self.assertEqual(
            format_award_result(_result(rank=22)),
            '22nd - 1988 Pulitzer Prize - Fiction',
        )
        self.assertEqual(
            format_award_result(_result(rank=23)),
            '23rd - 1988 Pulitzer Prize - Fiction',
        )

    def test_missing_award_year_uses_marker(self):
        result = _result(award_year=None)
        self.assertEqual(
            format_award_result(result),
            'Winner - <year missing> Pulitzer Prize - Fiction',
        )

    def test_missing_year_keeps_marker_when_category_is_absent(self):
        result = _result(award_year=None, category=None)
        formatted = format_award_result(result)
        self.assertEqual(formatted, 'Winner - <year missing> Pulitzer Prize')
        self.assertIn('<year missing>', formatted)
        self.assertNotIn('<category missing>', formatted)

    def test_present_category_keeps_default_segment(self):
        result = _result(
            work_title='The Poet',
            work_author='Michael Connelly',
            award_name='Edgar Award',
            award_year=2026,
            category='Best Novel',
            status='Winner',
            rank=None,
            source_name='Mystery Writers of America',
            source_url='https://edgarawards.com/',
        )
        self.assertEqual(
            format_award_result(result),
            'Winner - 2026 Edgar Award - Best Novel',
        )

    def test_none_category_omits_segment_and_separator(self):
        result = _result(
            work_title='More Than Friendship',
            work_author='Mary Howard',
            award_name='Romantic Novel of the Year Award',
            award_year=1960,
            category=None,
            status='Winner',
            rank=None,
            source_name="Romantic Novelists' Association",
            source_url='https://romanticnovelistsassociation.org/past-winners/more-than-friendship',
        )
        formatted = format_award_result(result)
        self.assertEqual(
            formatted,
            'Winner - 1960 Romantic Novel of the Year Award',
        )
        self.assertNotIn('<category missing>', formatted)
        self.assertNotIn('Overall', formatted)
        self.assertFalse(formatted.endswith(' -'))
        self.assertFalse(formatted.endswith(' '))

    def test_empty_category_omits_segment_and_separator(self):
        result = _result(category='')
        formatted = format_award_result(result)
        self.assertEqual(formatted, 'Winner - 1988 Pulitzer Prize')
        self.assertNotIn('<category missing>', formatted)
        self.assertFalse(formatted.endswith(' -'))

    def test_whitespace_category_omits_segment_and_separator(self):
        result = _result(category='   ')
        formatted = format_award_result(result)
        self.assertEqual(formatted, 'Winner - 1988 Pulitzer Prize')
        self.assertNotIn('<category missing>', formatted)

    def test_default_template_constant_and_output(self):
        self.assertEqual(
            DEFAULT_AWARD_OUTPUT_TEMPLATE,
            '<placement> - <year> <award> - <category>',
        )
        result = _result()
        self.assertEqual(
            format_award_result(result),
            format_award_result(result, DEFAULT_AWARD_OUTPUT_TEMPLATE),
        )
        self.assertEqual(
            format_award_result(result),
            'Winner - 1988 Pulitzer Prize - Fiction',
        )

    def test_custom_template_uses_four_placeholders(self):
        result = _result(status='Finalist', award_year=1991)
        self.assertEqual(
            format_award_result(
                result,
                template='<award> (<year>): <placement> [<category>]',
            ),
            'Pulitzer Prize (1991): Finalist [Fiction]',
        )

    def test_custom_template_omits_absent_category_without_empty_brackets(self):
        result = _result(category=None)
        self.assertEqual(
            format_award_result(
                result,
                template='<award> (<year>): <placement> [<category>]',
            ),
            'Pulitzer Prize (1988): Winner',
        )

    def test_placeholder_text_inside_status_is_not_replaced(self):
        result = _result(status='Contains <year>')
        self.assertEqual(
            format_award_result(result),
            'Contains <year> - 1988 Pulitzer Prize - Fiction',
        )

    def test_placeholder_text_inside_award_name_is_not_replaced(self):
        result = _result(award_name='Prize <category> Annual')
        self.assertEqual(
            format_award_result(result),
            'Winner - 1988 Prize <category> Annual - Fiction',
        )

    def test_unknown_placeholder_remains_unchanged(self):
        result = _result()
        self.assertEqual(
            format_award_result(result, template='<placement> <unknown> <award>'),
            'Winner <unknown> Pulitzer Prize',
        )

    def test_status_is_not_converted_into_a_rank(self):
        result = _result(status='Finalist', rank=None)
        formatted = format_award_result(result)
        self.assertEqual(
            formatted,
            'Finalist - 1988 Pulitzer Prize - Fiction',
        )
        self.assertNotIn('2nd', formatted)
        self.assertNotIn('1st', formatted)

    def test_explicit_rank_ignores_status_text(self):
        result = _result(status='Winner', rank=2)
        formatted = format_award_result(result)
        self.assertTrue(formatted.startswith('2nd - '))
        self.assertNotIn('Winner', formatted)

    def test_missing_award_name_uses_marker(self):
        result = SimpleNamespace(
            award_name='   ',
            award_year=1988,
            category='Fiction',
            status='Winner',
            rank=None,
        )
        self.assertEqual(
            format_award_result(result),
            'Winner - 1988 <award missing> - Fiction',
        )

    def test_missing_placement_uses_marker(self):
        result = SimpleNamespace(
            award_name='Pulitzer Prize',
            award_year=1988,
            category='Fiction',
            status='   ',
            rank=None,
        )
        self.assertEqual(
            format_award_result(result),
            '<placement missing> - 1988 Pulitzer Prize - Fiction',
        )


class LookupReportFormattingTests(unittest.TestCase):
    def test_report_uses_default_template(self):
        report = AwardLookupReport(
            assessments=(_assessment(_result()),),
            failures=(),
        )
        self.assertEqual(
            format_lookup_report(report),
            'Winner - 1988 Pulitzer Prize - Fiction',
        )

    def test_report_accepts_custom_template(self):
        report = AwardLookupReport(
            assessments=(_assessment(_result(rank=2)),),
            failures=(),
        )
        self.assertEqual(
            format_lookup_report(report, template='<placement> | <award>'),
            '2nd | Pulitzer Prize',
        )

    def test_source_failures_appear_in_report(self):
        report = AwardLookupReport(
            assessments=(_assessment(_result()),),
            failures=(
                SourceFailure(
                    source_name='Nebula Awards',
                    error_type='TimeoutError',
                    message='timed out',
                ),
            ),
        )
        text = format_lookup_report(report)
        self.assertEqual(
            text,
            'Winner - 1988 Pulitzer Prize - Fiction\n'
            '\n'
            'Source problems:\n'
            '\n'
            'Nebula Awards — TimeoutError — timed out',
        )

    def test_failures_only_report_still_includes_source_problems(self):
        report = AwardLookupReport(
            assessments=(),
            failures=(
                SourceFailure(
                    source_name='Pulitzer Prizes',
                    error_type='URLError',
                    message='network down',
                ),
            ),
        )
        self.assertEqual(
            format_lookup_report(report),
            'Source problems:\n'
            '\n'
            'Pulitzer Prizes — URLError — network down',
        )


class SeriesAwardFormattingTests(unittest.TestCase):
    def test_best_series_appends_official_name_inside_category(self):
        result = _result(
            work_title='The Vorkosigan Saga',
            work_author='Lois McMaster Bujold',
            award_name='Hugo Award',
            award_year=2017,
            category='Best Series',
            status='Winner',
            rank=None,
            source_name='Hugo Awards',
            source_url='https://www.thehugoawards.org/hugo-history/2017-hugo-awards/',
            identity_kind='series',
        )
        formatted = format_award_result(result)
        self.assertEqual(
            formatted,
            'Winner - 2017 Hugo Award - Best Series [The Vorkosigan Saga]',
        )
        self.assertEqual(formatted.split(' - '), [
            'Winner',
            '2017 Hugo Award',
            'Best Series [The Vorkosigan Saga]',
        ])

    def test_work_hugo_novel_output_is_unchanged(self):
        result = _result(
            work_title='Dune',
            work_author='Frank Herbert',
            award_name='Hugo Award',
            award_year=1966,
            category='Best Novel',
            status='Winner',
            rank=None,
            source_name='Hugo Awards',
            source_url='https://www.thehugoawards.org/hugo-history/1966-hugo-awards/',
        )
        self.assertEqual(
            format_award_result(result),
            'Winner - 1966 Hugo Award - Best Novel',
        )
        self.assertEqual(result.identity_kind, 'work')


class AuthorAwardFormattingTests(unittest.TestCase):
    def test_author_identity_appends_author_scope_inside_category(self):
        result = _result(
            work_title='Ernest Hemingway',
            work_author='Ernest Hemingway',
            award_name='Nobel Prize',
            award_year=1954,
            category='Literature',
            status='Winner',
            rank=None,
            source_name='NobelPrize.org',
            source_url='https://www.nobelprize.org/prizes/literature/1954/hemingway/facts/',
            identity_kind='author',
        )
        formatted = format_award_result(result)
        self.assertEqual(
            formatted,
            'Winner - 1954 Nobel Prize - Literature [Author: Ernest Hemingway]',
        )
        self.assertEqual(formatted.split(' - '), [
            'Winner',
            '1954 Nobel Prize',
            'Literature [Author: Ernest Hemingway]',
        ])

    def test_author_annotation_uses_work_author_not_work_title(self):
        result = _result(
            work_title='Canonical Awarded Author Identity',
            work_author='Displayed Author',
            award_name='Nobel Prize',
            award_year=1954,
            category='Literature',
            identity_kind='author',
        )
        formatted = format_award_result(result)
        self.assertEqual(
            formatted,
            'Winner - 1954 Nobel Prize - Literature [Author: Displayed Author]',
        )
        self.assertNotIn('Canonical Awarded Author Identity', formatted)

    def test_author_custom_template_still_substitutes_placeholders(self):
        result = _result(
            work_title='Ernest Hemingway',
            work_author='Ernest Hemingway',
            award_name='Nobel Prize',
            award_year=1954,
            category='Literature',
            identity_kind='author',
        )
        self.assertEqual(
            format_award_result(
                result,
                template='<award> (<year>): <placement> [<category>]',
            ),
            'Nobel Prize (1954): Winner [Literature [Author: Ernest Hemingway]]',
        )

    def test_work_formatting_is_unchanged_beside_author_results(self):
        result = _result()
        self.assertEqual(
            format_award_result(result),
            'Winner - 1988 Pulitzer Prize - Fiction',
        )

    def test_cited_work_nobel_formats_without_author_or_cited_suffix(self):
        result = _result(
            work_title='The Old Man and the Sea',
            work_author='Ernest Hemingway',
            award_name='Nobel Prize',
            award_year=1954,
            category='Literature',
            status='Winner',
            rank=None,
            source_name='NobelPrize.org',
            source_url='https://www.nobelprize.org/prizes/literature/1954/hemingway/facts/',
            notes=None,
            identity_kind='work',
            is_specifically_cited_work=True,
        )
        formatted = format_award_result(result)
        self.assertEqual(
            formatted,
            'Winner - 1954 Nobel Prize - Literature',
        )
        self.assertNotIn('[Author:', formatted)
        self.assertNotIn('specifically cited', formatted)


if __name__ == '__main__':
    unittest.main()
