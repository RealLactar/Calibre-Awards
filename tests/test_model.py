"""Unit tests for AwardResult identity_kind."""

from __future__ import annotations

import unittest

from awards.model import AwardResult


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


class AwardResultIdentityKindTests(unittest.TestCase):
    def test_default_identity_kind_is_work(self):
        result = _result()
        self.assertEqual(result.identity_kind, 'work')

    def test_accepts_series_identity_kind(self):
        result = _result(
            work_title='The Vorkosigan Saga',
            work_author='Lois McMaster Bujold',
            award_name='Hugo Award',
            award_year=2017,
            category='Best Series',
            identity_kind='series',
        )
        self.assertEqual(result.identity_kind, 'series')

    def test_invalid_identity_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            _result(identity_kind='volume')
        with self.assertRaises(ValueError):
            _result(identity_kind='')
        with self.assertRaises(ValueError):
            _result(identity_kind=' work')


if __name__ == '__main__':
    unittest.main()
