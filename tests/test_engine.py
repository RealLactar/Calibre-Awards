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
from awards.qualifier import QualificationDecision
from awards.source_registry import AWARD_SOURCES, AwardSource


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


class EngineEnabledSourceFilterTests(unittest.TestCase):
    def test_omitted_or_none_runs_every_registered_source(self):
        attempted: list[str] = []
        lock = threading.Lock()

        def _one(title: str, author: str, series=None):
            with lock:
                attempted.append('one')
            return []

        def _two(title: str, author: str, series=None):
            with lock:
                attempted.append('two')
            return []

        sources = (
            _source('one', 'Source One', _one),
            _source('two', 'Source Two', _two),
        )
        with patch('awards.engine.AWARD_SOURCES', sources):
            omitted = lookup_awards('Beloved', 'Toni Morrison')
            none_keys = lookup_awards(
                'Beloved',
                'Toni Morrison',
                enabled_source_keys=None,
            )
        self.assertEqual(attempted.count('one'), 2)
        self.assertEqual(attempted.count('two'), 2)
        self.assertEqual(omitted.assessments, ())
        self.assertEqual(omitted.failures, ())
        self.assertEqual(none_keys.assessments, ())
        self.assertEqual(none_keys.failures, ())

    def test_excluded_lookup_is_never_invoked(self):
        attempted: list[str] = []

        def _ok(title: str, author: str, series=None):
            attempted.append('ok')
            return [_result(source_name='OK Awards')]

        def _boom(title: str, author: str, series=None):
            attempted.append('boom')
            raise RuntimeError('should not run')

        sources = (
            _source('ok', 'OK Awards', _ok),
            _source('bad', 'Bad Awards', _boom),
        )
        with patch('awards.engine.AWARD_SOURCES', sources):
            report = lookup_awards(
                'Beloved',
                'Toni Morrison',
                enabled_source_keys=('ok',),
            )
        self.assertEqual(attempted, ['ok'])
        self.assertEqual(len(report.assessments), 1)
        self.assertEqual(report.failures, ())

    def test_only_one_enabled_source_runs(self):
        attempted: list[str] = []

        def _pulitzer(title: str, author: str, series=None):
            attempted.append('pulitzer')
            return []

        def _nobel(title: str, author: str, series=None):
            attempted.append('nobel')
            return [_result(source_name='NobelPrize.org')]

        sources = (
            _source('pulitzer', 'Pulitzer Prizes', _pulitzer),
            _source('nebula', 'Nebula Awards', lambda *a, **k: attempted.append('nebula') or []),
            _source('nobel', 'NobelPrize.org', _nobel),
        )
        with patch('awards.engine.AWARD_SOURCES', sources):
            report = lookup_awards(
                'Beloved',
                'Toni Morrison',
                enabled_source_keys=('nobel',),
            )
        self.assertEqual(attempted, ['nobel'])
        self.assertEqual(
            [item.result.source_name for item in report.assessments],
            ['NobelPrize.org'],
        )

    def test_empty_enabled_keys_run_zero_sources(self):
        attempted: list[str] = []

        def _ok(title: str, author: str, series=None):
            attempted.append('ok')
            return [_result()]

        sources = (_source('ok', 'OK Awards', _ok),)
        with patch('awards.engine.AWARD_SOURCES', sources):
            report = lookup_awards(
                'Beloved',
                'Toni Morrison',
                enabled_source_keys=(),
            )
        self.assertEqual(attempted, [])
        self.assertEqual(report.assessments, ())
        self.assertEqual(report.failures, ())

    def test_unknown_enabled_key_is_ignored(self):
        attempted: list[str] = []

        def _nobel(title: str, author: str, series=None):
            attempted.append('nobel')
            return []

        sources = (_source('nobel', 'NobelPrize.org', _nobel),)
        with patch('awards.engine.AWARD_SOURCES', sources):
            report = lookup_awards(
                'Beloved',
                'Toni Morrison',
                enabled_source_keys=('nobel', 'removed_old_source'),
            )
        self.assertEqual(attempted, ['nobel'])
        self.assertEqual(report.failures, ())

    def test_caller_order_does_not_reorder_registry_execution(self):
        attempted: list[str] = []
        lock = threading.Lock()

        def _hugo(title: str, author: str, series=None):
            with lock:
                attempted.append('hugo')
            return [_result(source_name='Hugo Awards')]

        def _nobel(title: str, author: str, series=None):
            with lock:
                attempted.append('nobel')
            return [_result(source_name='NobelPrize.org')]

        sources = (
            _source('pulitzer', 'Pulitzer Prizes', lambda *a, **k: []),
            _source('hugo', 'Hugo Awards', _hugo),
            _source('nobel', 'NobelPrize.org', _nobel),
        )
        with patch('awards.engine.AWARD_SOURCES', sources):
            report = lookup_awards(
                'Beloved',
                'Toni Morrison',
                enabled_source_keys=('nobel', 'hugo'),
            )
        self.assertEqual(set(attempted), {'hugo', 'nobel'})
        self.assertEqual(
            [item.result.source_name for item in report.assessments],
            ['Hugo Awards', 'NobelPrize.org'],
        )

    def test_excluded_raising_source_creates_no_failure(self):
        def _boom(title: str, author: str, series=None):
            raise RuntimeError('timeout')

        def _ok(title: str, author: str, series=None):
            return [_result(source_name='OK Awards')]

        sources = (
            _source('bad', 'Bad Awards', _boom),
            _source('ok', 'OK Awards', _ok),
        )
        with patch('awards.engine.AWARD_SOURCES', sources):
            report = lookup_awards(
                'Beloved',
                'Toni Morrison',
                enabled_source_keys=('ok',),
            )
        self.assertEqual(report.failures, ())
        self.assertEqual(len(report.assessments), 1)

    def test_enabled_raising_source_still_becomes_failure(self):
        def _boom(title: str, author: str, series=None):
            raise ValueError('bad payload')

        sources = (_source('broken', 'Broken Awards', _boom),)
        with patch('awards.engine.AWARD_SOURCES', sources):
            report = lookup_awards(
                'Beloved',
                'Toni Morrison',
                enabled_source_keys=('broken',),
            )
        self.assertEqual(len(report.failures), 1)
        self.assertEqual(report.failures[0].source_name, 'Broken Awards')
        self.assertEqual(report.failures[0].error_type, 'ValueError')

    def test_progress_total_uses_filtered_source_count(self):
        events: list[LookupProgress] = []

        def _nobel(title: str, author: str, series=None):
            return []

        def _unused(title: str, author: str, series=None):
            raise AssertionError('disabled source was submitted')

        sources = (
            _source('pulitzer', 'Pulitzer Prizes', _unused),
            _source('nobel', 'NobelPrize.org', _nobel),
        )
        with patch('awards.engine.AWARD_SOURCES', sources):
            lookup_awards(
                'Beloved',
                'Toni Morrison',
                on_progress=events.append,
                enabled_source_keys=('nobel',),
            )
        self.assertEqual(events[0], LookupProgress(0, 1, None))
        self.assertEqual(len(events), 2)
        self.assertTrue(all(item.total_sources == 1 for item in events))
        self.assertEqual(events[1].source_name, 'NobelPrize.org')

    def test_progress_total_for_two_enabled_sources(self):
        events: list[LookupProgress] = []

        def _ok(title: str, author: str, series=None):
            return []

        sources = (
            _source('pulitzer', 'Pulitzer Prizes', _ok),
            _source('hugo', 'Hugo Awards', _ok),
            _source('nobel', 'NobelPrize.org', _ok),
        )
        with patch('awards.engine.AWARD_SOURCES', sources):
            lookup_awards(
                'Beloved',
                'Toni Morrison',
                on_progress=events.append,
                enabled_source_keys=('nobel', 'hugo'),
            )
        self.assertTrue(all(item.total_sources == 2 for item in events))
        self.assertEqual(events[0].completed_sources, 0)
        self.assertEqual(
            sorted(item.source_name for item in events[1:]),
            ['Hugo Awards', 'NobelPrize.org'],
        )


