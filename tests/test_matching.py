"""Offline coverage for shared title-conjunction normalization."""

from __future__ import annotations

import unittest

from awards.matching import normalize_title_conjunctions


class TitleConjunctionTests(unittest.TestCase):
    def test_jonathan_strange_ampersand_equals_and(self):
        self.assertEqual(
            normalize_title_conjunctions('Jonathan Strange & Mr Norrell'),
            normalize_title_conjunctions('Jonathan Strange and Mr Norrell'),
        )

    def test_smith_and_jones(self):
        self.assertEqual(
            normalize_title_conjunctions('Smith & Jones'),
            normalize_title_conjunctions('Smith and Jones'),
        )
        self.assertEqual(
            normalize_title_conjunctions('Smith & Jones'),
            'Smith and Jones',
        )

    def test_embedded_ampersand_r_and_b_unchanged(self):
        self.assertEqual(normalize_title_conjunctions('R&B'), 'R&B')

    def test_embedded_ampersand_at_and_t_unchanged(self):
        self.assertEqual(normalize_title_conjunctions('AT&T'), 'AT&T')


if __name__ == '__main__':
    unittest.main()
