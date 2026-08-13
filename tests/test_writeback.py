"""Unit tests for Calibre-free award write-back helpers."""

from __future__ import annotations

import unittest

from awards.engine import AwardAssessment, AwardLookupReport, SourceFailure
from awards.formatter import DEFAULT_AWARD_OUTPUT_TEMPLATE, format_award_result
from awards.model import AwardResult
from awards.qualifier import QualificationDecision, QualificationResult
from awards.writeback import (
    append_award_values,
    formatted_qualifying_awards,
    partition_comma_unsafe_award_values,
    prepare_append_award_values,
    prepare_replace_award_values,
    replace_award_values,
    unique_award_values,
)


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


def _assessment(
    result: AwardResult,
    decision: QualificationDecision = QualificationDecision.QUALIFIES,
) -> AwardAssessment:
    return AwardAssessment(
        result=result,
        qualification=QualificationResult(decision, 'test'),
    )


class QualifyingAwardFormattingTests(unittest.TestCase):
    def test_qualifies_is_included(self):
        report = AwardLookupReport(
            assessments=(_assessment(_result()),),
            failures=(),
        )
        self.assertEqual(
            formatted_qualifying_awards(report),
            ['Winner - 1988 Pulitzer Prize - Fiction'],
        )

    def test_review_is_excluded(self):
        report = AwardLookupReport(
            assessments=(
                _assessment(_result(), QualificationDecision.REVIEW),
            ),
            failures=(),
        )
        self.assertEqual(formatted_qualifying_awards(report), [])

    def test_does_not_qualify_is_excluded(self):
        report = AwardLookupReport(
            assessments=(
                _assessment(
                    _result(status='Longlisted', award_name='Booker Prize'),
                    QualificationDecision.DOES_NOT_QUALIFY,
                ),
            ),
            failures=(),
        )
        self.assertEqual(formatted_qualifying_awards(report), [])

    def test_source_failures_are_not_writeback_values(self):
        report = AwardLookupReport(
            assessments=(),
            failures=(
                SourceFailure(
                    source_name='Nebula Awards',
                    error_type='TimeoutError',
                    message='timed out',
                ),
            ),
        )
        self.assertEqual(formatted_qualifying_awards(report), [])

    def test_only_qualifies_from_mixed_report(self):
        qualifies = _result()
        review = _result(
            work_title='The Fifth Season',
            work_author='N.K. Jemisin',
            award_name='Nebula Award',
            award_year=2015,
            category='Best Novel',
            status='Nominated',
            source_name='Nebula Awards',
        )
        rejected = _result(
            work_title='Other',
            work_author='Author',
            award_name='Booker Prize',
            award_year=2026,
            category=None,
            status='Longlisted',
            source_name='Booker Prize',
        )
        report = AwardLookupReport(
            assessments=(
                _assessment(review, QualificationDecision.REVIEW),
                _assessment(qualifies, QualificationDecision.QUALIFIES),
                _assessment(rejected, QualificationDecision.DOES_NOT_QUALIFY),
            ),
            failures=(
                SourceFailure('Pulitzer Prizes', 'URLError', 'network down'),
            ),
        )
        self.assertEqual(
            formatted_qualifying_awards(report),
            ['Winner - 1988 Pulitzer Prize - Fiction'],
        )

    def test_configured_template_is_honored(self):
        report = AwardLookupReport(
            assessments=(_assessment(_result()),),
            failures=(),
        )
        self.assertEqual(
            formatted_qualifying_awards(
                report,
                template='<award> (<year>): <placement>',
            ),
            ['Pulitzer Prize (1988): Winner'],
        )

    def test_missing_value_markers_are_unchanged(self):
        result = _result(award_year=None, category=None)
        report = AwardLookupReport(
            assessments=(_assessment(result),),
            failures=(),
        )
        formatted = formatted_qualifying_awards(report)
        self.assertEqual(
            formatted,
            [format_award_result(result, DEFAULT_AWARD_OUTPUT_TEMPLATE)],
        )
        self.assertEqual(
            formatted,
            ['Winner - <year missing> Pulitzer Prize - <category missing>'],
        )


