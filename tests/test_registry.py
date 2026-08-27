"""Offline coverage for the award-policy registry.

Pulitzer Fiction and Newbery Honor are the registered policies. A Booker
Prize name in a test is an unsupported fixture, not plugin support for that
award.
"""

from __future__ import annotations

import unittest

from awards.model import AwardResult
from awards.registry import (
    AWARD_POLICIES,
    NEWBERY_POLICY,
    PULITZER_FICTION_POLICY,
    find_award_policy,
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


def _newbery_result(**overrides) -> AwardResult:
    values = {
        'work_title': 'The Tombs of Atuan',
        'work_author': 'Ursula K. LeGuin',
        'award_name': 'Newbery Medal',
        'award_year': 1972,
        'category': "Children's Literature",
        'status': 'Honor',
        'rank': None,
        'source_name': 'John Newbery Medal',
        'source_url': 'https://www.ala.org/winner/tombs-atuan',
    }
    values.update(overrides)
    return AwardResult(**values)


class AwardPolicyRegistryTests(unittest.TestCase):
    def test_registered_policies_are_pulitzer_then_newbery(self):
        self.assertEqual(
            AWARD_POLICIES,
            (PULITZER_FICTION_POLICY, NEWBERY_POLICY),
        )

    def test_pulitzer_fiction_result_finds_the_active_policy(self):
        winner = _result()
        finalist = _result(status='Finalist')
        self.assertIs(find_award_policy(winner), PULITZER_FICTION_POLICY)
        self.assertIs(find_award_policy(finalist), PULITZER_FICTION_POLICY)

    def test_newbery_result_finds_the_honor_policy(self):
        honor = _newbery_result()
        winner = _newbery_result(status='Winner', award_year=1963)
        self.assertIs(find_award_policy(honor), NEWBERY_POLICY)
        self.assertIs(find_award_policy(winner), NEWBERY_POLICY)

    def test_newbery_policy_does_not_match_other_award_or_category(self):
        self.assertIsNone(
            find_award_policy(
                _newbery_result(award_name='Caldecott Medal')
            )
        )
        self.assertIsNone(
            find_award_policy(_newbery_result(category='Fiction'))
        )
        self.assertIsNone(
            find_award_policy(
                _result(
                    award_name='Hugo Award',
                    category='Best Novel',
                    status='Honor',
                )
            )
        )

    def test_unsupported_booker_result_has_no_registry_policy(self):
        # Negative fixture: Booker is not a registered policy.
        result = _result(
            work_title='Other',
            work_author='Author',
            award_name='Booker Prize',
            award_year=2026,
            category=None,
            status='Longlisted',
            source_name='Booker Prize',
            source_url=None,
        )
        self.assertIsNone(find_award_policy(result))


if __name__ == '__main__':
    unittest.main()
