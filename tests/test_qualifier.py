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
            'Source establishes an ordinal rank within the top five.',
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
            'Source establishes an ordinal rank within the top five.',
        )

    def test_no_policy_rank_above_five_still_does_not_qualify(self):
        result = _hugo_result(status='Finalist', rank=6)
        assessment = qualify_award_result(result, policy=None)
        self.assertEqual(
            assessment.decision,
            QualificationDecision.DOES_NOT_QUALIFY,
        )

    def test_no_policy_review_status_still_reviews(self):
        result = _hugo_result(status='Nominee', rank=None)
        assessment = qualify_award_result(result, policy=None)
        self.assertEqual(assessment.decision, QualificationDecision.REVIEW)


if __name__ == '__main__':
    unittest.main()
