"""Offline coverage for the award-policy registry.

Pulitzer Fiction is the only active registered policy. A Booker Prize
name in a test is an unsupported fixture, not plugin support for that award.
"""

from __future__ import annotations

import unittest

from awards.model import AwardResult
from awards.registry import (
    AWARD_POLICIES,
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


class AwardPolicyRegistryTests(unittest.TestCase):
    def test_pulitzer_fiction_policy_is_the_only_registered_policy(self):
        self.assertEqual(AWARD_POLICIES, (PULITZER_FICTION_POLICY,))

    def test_pulitzer_fiction_result_finds_the_active_policy(self):
        winner = _result()
        finalist = _result(status='Finalist')
        self.assertIs(find_award_policy(winner), PULITZER_FICTION_POLICY)
        self.assertIs(find_award_policy(finalist), PULITZER_FICTION_POLICY)

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
