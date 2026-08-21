"""Offline coverage for engine source isolation via a substitute source list."""

from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

from awards.engine import (
    LookupProgress,
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
        lock = threading.Lock()

        def _ok(title: str, author: str, series=None):
            with lock:
                attempted.append('ok')
            return []

        def _boom(title: str, author: str, series=None):
            with lock:
                attempted.append('boom')
            raise RuntimeError('network down')

        def _also_ok(title: str, author: str, series=None):
            with lock:
                attempted.append('also_ok')
            return []

        sources = (
            _source('one', 'Source One', _ok),
            _source('two', 'Source Two', _boom),
            _source('three', 'Source Three', _also_ok),
        )
        report = _lookup_awards_from_sources('Beloved', 'Toni Morrison', sources)
        self.assertEqual(set(attempted), {'ok', 'boom', 'also_ok'})
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


class EngineConcurrencyTests(unittest.TestCase):
    def test_independent_sources_run_concurrently(self):
        barrier = threading.Barrier(3, timeout=2)

        def _one(title: str, author: str, series=None):
            barrier.wait()
            return [_result(source_name='One')]

        def _two(title: str, author: str, series=None):
            barrier.wait()
            return [_result(source_name='Two', award_name='Nebula Award')]

        def _three(title: str, author: str, series=None):
            barrier.wait()
            return [_result(source_name='Three', award_name='Hugo Award')]

        sources = (
            _source('one', 'Source One', _one),
            _source('two', 'Source Two', _two),
            _source('three', 'Source Three', _three),
        )
        report = _lookup_awards_from_sources('Beloved', 'Toni Morrison', sources)
        self.assertEqual(
            [item.result.source_name for item in report.assessments],
            ['One', 'Two', 'Three'],
        )

    def test_assessments_keep_registry_order_when_finish_order_differs(self):
        release_slow = threading.Event()
        started_slow = threading.Event()

        def _slow(title: str, author: str, series=None):
            started_slow.set()
            if not release_slow.wait(timeout=2):
                raise TimeoutError('slow source was not released')
            return [_result(source_name='Slow Source', work_title='Slow')]

        def _fast_b(title: str, author: str, series=None):
            return [_result(source_name='Fast B', work_title='B')]

        def _fast_c(title: str, author: str, series=None):
            return [_result(source_name='Fast C', work_title='C')]

        sources = (
            _source('a', 'Source A', _slow),
            _source('b', 'Source B', _fast_b),
            _source('c', 'Source C', _fast_c),
        )
        result_box = {}

        def _lookup():
            result_box['report'] = _lookup_awards_from_sources(
                'Beloved', 'Toni Morrison', sources
            )

        thread = threading.Thread(target=_lookup)
        thread.start()
        self.assertTrue(started_slow.wait(timeout=2))
        release_slow.set()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        report = result_box['report']
        self.assertEqual(
            [item.result.source_name for item in report.assessments],
            ['Slow Source', 'Fast B', 'Fast C'],
        )

    def test_failure_keeps_source_identity_and_other_results(self):
        def _ok(title: str, author: str, series=None):
            return [_result(source_name='OK Awards')]

        def _boom(title: str, author: str, series=None):
            raise RuntimeError('timeout')

        def _also(title: str, author: str, series=None):
            return [_result(source_name='Also Awards', work_title='Jazz')]

        sources = (
            _source('ok', 'OK Awards', _ok),
            _source('bad', 'Bad Awards', _boom),
            _source('also', 'Also Awards', _also),
        )
        report = _lookup_awards_from_sources('Beloved', 'Toni Morrison', sources)
        self.assertEqual(
            [item.result.source_name for item in report.assessments],
            ['OK Awards', 'Also Awards'],
        )
        self.assertEqual(len(report.failures), 1)
        self.assertEqual(report.failures[0].source_name, 'Bad Awards')
        self.assertEqual(report.failures[0].error_type, 'RuntimeError')

    def test_progress_callback_counts_each_source_once(self):
        events: list[LookupProgress] = []

        def _a(title: str, author: str, series=None):
            return [_result(source_name='Alpha')]

        def _b(title: str, author: str, series=None):
            raise ValueError('nope')

        def _c(title: str, author: str, series=None):
            return []

        sources = (
            _source('a', 'Alpha Awards', _a),
            _source('b', 'Beta Awards', _b),
            _source('c', 'Gamma Awards', _c),
        )
        report = _lookup_awards_from_sources(
            'Beloved',
            'Toni Morrison',
            sources,
            on_progress=events.append,
        )
        self.assertEqual(len(report.assessments), 1)
        self.assertEqual(len(report.failures), 1)
        self.assertEqual(events[0], LookupProgress(0, 3, None))
        completions = events[1:]
        self.assertEqual(len(completions), 3)
        self.assertEqual(
            [item.completed_sources for item in completions],
            [1, 2, 3],
        )
        self.assertTrue(all(item.total_sources == 3 for item in completions))
        self.assertEqual(
            sorted(item.source_name for item in completions),
            ['Alpha Awards', 'Beta Awards', 'Gamma Awards'],
        )


if __name__ == '__main__':
    unittest.main()
