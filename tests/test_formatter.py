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

    def test_missing_category_uses_marker(self):
        result = _result(category=None)
        self.assertEqual(
            format_award_result(result),
            'Winner - 1988 Pulitzer Prize - <category missing>',
        )

    def test_empty_category_uses_marker(self):
        result = _result(category='   ')
        self.assertEqual(
            format_award_result(result),
            'Winner - 1988 Pulitzer Prize - <category missing>',
        )

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


if __name__ == '__main__':
    unittest.main()