class AppendAwardValuesTests(unittest.TestCase):
    def test_existing_values_are_preserved(self):
        self.assertEqual(
            append_award_values(
                ['Winner - 1988 Pulitzer Prize - Fiction'],
                [],
            ),
            ['Winner - 1988 Pulitzer Prize - Fiction'],
        )

    def test_new_unique_values_append_in_order(self):
        self.assertEqual(
            append_award_values(
                ['Winner - 1988 Pulitzer Prize - Fiction'],
                [
                    'Winner - 2016 Hugo Award - Best Novel',
                    'Winner - 1965 Nebula Award - Best Novel',
                ],
            ),
            [
                'Winner - 1988 Pulitzer Prize - Fiction',
                'Winner - 2016 Hugo Award - Best Novel',
                'Winner - 1965 Nebula Award - Best Novel',
            ],
        )

    def test_exact_duplicate_is_not_appended(self):
        existing = ['Winner - 1988 Pulitzer Prize - Fiction']
        self.assertEqual(
            append_award_values(
                existing,
                ['Winner - 1988 Pulitzer Prize - Fiction'],
            ),
            existing,
        )

    def test_case_difference_is_not_appended(self):
        self.assertEqual(
            append_award_values(
                ['Winner - 1988 Pulitzer Prize - Fiction'],
                ['winner - 1988 pulitzer prize - fiction'],
            ),
            ['Winner - 1988 Pulitzer Prize - Fiction'],
        )

    def test_whitespace_difference_is_not_appended(self):
        self.assertEqual(
            append_award_values(
                ['Winner - 1988 Pulitzer Prize - Fiction'],
                ['  Winner - 1988 Pulitzer Prize - Fiction  '],
            ),
            ['Winner - 1988 Pulitzer Prize - Fiction'],
        )

    def test_duplicates_within_new_values_are_removed(self):
        self.assertEqual(
            append_award_values(
                [],
                [
                    'Winner - 1988 Pulitzer Prize - Fiction',
                    'Winner - 1988 Pulitzer Prize - Fiction',
                    'winner - 1988 pulitzer prize - fiction',
                ],
            ),
            ['Winner - 1988 Pulitzer Prize - Fiction'],
        )

    def test_existing_spelling_wins(self):
        self.assertEqual(
            append_award_values(
                ['Winner - 1988 Pulitzer Prize - Fiction'],
                ['WINNER - 1988 PULITZER PRIZE - FICTION'],
            ),
            ['Winner - 1988 Pulitzer Prize - Fiction'],
        )

    def test_empty_existing_list_works(self):
        self.assertEqual(
            append_award_values(
                [],
                ['Winner - 1988 Pulitzer Prize - Fiction'],
            ),
            ['Winner - 1988 Pulitzer Prize - Fiction'],
        )


class ReplaceAwardValuesTests(unittest.TestCase):
    def test_existing_values_are_ignored(self):
        new = ['Winner - 2016 Hugo Award - Best Novel']
        self.assertEqual(replace_award_values(new), new)

    def test_duplicate_new_values_are_removed(self):
        self.assertEqual(
            replace_award_values(
                [
                    'Winner - 1988 Pulitzer Prize - Fiction',
                    '  Winner - 1988 Pulitzer Prize - Fiction  ',
                    'winner - 1988 pulitzer prize - fiction',
                    'Winner - 2016 Hugo Award - Best Novel',
                ],
            ),
            [
                'Winner - 1988 Pulitzer Prize - Fiction',
                'Winner - 2016 Hugo Award - Best Novel',
            ],
        )

    def test_ordering_is_preserved(self):
        self.assertEqual(
            replace_award_values(
                [
                    'Winner - 2016 Hugo Award - Best Novel',
                    'Winner - 1988 Pulitzer Prize - Fiction',
                ],
            ),
            [
                'Winner - 2016 Hugo Award - Best Novel',
                'Winner - 1988 Pulitzer Prize - Fiction',
            ],
        )

    def test_unique_helper_keeps_first_spelling(self):
        self.assertEqual(
            unique_award_values(
                [
                    'Winner - 1988 Pulitzer Prize - Fiction',
                    'WINNER - 1988 PULITZER PRIZE - FICTION',
                ],
            ),
            ['Winner - 1988 Pulitzer Prize - Fiction'],
        )


class CommaPartitionTests(unittest.TestCase):
    def test_comma_value_is_rejected(self):
        partition = partition_comma_unsafe_award_values(
            ['Winner - 1988 Foo, Bar Prize - Fiction'],
        )
        self.assertEqual(partition.safe, [])
        self.assertEqual(
            partition.rejected_for_comma,
            ['Winner - 1988 Foo, Bar Prize - Fiction'],
        )

    def test_safe_values_remain_when_another_is_rejected(self):
        partition = partition_comma_unsafe_award_values(
            [
                'Winner - 1988 Pulitzer Prize - Fiction',
                'Winner - 1988 Foo, Bar Prize - Fiction',
                'Winner - 2016 Hugo Award - Best Novel',
            ],
        )
        self.assertEqual(
            partition.safe,
            [
                'Winner - 1988 Pulitzer Prize - Fiction',
                'Winner - 2016 Hugo Award - Best Novel',
            ],
        )
        self.assertEqual(
            partition.rejected_for_comma,
            ['Winner - 1988 Foo, Bar Prize - Fiction'],
        )

    def test_rejected_award_text_is_preserved(self):
        original = 'Finalist - 1991 The Things They Carried, Expanded - Fiction'
        partition = partition_comma_unsafe_award_values([original])
        self.assertEqual(partition.rejected_for_comma, [original])
        self.assertIs(partition.rejected_for_comma[0], original)


