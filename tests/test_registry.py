"""Offline coverage for the award-policy registry.

Pulitzer Fiction, Newbery Honor, and Booker Shortlisted are the registered
policies.
"""

from __future__ import annotations

import unittest

from awards.model import AwardResult
from awards.registry import (
    AWARD_POLICIES,
    BOOKER_POLICY,
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


def _booker_result(**overrides) -> AwardResult:
    values = {
        'work_title': 'Midnight’s Children',
        'work_author': 'Salman Rushdie',
        'award_name': 'Booker Prize',
        'award_year': 1981,
        'category': 'Fiction',
        'status': 'Winner',
        'rank': None,
        'source_name': 'The Booker Prize',
        'source_url': 'https://thebookerprizes.com/the-booker-library/books/midnights-children',
    }
    values.update(overrides)
    return AwardResult(**values)


class AwardPolicyRegistryTests(unittest.TestCase):
    def test_registered_policies_are_pulitzer_newbery_then_booker(self):
        self.assertEqual(
            AWARD_POLICIES,
            (PULITZER_FICTION_POLICY, NEWBERY_POLICY, BOOKER_POLICY),
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

    def test_booker_result_finds_the_shortlisted_policy(self):
        winner = _booker_result()
        shortlisted = _booker_result(
            work_title='Empire of the Sun',
            work_author='J. G. Ballard',
            award_year=1984,
            status='Shortlisted',
            source_url=(
                'https://thebookerprizes.com/the-booker-library/books/'
                'empire-of-the-sun'
            ),
        )
        self.assertIs(find_award_policy(winner), BOOKER_POLICY)
        self.assertIs(find_award_policy(shortlisted), BOOKER_POLICY)

    def test_booker_policy_does_not_match_other_award_or_category(self):
        self.assertIsNone(
            find_award_policy(_booker_result(award_name='International Booker Prize'))
        )
        self.assertIsNone(find_award_policy(_booker_result(category='Poetry')))
        self.assertIsNone(find_award_policy(_booker_result(category=None)))

    def test_longlisted_booker_name_without_fiction_category_has_no_policy(self):
        result = _result(
            work_title='Other',
            work_author='Author',
            award_name='Booker Prize',
            award_year=2026,
            category=None,
            status='Longlisted',
            source_name='The Booker Prize',
            source_url=None,
        )
        self.assertIsNone(find_award_policy(result))
        self.assertNotIn('longlisted', BOOKER_POLICY.qualifying_statuses)


if __name__ == '__main__':
    unittest.main()
