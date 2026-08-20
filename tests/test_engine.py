"""Offline coverage for engine source isolation via a substitute source list."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from awards.engine import (
    _lookup_awards_from_sources,
    lookup_awards,
)
from awards.model import AwardResult
from awards.source_registry import AwardSource


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


def _source(key: str, display_name: str, lookup) -> AwardSource:
    return AwardSource(key=key, display_name=display_name, lookup=lookup)


class EngineSourceIsolationTests(unittest.TestCase):
    def test_all_registered_sources_are_attempted(self):
        attempted: list[str] = []

        def _ok(title: str, author: str, series=None):
            attempted.append('ok')
            return []

        def _boom(title: str, author: str, series=None):
            attempted.append('boom')
            raise RuntimeError('network down')

        def _also_ok(title: str, author: str, series=None):
            attempted.append('also_ok')
            return []

        sources = (
            _source('one', 'Source One', _ok),
            _source('two', 'Source Two', _boom),
            _source('three', 'Source Three', _also_ok),
        )
        report = _lookup_awards_from_sources('Beloved', 'Toni Morrison', sources)
        self.assertEqual(attempted, ['ok', 'boom', 'also_ok'])
        self.assertEqual(len(report.failures), 1)
        self.assertEqual(report.failures[0].source_name, 'Source Two')
        self.assertEqual(report.assessments, ())

    def test_source_exception_becomes_failure_with_display_name(self):
        def _boom(title: str, author: str, series=None):
            raise ValueError('bad payload')

        sources = (_source('broken', 'Broken Awards', _boom),)
        report = _lookup_awards_from_sources('Beloved', 'Toni Morrison', sources)
        self.assertEqual(len(report.failures), 1)
        failure = report.failures[0]
        self.assertEqual(failure.source_name, 'Broken Awards')
        self.assertEqual(failure.error_type, 'ValueError')
        self.assertEqual(failure.message, 'bad payload')
        self.assertEqual(report.assessments, ())

    def test_successful_result_survives_another_source_failure(self):
        def _ok(title: str, author: str, series=None):
            return [_result()]

        def _boom(title: str, author: str, series=None):
            raise RuntimeError('timeout')

        sources = (
            _source('ok', 'OK Awards', _ok),
            _source('bad', 'Bad Awards', _boom),
        )
        report = _lookup_awards_from_sources('Beloved', 'Toni Morrison', sources)
        self.assertEqual(len(report.assessments), 1)
        self.assertEqual(report.assessments[0].result.work_title, 'Beloved')
        self.assertEqual(len(report.failures), 1)
        self.assertEqual(report.failures[0].source_name, 'Bad Awards')

    def test_successful_empty_results_do_not_create_failures(self):
        def _empty(title: str, author: str, series=None):
            return []

        sources = (
            _source('one', 'Source One', _empty),
            _source('two', 'Source Two', _empty),
        )
        report = _lookup_awards_from_sources('Beloved', 'Toni Morrison', sources)
        self.assertEqual(report.assessments, ())
        self.assertEqual(report.failures, ())

    def test_public_lookup_awards_rejects_empty_title_or_author(self):
        with self.assertRaises(ValueError):
            lookup_awards('  ', 'Toni Morrison')
        with self.assertRaises(ValueError):
            lookup_awards('Beloved', '  ')

    def test_optional_series_is_passed_to_sources(self):
        seen: list[tuple[str, str, str | None]] = []

        def _capture(title: str, author: str, series=None):
            seen.append((title, author, series))
            return []

        sources = (_source('hugo', 'Hugo Awards', _capture),)
        report = _lookup_awards_from_sources(
            'Shards of Honor',
            'Lois McMaster Bujold',
            sources,
            series='Vorkosigan Saga',
        )
        self.assertEqual(report.assessments, ())
        self.assertEqual(
            seen,
            [
                (
                    'Shards of Honor',
                    'Lois McMaster Bujold',
                    'Vorkosigan Saga',
                )
            ],
        )

    def test_no_series_passes_none_and_is_not_an_error(self):
        seen: list[str | None] = []

        def _capture(title: str, author: str, series=None):
            seen.append(series)
            return [_result()]

        sources = (_source('ok', 'OK Awards', _capture),)
        report = _lookup_awards_from_sources(
            'Beloved', 'Toni Morrison', sources
        )
        self.assertEqual(seen, [None])
        self.assertEqual(len(report.assessments), 1)

    def test_public_lookup_awards_treats_blank_series_as_absent(self):
        seen: list[str | None] = []

        def _capture(title: str, author: str, series=None):
            seen.append(series)
            return []

        stub = _source('stub', 'Stub Awards', _capture)
        with patch('awards.engine.AWARD_SOURCES', (stub,)):
            lookup_awards('Beloved', 'Toni Morrison', series='  ')
        self.assertEqual(seen, [None])

    def test_non_hugo_stub_ignores_series_without_behavior_change(self):
        def _ok(title: str, author: str, series=None):
            return [_result()]

        sources = (_source('pulitzer', 'Pulitzer Prizes', _ok),)
        report = _lookup_awards_from_sources(
            'Beloved',
            'Toni Morrison',
            sources,
            series='Vorkosigan Saga',
        )
        self.assertEqual(len(report.assessments), 1)
        self.assertEqual(report.assessments[0].result.work_title, 'Beloved')
        self.assertEqual(report.assessments[0].result.identity_kind, 'work')


if __name__ == '__main__':
    unittest.main()