class PrepareAppendAwardValuesTests(unittest.TestCase):
    def test_existing_comma_value_is_preserved(self):
        existing = ['Winner - 1988 Foo, Bar Prize - Fiction']
        prepared = prepare_append_award_values(
            existing,
            ['Winner - 2016 Hugo Award - Best Novel'],
        )
        self.assertEqual(
            prepared.values,
            [
                'Winner - 1988 Foo, Bar Prize - Fiction',
                'Winner - 2016 Hugo Award - Best Novel',
            ],
        )
        self.assertEqual(prepared.rejected_for_comma, [])

    def test_existing_duplicates_remain_duplicated(self):
        existing = [
            'Winner - 1988 Pulitzer Prize - Fiction',
            'Winner - 1988 Pulitzer Prize - Fiction',
        ]
        prepared = prepare_append_award_values(
            existing,
            ['Winner - 2016 Hugo Award - Best Novel'],
        )
        self.assertEqual(
            prepared.values,
            [
                'Winner - 1988 Pulitzer Prize - Fiction',
                'Winner - 1988 Pulitzer Prize - Fiction',
                'Winner - 2016 Hugo Award - Best Novel',
            ],
        )

    def test_existing_whitespace_and_case_are_not_normalized(self):
        existing = ['  WINNER - 1988 Pulitzer Prize - Fiction  ']
        prepared = prepare_append_award_values(
            existing,
            ['Winner - 2016 Hugo Award - Best Novel'],
        )
        self.assertEqual(prepared.values[0], existing[0])
        self.assertEqual(
            prepared.values,
            [
                '  WINNER - 1988 Pulitzer Prize - Fiction  ',
                'Winner - 2016 Hugo Award - Best Novel',
            ],
        )

    def test_new_comma_value_is_rejected_and_not_appended(self):
        existing = ['Winner - 1988 Pulitzer Prize - Fiction']
        prepared = prepare_append_award_values(
            existing,
            ['Winner - 1988 Foo, Bar Prize - Fiction'],
        )
        self.assertEqual(prepared.values, existing)
        self.assertEqual(
            prepared.rejected_for_comma,
            ['Winner - 1988 Foo, Bar Prize - Fiction'],
        )

    def test_safe_new_values_append_when_another_is_rejected(self):
        prepared = prepare_append_award_values(
            ['Winner - 1988 Pulitzer Prize - Fiction'],
            [
                'Winner - 1988 Foo, Bar Prize - Fiction',
                'Winner - 2016 Hugo Award - Best Novel',
            ],
        )
        self.assertEqual(
            prepared.values,
            [
                'Winner - 1988 Pulitzer Prize - Fiction',
                'Winner - 2016 Hugo Award - Best Novel',
            ],
        )
        self.assertEqual(
            prepared.rejected_for_comma,
            ['Winner - 1988 Foo, Bar Prize - Fiction'],
        )

    def test_new_duplicate_of_existing_is_not_appended(self):
        existing = ['Winner - 1988 Pulitzer Prize - Fiction']
        prepared = prepare_append_award_values(
            existing,
            ['winner - 1988 pulitzer prize - fiction'],
        )
        self.assertEqual(prepared.values, existing)
        self.assertEqual(prepared.rejected_for_comma, [])

    def test_duplicate_safe_new_values_are_not_appended_twice(self):
        prepared = prepare_append_award_values(
            [],
            [
                'Winner - 2016 Hugo Award - Best Novel',
                '  Winner - 2016 Hugo Award - Best Novel  ',
                'winner - 2016 hugo award - best novel',
            ],
        )
        self.assertEqual(
            prepared.values,
            ['Winner - 2016 Hugo Award - Best Novel'],
        )
        self.assertEqual(prepared.rejected_for_comma, [])


class PrepareReplaceAwardValuesTests(unittest.TestCase):
    def test_comma_containing_new_value_is_rejected(self):
        prepared = prepare_replace_award_values(
            [
                'Winner - 1988 Foo, Bar Prize - Fiction',
                'Winner - 2016 Hugo Award - Best Novel',
            ],
        )
        self.assertEqual(
            prepared.values,
            ['Winner - 2016 Hugo Award - Best Novel'],
        )
        self.assertEqual(
            prepared.rejected_for_comma,
            ['Winner - 1988 Foo, Bar Prize - Fiction'],
        )

    def test_safe_values_remain(self):
        prepared = prepare_replace_award_values(
            [
                'Winner - 1988 Pulitzer Prize - Fiction',
                'Winner - 2016 Hugo Award - Best Novel',
            ],
        )
        self.assertEqual(
            prepared.values,
            [
                'Winner - 1988 Pulitzer Prize - Fiction',
                'Winner - 2016 Hugo Award - Best Novel',
            ],
        )
        self.assertEqual(prepared.rejected_for_comma, [])

    def test_duplicate_safe_new_values_are_deduplicated(self):
        prepared = prepare_replace_award_values(
            [
                'Winner - 1988 Pulitzer Prize - Fiction',
                'winner - 1988 pulitzer prize - fiction',
                'Winner - 2016 Hugo Award - Best Novel',
            ],
        )
        self.assertEqual(
            prepared.values,
            [
                'Winner - 1988 Pulitzer Prize - Fiction',
                'Winner - 2016 Hugo Award - Best Novel',
            ],
        )


if __name__ == '__main__':
    unittest.main()
