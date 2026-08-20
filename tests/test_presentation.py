"""Offline coverage for compact lookup/source identity display helpers."""

from __future__ import annotations

import unittest

from awards.presentation import (
    format_book_line,
    format_series_line,
    format_work_identity,
    lookup_has_series_award,
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


class SeriesDisplayLineTests(unittest.TestCase):
    def test_book_line_uses_title_pipe_author(self):
        self.assertEqual(
            format_book_line('Shards of Honor', 'Lois McMaster Bujold'),
            'Book: Shards of Honor | Lois McMaster Bujold',
        )

    def test_series_line_is_series_name_only(self):
        self.assertEqual(
            format_series_line('Vorkosigan Saga'),
            'Series: Vorkosigan Saga',
        )

    def test_blank_series_line_is_omitted(self):
        self.assertIsNone(format_series_line(''))
        self.assertIsNone(format_series_line('   '))

    def test_source_series_omitted_when_visibly_identical(self):
        self.assertIsNone(
            source_identity_if_different(
                'The Vorkosigan Saga',
                'Lois McMaster Bujold',
                'The Vorkosigan Saga',
                'Lois McMaster Bujold',
            )
        )

    def test_source_series_shown_when_calibre_spelling_differs(self):
        identity = source_identity_if_different(
            'Vorkosigan Saga',
            'Lois McMaster Bujold',
            'The Vorkosigan Saga',
            'Lois McMaster Bujold',
        )
        self.assertEqual(
            identity,
            'The Vorkosigan Saga | Lois McMaster Bujold',
        )

    def test_series_header_only_when_lookup_has_series_award(self):
        from types import SimpleNamespace

        series_item = SimpleNamespace(
            result=SimpleNamespace(identity_kind='series')
        )
        work_item = SimpleNamespace(
            result=SimpleNamespace(identity_kind='work')
        )
        self.assertTrue(
            lookup_has_series_award('Vorkosigan Saga', (series_item,))
        )
        self.assertFalse(lookup_has_series_award('', (series_item,)))
        self.assertFalse(lookup_has_series_award('Vorkosigan Saga', ()))
        self.assertFalse(
            lookup_has_series_award('Vorkosigan Saga', (work_item,))
        )


if __name__ == '__main__':
    unittest.main()