class EngineRankCutoffTests(unittest.TestCase):
    def test_omitted_cutoff_rejects_rank_six(self):
        def _ranked(title: str, author: str, series=None):
            return [_result(status='Finalist', rank=6, award_name='Hugo Award')]

        sources = (_source('hugo', 'Hugo Awards', _ranked),)
        report = _lookup_awards_from_sources('Beloved', 'Toni Morrison', sources)
        self.assertEqual(len(report.assessments), 1)
        self.assertEqual(report.assessments[0].result.rank, 6)
        self.assertEqual(
            report.assessments[0].qualification.decision,
            QualificationDecision.DOES_NOT_QUALIFY,
        )

    def test_public_lookup_awards_threads_cutoff(self):
        def _ranked(title: str, author: str, series=None):
            return [_result(status='Finalist', rank=6, award_name='Hugo Award')]

        stub = _source('hugo', 'Hugo Awards', _ranked)
        with patch('awards.engine.AWARD_SOURCES', (stub,)):
            omitted = lookup_awards('Beloved', 'Toni Morrison')
            raised = lookup_awards(
                'Beloved',
                'Toni Morrison',
                max_qualifying_rank=10,
            )
        self.assertEqual(
            omitted.assessments[0].qualification.decision,
            QualificationDecision.DOES_NOT_QUALIFY,
        )
        self.assertEqual(
            raised.assessments[0].qualification.decision,
            QualificationDecision.QUALIFIES,
        )

    def test_cutoff_ten_qualifies_rank_six(self):
        def _ranked(title: str, author: str, series=None):
            return [_result(status='Finalist', rank=6, award_name='Hugo Award')]

        sources = (_source('hugo', 'Hugo Awards', _ranked),)
        report = _lookup_awards_from_sources(
            'Beloved',
            'Toni Morrison',
            sources,
            max_qualifying_rank=10,
        )
        self.assertEqual(
            report.assessments[0].qualification.decision,
            QualificationDecision.QUALIFIES,
        )

    def test_custom_cutoff_does_not_alter_unranked_winner(self):
        def _winner(title: str, author: str, series=None):
            return [_result(status='Winner', rank=None)]

        sources = (_source('ok', 'OK Awards', _winner),)
        report = _lookup_awards_from_sources(
            'Beloved',
            'Toni Morrison',
            sources,
            max_qualifying_rank=1,
        )
        self.assertEqual(
            report.assessments[0].qualification.decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            report.assessments[0].qualification.reason,
            'Status indicates a win without an established ordinal rank.',
        )


