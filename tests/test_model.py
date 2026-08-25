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

    def test_accepts_author_identity_kind(self):
        result = _result(
            work_title='Ernest Hemingway',
            work_author='Ernest Hemingway',
            award_name='Nobel Prize',
            award_year=1954,
            category='Literature',
            identity_kind='author',
        )
        self.assertEqual(result.identity_kind, 'author')
        self.assertEqual(result.work_title, 'Ernest Hemingway')
        self.assertEqual(result.work_author, 'Ernest Hemingway')

    def test_invalid_identity_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            _result(identity_kind='volume')
        with self.assertRaises(ValueError):
            _result(identity_kind='')
        with self.assertRaises(ValueError):
            _result(identity_kind=' work')
        with self.assertRaises(ValueError):
            _result(identity_kind=' author ')


class AwardResultCitedWorkFlagTests(unittest.TestCase):
    def test_default_is_specifically_cited_work_is_false(self):
        result = _result()
        self.assertIs(result.is_specifically_cited_work, False)

    def test_work_with_cited_flag_true_is_accepted(self):
        result = _result(
            work_title='The Old Man and the Sea',
            work_author='Ernest Hemingway',
            award_name='Nobel Prize',
            award_year=1954,
            category='Literature',
            identity_kind='work',
            is_specifically_cited_work=True,
        )
        self.assertEqual(result.identity_kind, 'work')
        self.assertIs(result.is_specifically_cited_work, True)

    def test_author_with_cited_flag_true_is_rejected(self):
        with self.assertRaises(ValueError):
            _result(
                work_title='Ernest Hemingway',
                work_author='Ernest Hemingway',
                award_name='Nobel Prize',
                identity_kind='author',
                is_specifically_cited_work=True,
            )

    def test_series_with_cited_flag_true_is_rejected(self):
        with self.assertRaises(ValueError):
            _result(
                work_title='The Vorkosigan Saga',
                work_author='Lois McMaster Bujold',
                award_name='Hugo Award',
                identity_kind='series',
                is_specifically_cited_work=True,
            )

    def test_non_bool_cited_flag_is_rejected(self):
        with self.assertRaises(ValueError):
            _result(is_specifically_cited_work='yes')
        with self.assertRaises(ValueError):
            _result(is_specifically_cited_work=1)


if __name__ == '__main__':
    unittest.main()
