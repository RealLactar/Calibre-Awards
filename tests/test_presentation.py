"""Offline coverage for compact lookup/source identity display helpers."""

from __future__ import annotations

import unittest

from awards.presentation import (
    CITED_WORK_SCOPE_NOTE,
    format_author_award_caption,
    format_book_line,
    format_cited_work_caption,
    format_series_line,
    format_work_identity,
    is_cited_work_result,
    lookup_has_series_award,
    match_row_scope_lines,
    result_identity_kind,
    source_author_identity_if_different,
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


class AuthorIdentityPresentationTests(unittest.TestCase):
    def test_author_kind_is_distinct_from_work_and_series(self):
        from types import SimpleNamespace

        author = SimpleNamespace(identity_kind='author')
        work = SimpleNamespace(identity_kind='work')
        series = SimpleNamespace(identity_kind='series')
        self.assertEqual(result_identity_kind(author), 'author')
        self.assertEqual(result_identity_kind(work), 'work')
        self.assertEqual(result_identity_kind(series), 'series')
        self.assertEqual(
            result_identity_kind(SimpleNamespace()),
            'work',
        )

    def test_author_award_does_not_trigger_series_header(self):
        from types import SimpleNamespace

        author_item = SimpleNamespace(
            result=SimpleNamespace(identity_kind='author')
        )
        self.assertFalse(
            lookup_has_series_award('Vorkosigan Saga', (author_item,))
        )

    def test_author_caption_uses_awarded_author_name(self):
        self.assertEqual(
            format_author_award_caption('Ernest Hemingway'),
            'AUTHOR AWARD - Awarded to Ernest Hemingway, '
            'not specifically to this book.',
        )

    def test_source_author_omitted_when_spelling_matches(self):
        self.assertIsNone(
            source_author_identity_if_different(
                'Ernest Hemingway',
                'Ernest Hemingway',
            )
        )

    def test_source_author_shown_when_spelling_differs(self):
        self.assertEqual(
            source_author_identity_if_different(
                'Hemingway, Ernest',
                'Ernest Hemingway',
            ),
            'Ernest Hemingway',
        )

    def test_author_row_does_not_compare_book_title_to_work_title(self):
        from types import SimpleNamespace

        result = SimpleNamespace(
            identity_kind='author',
            work_title='Ernest Hemingway',
            work_author='Ernest Hemingway',
        )
        lines = match_row_scope_lines(
            result,
            'For Whom the Bell Tolls',
            'Ernest Hemingway',
        )
        self.assertEqual(
            lines,
            (
                'AUTHOR AWARD - Awarded to Ernest Hemingway, '
                'not specifically to this book.',
            ),
        )
        self.assertFalse(any(line.startswith('Source:') for line in lines))
        self.assertFalse(any('For Whom the Bell Tolls' in line for line in lines))

    def test_author_row_can_show_official_author_spelling(self):
        from types import SimpleNamespace

        result = SimpleNamespace(
            identity_kind='author',
            work_title='Gabriel García Márquez',
            work_author='Gabriel García Márquez',
        )
        lines = match_row_scope_lines(
            result,
            'One Hundred Years of Solitude',
            'Gabriel Garcia Marquez',
        )
        self.assertEqual(
            lines,
            (
                'AUTHOR AWARD - Awarded to Gabriel García Márquez, '
                'not specifically to this book.',
                'Source author: Gabriel García Márquez',
            ),
        )

    def test_work_row_scope_is_unchanged(self):
        from types import SimpleNamespace

        same = SimpleNamespace(
            identity_kind='work',
            work_title='Beloved',
            work_author='Toni Morrison',
        )
        self.assertEqual(
            match_row_scope_lines(same, 'Beloved', 'Toni Morrison'),
            (),
        )
        different = SimpleNamespace(
            identity_kind='work',
            work_title='Jonathan Strange & Mr Norrell',
            work_author='Susanna Clarke',
        )
        self.assertEqual(
            match_row_scope_lines(
                different,
                'Jonathan Strange and Mr Norrell',
                'Susanna Clarke',
            ),
            (
                'Source: Jonathan Strange & Mr Norrell | Susanna Clarke',
            ),
        )
        self.assertFalse(
            any('AUTHOR AWARD' in line for line in match_row_scope_lines(
                different,
                'Jonathan Strange and Mr Norrell',
                'Susanna Clarke',
            ))
        )

    def test_series_row_scope_is_unchanged(self):
        from types import SimpleNamespace

        result = SimpleNamespace(
            identity_kind='series',
            work_title='The Vorkosigan Saga',
            work_author='Lois McMaster Bujold',
        )
        self.assertEqual(
            match_row_scope_lines(
                result,
                'Shards of Honor',
                'Lois McMaster Bujold',
                'The Vorkosigan Saga',
            ),
            (),
        )
        self.assertEqual(
            match_row_scope_lines(
                result,
                'Shards of Honor',
                'Lois McMaster Bujold',
                'Vorkosigan Saga',
            ),
            (
                'Source series: The Vorkosigan Saga | Lois McMaster Bujold',
            ),
        )
        self.assertFalse(
            any('AUTHOR AWARD' in line for line in match_row_scope_lines(
                result,
                'Shards of Honor',
                'Lois McMaster Bujold',
                'Vorkosigan Saga',
            ))
        )


class CitedWorkPresentationTests(unittest.TestCase):
    def test_cited_work_caption_is_quiet_work_award_line(self):
        self.assertEqual(
            format_cited_work_caption(),
            'WORK AWARD - This work was specifically cited in the Nobel Prize '
            'motivation.',
        )

    def test_cited_work_row_shows_explanatory_caption(self):
        from types import SimpleNamespace

        result = SimpleNamespace(
            identity_kind='work',
            work_title='The Old Man and the Sea',
            work_author='Ernest Hemingway',
            notes=CITED_WORK_SCOPE_NOTE,
        )
        self.assertTrue(is_cited_work_result(result))
        self.assertEqual(
            match_row_scope_lines(
                result,
                'The Old Man and the Sea',
                'Ernest Hemingway',
            ),
            (
                'WORK AWARD - This work was specifically cited in the Nobel '
                'Prize motivation.',
            ),
        )

    def test_ordinary_work_row_does_not_gain_work_award_caption(self):
        from types import SimpleNamespace

        result = SimpleNamespace(
            identity_kind='work',
            work_title='Beloved',
            work_author='Toni Morrison',
            notes=None,
        )
        self.assertFalse(is_cited_work_result(result))
        self.assertEqual(
            match_row_scope_lines(result, 'Beloved', 'Toni Morrison'),
            (),
        )

    def test_declined_author_notes_do_not_create_work_award_caption(self):
        from types import SimpleNamespace

        result = SimpleNamespace(
            identity_kind='author',
            work_title='Jean-Paul Sartre',
            work_author='Jean-Paul Sartre',
            notes='Nobel Prize status: declined.',
        )
        lines = match_row_scope_lines(result, 'Nausea', 'Jean-Paul Sartre')
        self.assertFalse(is_cited_work_result(result))
        self.assertEqual(
            lines,
            (
                'AUTHOR AWARD - Awarded to Jean-Paul Sartre, '
                'not specifically to this book.',
            ),
        )
        self.assertFalse(any('WORK AWARD' in line for line in lines))

    def test_restricted_author_notes_do_not_create_work_award_caption(self):
        from types import SimpleNamespace

        result = SimpleNamespace(
            identity_kind='author',
            work_title='Boris Pasternak',
            work_author='Boris Pasternak',
            notes='Nobel Prize status: restricted.',
        )
        lines = match_row_scope_lines(
            result,
            'Doctor Zhivago',
            'Boris Pasternak',
        )
        self.assertFalse(any('WORK AWARD' in line for line in lines))
        self.assertTrue(any(line.startswith('AUTHOR AWARD') for line in lines))

    def test_declined_notes_on_a_work_result_are_not_a_cited_caption(self):
        from types import SimpleNamespace

        result = SimpleNamespace(
            identity_kind='work',
            work_title='Beloved',
            work_author='Toni Morrison',
            notes='Nobel Prize status: declined.',
        )
        self.assertFalse(is_cited_work_result(result))
        self.assertEqual(
            match_row_scope_lines(result, 'Beloved', 'Toni Morrison'),
            (),
        )


if __name__ == '__main__':
    unittest.main()
