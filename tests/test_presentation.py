"""Offline coverage for compact lookup/source identity display helpers."""

from __future__ import annotations

import unittest

from awards.presentation import (
    format_work_identity,
    source_identity_if_different,
)


class WorkIdentityFormatTests(unittest.TestCase):
    def test_compact_title_pipe_author(self):
        self.assertEqual(
            format_work_identity('Every Heart a Doorway', 'Seanan McGuire'),
            'Every Heart a Doorway | Seanan McGuire',
        )

    def test_format_strips_surrounding_whitespace(self):
        self.assertEqual(
            format_work_identity('  Dune  ', '  Frank Herbert  '),
            'Dune | Frank Herbert',
        )


class SourceIdentityDisplayTests(unittest.TestCase):
    def test_exact_same_title_and_author_returns_none(self):
        self.assertIsNone(
            source_identity_if_different(
                'Every Heart a Doorway',
                'Seanan McGuire',
                'Every Heart a Doorway',
                'Seanan McGuire',
            )
        )

    def test_and_versus_ampersand_is_a_visible_difference(self):
        identity = source_identity_if_different(
            'Jonathan Strange and Mr Norrell',
            'Susanna Clarke',
            'Jonathan Strange & Mr Norrell',
            'Susanna Clarke',
        )
        self.assertEqual(
            identity,
            'Jonathan Strange & Mr Norrell | Susanna Clarke',
        )

    def test_author_only_visible_difference_is_returned(self):
        identity = source_identity_if_different(
            'Dune',
            'Frank Herbert',
            'Dune',
            'Frank Herbert (and others)',
        )
        self.assertEqual(identity, 'Dune | Frank Herbert (and others)')

    def test_leading_and_trailing_whitespace_alone_is_not_a_difference(self):
        self.assertIsNone(
            source_identity_if_different(
                '  Dune  ',
                '  Frank Herbert  ',
                'Dune',
                'Frank Herbert',
            )
        )
        self.assertIsNone(
            source_identity_if_different(
                'Dune',
                'Frank Herbert',
                ' Dune',
                'Frank Herbert ',
            )
        )

    def test_case_difference_remains_visible(self):
        identity = source_identity_if_different(
            'Dune',
            'Frank Herbert',
            'dune',
            'Frank Herbert',
        )
        self.assertEqual(identity, 'dune | Frank Herbert')

    def test_punctuation_difference_remains_visible(self):
        identity = source_identity_if_different(
            'The Three Body Problem',
            'Cixin Liu',
            'The Three-Body Problem',
            'Cixin Liu',
        )
        self.assertEqual(identity, 'The Three-Body Problem | Cixin Liu')


if __name__ == '__main__':
    unittest.main()
