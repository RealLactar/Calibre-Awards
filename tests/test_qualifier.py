"""Offline coverage for qualify_award_result policy-applicability order.

Applicability is validated before rank or Winner logic so a mismatched
policy cannot leak a qualification from another award family.
"""

from __future__ import annotations

import unittest

from awards.model import AwardResult
from awards.qualifier import QualificationDecision, qualify_award_result
from awards.registry import PULITZER_FICTION_POLICY


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


def _hugo_result(**overrides) -> AwardResult:
    values = {
        'work_title': 'The Graveyard Book',
        'work_author': 'Neil Gaiman',
        'award_name': 'Hugo Award',
        'award_year': 2009,
        'category': 'Best Novel',
        'status': 'Winner',
        'rank': None,
        'source_name': 'The Hugo Awards',
        'source_url': 'https://www.thehugoawards.org/hugo-history/2009-hugo-awards/',
    }
    values.update(overrides)
    return AwardResult(**values)


class QualifyAwardResultPolicyApplicabilityTests(unittest.TestCase):
    def test_mismatched_policy_rejects_winner(self):
        result = _hugo_result(status='Winner', rank=None)
        with self.assertRaises(ValueError) as caught:
            qualify_award_result(result, PULITZER_FICTION_POLICY)
        self.assertIn('does not apply', str(caught.exception))

    def test_mismatched_policy_rejects_ranked_result_that_would_qualify(self):
        result = _hugo_result(status='Finalist', rank=1)
        with self.assertRaises(ValueError) as caught:
            qualify_award_result(result, PULITZER_FICTION_POLICY)
        self.assertIn('does not apply', str(caught.exception))

    def test_mismatched_policy_rejects_review_status(self):
        result = _hugo_result(status='Nominee', rank=None)
        with self.assertRaises(ValueError) as caught:
            qualify_award_result(result, PULITZER_FICTION_POLICY)
        self.assertIn('does not apply', str(caught.exception))

    def test_matching_policy_still_qualifies_winner(self):
        result = _result(status='Winner', rank=None)
        assessment = qualify_award_result(result, PULITZER_FICTION_POLICY)
        self.assertEqual(assessment.decision, QualificationDecision.QUALIFIES)
        self.assertEqual(
            assessment.reason,
            'Status indicates a win without an established ordinal rank.',
        )

    def test_matching_policy_still_qualifies_rank_in_top_five(self):
        result = _result(status='Finalist', rank=1)
        assessment = qualify_award_result(result, PULITZER_FICTION_POLICY)
        self.assertEqual(assessment.decision, QualificationDecision.QUALIFIES)
        self.assertEqual(
            assessment.reason,
            'Source establishes an ordinal rank within the configured cutoff (5).',
        )

    def test_matching_policy_still_qualifies_pulitzer_finalist(self):
        result = _result(status='Finalist', rank=None)
        assessment = qualify_award_result(result, PULITZER_FICTION_POLICY)
        self.assertEqual(assessment.decision, QualificationDecision.QUALIFIES)

    def test_no_policy_winner_still_qualifies(self):
        result = _hugo_result(status='Winner', rank=None)
        assessment = qualify_award_result(result)
        self.assertEqual(assessment.decision, QualificationDecision.QUALIFIES)
        self.assertEqual(
            assessment.reason,
            'Status indicates a win without an established ordinal rank.',
        )

    def test_no_policy_rank_in_top_five_still_qualifies(self):
        result = _hugo_result(status='Finalist', rank=2)
        assessment = qualify_award_result(result, policy=None)
        self.assertEqual(assessment.decision, QualificationDecision.QUALIFIES)
        self.assertEqual(
            assessment.reason,
            'Source establishes an ordinal rank within the configured cutoff (5).',
        )

    def test_no_policy_rank_1_qualifies_by_default(self):
        result = _hugo_result(status='Finalist', rank=1)
        assessment = qualify_award_result(result)
        self.assertEqual(assessment.decision, QualificationDecision.QUALIFIES)
        self.assertEqual(
            assessment.reason,
            'Source establishes an ordinal rank within the configured cutoff (5).',
        )

    def test_no_policy_rank_5_qualifies_by_default(self):
        result = _hugo_result(status='Finalist', rank=5)
        assessment = qualify_award_result(result)
        self.assertEqual(assessment.decision, QualificationDecision.QUALIFIES)

    def test_no_policy_rank_above_five_still_does_not_qualify(self):
        result = _hugo_result(status='Finalist', rank=6)
        assessment = qualify_award_result(result, policy=None)
        self.assertEqual(
            assessment.decision,
            QualificationDecision.DOES_NOT_QUALIFY,
        )
        self.assertEqual(
            assessment.reason,
            'Source establishes an ordinal rank outside the configured cutoff (5).',
        )

    def test_no_policy_review_status_still_reviews(self):
        result = _hugo_result(status='Nominee', rank=None)
        assessment = qualify_award_result(result, policy=None)
        self.assertEqual(assessment.decision, QualificationDecision.REVIEW)