class EngineNewberyParticipationTests(unittest.TestCase):
    def _newbery_result(self, **overrides) -> AwardResult:
        values = {
            'work_title': 'The Tombs of Atuan',
            'work_author': 'Ursula K. LeGuin',
            'award_name': 'Newbery Medal',
            'award_year': 1972,
            'category': "Children's Literature",
            'status': 'Honor',
            'rank': None,
            'source_name': 'John Newbery Medal',
            'source_url': 'https://www.ala.org/winner/tombs-atuan',
            'identity_kind': 'work',
        }
        values.update(overrides)
        return AwardResult(**values)

    def test_newbery_honor_result_qualifies_in_lookup_report(self):
        def _newbery(title: str, author: str, series=None):
            return [self._newbery_result()]

        sources = (
            _source('newbery', 'John Newbery Medal', _newbery),
        )
        report = _lookup_awards_from_sources(
            'The Tombs of Atuan',
            'Ursula K. Le Guin',
            sources,
        )
        self.assertEqual(len(report.assessments), 1)
        assessment = report.assessments[0]
        self.assertEqual(assessment.result.source_name, 'John Newbery Medal')
        self.assertEqual(assessment.result.status, 'Honor')
        self.assertIsNone(assessment.result.rank)
        self.assertEqual(
            assessment.qualification.decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(report.failures, ())

    def test_newbery_failure_does_not_suppress_other_source_results(self):
        def _pulitzer(title: str, author: str, series=None):
            return [_result()]

        def _newbery(title: str, author: str, series=None):
            raise RuntimeError('ala archive unavailable')

        def _nobel(title: str, author: str, series=None):
            return [_result(source_name='NobelPrize.org', award_name='Nobel Prize')]

        sources = (
            _source('pulitzer', 'Pulitzer Prizes', _pulitzer),
            _source('newbery', 'John Newbery Medal', _newbery),
            _source('nobel', 'NobelPrize.org', _nobel),
        )
        report = _lookup_awards_from_sources(
            'Beloved',
            'Toni Morrison',
            sources,
        )
        self.assertEqual(
            [item.result.source_name for item in report.assessments],
            ['Pulitzer Prizes', 'NobelPrize.org'],
        )
        self.assertEqual(len(report.failures), 1)
        failure = report.failures[0]
        self.assertEqual(failure.source_name, 'John Newbery Medal')
        self.assertEqual(failure.error_type, 'RuntimeError')
        self.assertEqual(failure.message, 'ala archive unavailable')

    def test_registered_newbery_is_scheduled_and_keeps_registry_order(self):
        attempted: list[str] = []
        lock = threading.Lock()

        def _lookup_for(key: str):
            def _lookup(title: str, author: str, series=None):
                with lock:
                    attempted.append(key)
                if key == 'newbery':
                    raise RuntimeError('ala archive unavailable')
                if key == 'pulitzer':
                    return [_result()]
                return []

            return _lookup

        stubs = tuple(
            AwardSource(
                key=source.key,
                display_name=source.display_name,
                lookup=_lookup_for(source.key),
            )
            for source in AWARD_SOURCES
        )
        self.assertEqual(stubs[-1].key, 'newbery')
        with patch('awards.engine.AWARD_SOURCES', stubs):
            report = lookup_awards('Beloved', 'Toni Morrison')
        self.assertEqual(
            set(attempted),
            {source.key for source in AWARD_SOURCES},
        )
        self.assertEqual(
            [item.result.source_name for item in report.assessments],
            ['Pulitzer Prizes'],
        )
        self.assertEqual(len(report.failures), 1)
        self.assertEqual(report.failures[0].source_name, 'John Newbery Medal')


if __name__ == '__main__':
    unittest.main()
