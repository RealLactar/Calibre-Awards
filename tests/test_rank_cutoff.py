"""Offline coverage for persisted max_qualifying_rank normalization.

Clean integer strings such as "10" are accepted for JSONConfig tolerance.
Out-of-range values fall back to 5; they are not clamped to 1 or 100.
"""

from __future__ import annotations

import unittest

from awards.rank_cutoff import (
    DEFAULT_MAX_QUALIFYING_RANK,
    MAX_MAX_QUALIFYING_RANK,
    MIN_MAX_QUALIFYING_RANK,
    normalize_max_qualifying_rank,
)


class NormalizeMaxQualifyingRankTests(unittest.TestCase):
    def test_default_constant_is_five(self):
        self.assertEqual(DEFAULT_MAX_QUALIFYING_RANK, 5)
        self.assertEqual(MIN_MAX_QUALIFYING_RANK, 1)
        self.assertEqual(MAX_MAX_QUALIFYING_RANK, 100)

    def test_in_range_ints_are_unchanged(self):
        self.assertEqual(normalize_max_qualifying_rank(1), 1)
        self.assertEqual(normalize_max_qualifying_rank(5), 5)
        self.assertEqual(normalize_max_qualifying_rank(10), 10)
        self.assertEqual(normalize_max_qualifying_rank(100), 100)

    def test_none_falls_back_to_default(self):
        self.assertEqual(normalize_max_qualifying_rank(None), 5)

    def test_out_of_range_ints_fall_back_to_default(self):
        self.assertEqual(normalize_max_qualifying_rank(0), 5)
        self.assertEqual(normalize_max_qualifying_rank(-1), 5)
        self.assertEqual(normalize_max_qualifying_rank(101), 5)

    def test_bool_is_not_an_int(self):
        self.assertEqual(normalize_max_qualifying_rank(True), 5)
        self.assertEqual(normalize_max_qualifying_rank(False), 5)

    def test_garbage_string_falls_back_to_default(self):
        self.assertEqual(normalize_max_qualifying_rank('ten'), 5)
        self.assertEqual(normalize_max_qualifying_rank('10.0'), 5)
        self.assertEqual(normalize_max_qualifying_rank(''), 5)

    def test_clean_integer_strings_are_accepted(self):
        self.assertEqual(normalize_max_qualifying_rank('10'), 10)
        self.assertEqual(normalize_max_qualifying_rank('1'), 1)
        self.assertEqual(normalize_max_qualifying_rank('100'), 100)

    def test_out_of_range_integer_strings_fall_back_to_default(self):
        self.assertEqual(normalize_max_qualifying_rank('0'), 5)
        self.assertEqual(normalize_max_qualifying_rank('101'), 5)


if __name__ == '__main__':
    unittest.main()