class QualifyAwardResultCutoffTests(unittest.TestCase):
    def test_cutoff_10_qualifies_rank_6_and_10(self):
        rank_6 = qualify_award_result(
            _hugo_result(status='Finalist', rank=6),
            max_qualifying_rank=10,
        )
        rank_10 = qualify_award_result(
            _hugo_result(status='Finalist', rank=10),
            max_qualifying_rank=10,
        )
        self.assertEqual(rank_6.decision, QualificationDecision.QUALIFIES)
        self.assertEqual(
            rank_6.reason,
            'Source establishes an ordinal rank within the configured cutoff (10).',
        )
        self.assertEqual(rank_10.decision, QualificationDecision.QUALIFIES)
        self.assertEqual(
            rank_10.reason,
            'Source establishes an ordinal rank within the configured cutoff (10).',
        )

    def test_cutoff_10_rejects_rank_11(self):
        assessment = qualify_award_result(
            _hugo_result(status='Finalist', rank=11),
            max_qualifying_rank=10,
        )
        self.assertEqual(
            assessment.decision,
            QualificationDecision.DOES_NOT_QUALIFY,
        )
        self.assertEqual(
            assessment.reason,
            'Source establishes an ordinal rank outside the configured cutoff (10).',
        )

    def test_cutoff_1_qualifies_rank_1_and_rejects_rank_2(self):
        rank_1 = qualify_award_result(
            _hugo_result(status='Finalist', rank=1),
            max_qualifying_rank=1,
        )
        rank_2 = qualify_award_result(
            _hugo_result(status='Finalist', rank=2),
            max_qualifying_rank=1,
        )
        self.assertEqual(rank_1.decision, QualificationDecision.QUALIFIES)
        self.assertEqual(
            rank_2.decision,
            QualificationDecision.DOES_NOT_QUALIFY,
        )

    def test_cutoff_1_does_not_change_unranked_winner(self):
        assessment = qualify_award_result(
            _hugo_result(status='Winner', rank=None),
            max_qualifying_rank=1,
        )
        self.assertEqual(assessment.decision, QualificationDecision.QUALIFIES)
        self.assertEqual(
            assessment.reason,
            'Status indicates a win without an established ordinal rank.',
        )

    def test_cutoff_1_does_not_change_unranked_pulitzer_finalist(self):
        assessment = qualify_award_result(
            _result(status='Finalist', rank=None),
            PULITZER_FICTION_POLICY,
            max_qualifying_rank=1,
        )
        self.assertEqual(assessment.decision, QualificationDecision.QUALIFIES)

    def test_invalid_cutoff_raises_value_error(self):
        result = _hugo_result(status='Finalist', rank=1)
        for cutoff in (0, 101, '5', True, None):
            with self.subTest(cutoff=cutoff):
                with self.assertRaises(ValueError):
                    qualify_award_result(result, max_qualifying_rank=cutoff)


class QualifyAwardResultIdentityConfirmationTests(unittest.TestCase):
    def test_identity_confirmation_does_not_change_qualification(self):
        note = (
            'Source lists the author as Allen Steele; '
            'Calibre lists Allen M. Steele.'
        )
        result = _hugo_result(
            work_title='Clarke County, Space',
            work_author='Allen Steele',
            status='19th place',
            rank=19,
            identity_confirmation_required=True,
            source_identity_note=note,
        )
        at_12 = qualify_award_result(result, max_qualifying_rank=12)
        at_20 = qualify_award_result(result, max_qualifying_rank=20)
        self.assertEqual(at_12.decision, QualificationDecision.DOES_NOT_QUALIFY)
        self.assertEqual(at_20.decision, QualificationDecision.QUALIFIES)
        self.assertIsNot(at_12.decision, QualificationDecision.REVIEW)
        self.assertIsNot(at_20.decision, QualificationDecision.REVIEW)
        self.assertIs(result.identity_confirmation_required, True)


if __name__ == '__main__':
    unittest.main()
