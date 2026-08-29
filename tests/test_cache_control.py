"""Offline coverage for per-source cache refresh (disk + RAM, no network)."""

from __future__ import annotations

import hashlib
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards import cache_control
from awards.cache_control import (
    refresh_award_source_cache,
    run_source_cache_refresh_if_confirmed,
    runtime_reset_source_keys,
    source_cache_refresh_failure_text,
    source_cache_refresh_status_text,
)
from awards.source_info import SOURCE_INFOS
from awards.source_registry import AWARD_SOURCES
from awards.sources import booker, hugo, locus, nebula, newbery, nobel, pulitzer, world_fantasy

_UTC = timezone.utc
_AUTHOR_URL = 'https://www.sfadb.com/Dan_Simmons'
_ANNUAL_URL = 'https://www.sfadb.com/Locus_Awards_1990'


def _utc():
    return datetime(2026, 1, 1, tzinfo=_UTC)


def _save_archive(source_key, *, source_urls=None):
    cache.save_source_cache(
        source_key,
        1,
        records=[{'title': source_key, 'year': 2020}],
        source_urls=source_urls or [f'https://example.test/{source_key}'],
        coverage={'source': source_key},
        ttl_seconds=3600,
        generated_at=_utc(),
    )


def _save_locus_entry(entry_kind, entry_key):
    cache.save_cache_entry(
        'locus',
        entry_kind,
        entry_key,
        1,
        records=[{'url': entry_key}],
        source_urls=[entry_key],
        coverage={'kind': entry_kind},
        ttl_seconds=3600,
        generated_at=_utc(),
    )


def _entry_path(cache_dir: Path, source_key: str, entry_kind: str, entry_key: str) -> Path:
    digest = hashlib.sha256(entry_key.encode('utf-8')).hexdigest()
    return cache_dir / source_key / entry_kind / f'{digest}.json'


def _fail_unlink_for(*filenames):
    blocked = frozenset(filenames)
    original = Path.unlink

    def _unlink(self, *args, **kwargs):
        if self.name in blocked:
            raise OSError('permission denied')
        return original(self, *args, **kwargs)

    return _unlink


class CacheControlTestCase(unittest.TestCase):
    def setUp(self):
        cache._reset_runtime_state()
        booker._reset_runtime_state()
        hugo._reset_runtime_state()
        locus._reset_runtime_state()
        nebula._reset_runtime_state()
        newbery._reset_runtime_state()
        nobel._reset_runtime_state()
        pulitzer._reset_runtime_state()
        world_fantasy._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        booker._reset_runtime_state()
        hugo._reset_runtime_state()
        locus._reset_runtime_state()
        nebula._reset_runtime_state()
        newbery._reset_runtime_state()
        nobel._reset_runtime_state()
        pulitzer._reset_runtime_state()
        world_fantasy._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()


class RegistryResetAlignmentTests(CacheControlTestCase):
    def test_runtime_reset_keys_match_registered_sources(self):
        registered = {source.key for source in AWARD_SOURCES}
        infos = {info.key for info in SOURCE_INFOS}
        resets = set(runtime_reset_source_keys())
        self.assertEqual(resets, registered)
        self.assertEqual(resets, infos)


class ArchiveSourceRefreshTests(CacheControlTestCase):
    def test_refresh_archive_source_removes_only_that_persistent_cache(self):
        _save_archive('nebula')
        _save_archive('hugo')
        nebula._pages_cache['best-novel'] = (('https://example.test/n', 'html'),)
        nebula._records_cache['best-novel'] = ()
        hugo._archive_records_cache = ()
        self.assertTrue(refresh_award_source_cache('nebula'))
        self.assertFalse((self.cache_dir / 'nebula.json').exists())
        self.assertIsNone(cache.load_source_cache('nebula', 1))
        self.assertEqual(nebula._pages_cache, {})
        self.assertEqual(nebula._records_cache, {})
        self.assertTrue((self.cache_dir / 'hugo.json').is_file())
        self.assertIsNotNone(cache.load_source_cache('hugo', 1))
        self.assertEqual(hugo._archive_records_cache, ())

    def test_sibling_archive_caches_survive(self):
        for key in (
            'pulitzer',
            'nebula',
            'hugo',
            'world_fantasy',
            'nobel',
            'booker',
            'newbery',
        ):
            _save_archive(key)
        refresh_award_source_cache('hugo')
        self.assertFalse((self.cache_dir / 'hugo.json').exists())
        for key in ('pulitzer', 'nebula', 'world_fantasy', 'nobel', 'booker', 'newbery'):
            self.assertTrue((self.cache_dir / f'{key}.json').is_file(), key)
            self.assertIsNotNone(cache.load_source_cache(key, 1), key)


class LocusRefreshTests(CacheControlTestCase):
    def test_refresh_locus_clears_author_and_annual_keyed_cache_and_ram(self):
        _save_archive('hugo')
        _save_locus_entry('authors', _AUTHOR_URL)
        _save_locus_entry('annuals', _ANNUAL_URL)
        locus._author_page_cache[_AUTHOR_URL] = 'author-ram'
        locus._annual_page_cache[_ANNUAL_URL] = ()
        hugo._archive_records_cache = ()
        self.assertTrue(refresh_award_source_cache('locus'))
        self.assertFalse(_entry_path(self.cache_dir, 'locus', 'authors', _AUTHOR_URL).exists())
        self.assertFalse(_entry_path(self.cache_dir, 'locus', 'annuals', _ANNUAL_URL).exists())
        self.assertIsNone(
            cache.load_cache_entry('locus', 'authors', _AUTHOR_URL, 1)
        )
        self.assertIsNone(
            cache.load_cache_entry('locus', 'annuals', _ANNUAL_URL, 1)
        )
        self.assertEqual(locus._author_page_cache, {})
        self.assertEqual(locus._annual_page_cache, {})
        self.assertTrue((self.cache_dir / 'hugo.json').is_file())
        self.assertEqual(hugo._archive_records_cache, ())

    def test_non_locus_caches_survive_locus_refresh(self):
        _save_archive('nebula')
        _save_archive('newbery')
        _save_locus_entry('authors', _AUTHOR_URL)
        refresh_award_source_cache('locus')
        self.assertTrue((self.cache_dir / 'nebula.json').is_file())
        self.assertTrue((self.cache_dir / 'newbery.json').is_file())
        self.assertFalse(_entry_path(self.cache_dir, 'locus', 'authors', _AUTHOR_URL).exists())

    def test_one_locked_locus_file_is_persistent_failure_and_resets_ram(self):
        _save_locus_entry('authors', _AUTHOR_URL)
        _save_locus_entry('annuals', _ANNUAL_URL)
        locus._author_page_cache[_AUTHOR_URL] = 'author-ram'
        locus._annual_page_cache[_ANNUAL_URL] = ()
        blocked = _entry_path(
            self.cache_dir, 'locus', 'authors', _AUTHOR_URL
        ).name
        with patch.object(Path, 'unlink', _fail_unlink_for(blocked)):
            self.assertFalse(refresh_award_source_cache('locus'))
        self.assertEqual(locus._author_page_cache, {})
        self.assertEqual(locus._annual_page_cache, {})
        self.assertTrue(
            _entry_path(self.cache_dir, 'locus', 'authors', _AUTHOR_URL).is_file()
        )
        self.assertFalse(
            _entry_path(self.cache_dir, 'locus', 'annuals', _ANNUAL_URL).exists()
        )


class NewberyRefreshTests(CacheControlTestCase):
    def test_refresh_newbery_clears_listing_and_detail_author_ram(self):
        _save_archive('newbery')
        _save_archive('nebula')
        newbery._listing_records_cache = ()
        newbery._detail_author_cache['https://www.ala.org/winner/x'] = 'Madeleine L\'Engle'
        nebula._pages_cache['best-novel'] = (('https://example.test/n', 'html'),)
        refresh_award_source_cache('newbery')
        self.assertFalse((self.cache_dir / 'newbery.json').exists())
        self.assertIsNone(newbery._listing_records_cache)
        self.assertEqual(newbery._detail_author_cache, {})
        self.assertTrue((self.cache_dir / 'nebula.json').is_file())
        self.assertIn('best-novel', nebula._pages_cache)


class RuntimeResetDispatchTests(CacheControlTestCase):
    def test_refresh_calls_only_matching_runtime_reset(self):
        called = []

        def _tracker(name):
            def _reset():
                called.append(name)

            return _reset

        tracked = {
            key: _tracker(key) for key in cache_control._SOURCE_RUNTIME_RESETS
        }
        with patch.dict(cache_control._SOURCE_RUNTIME_RESETS, tracked, clear=True):
            refresh_award_source_cache('nebula')
        self.assertEqual(called, ['nebula'])

    def test_other_runtime_resets_are_not_called(self):
        called = []

        def _tracker(name):
            def _reset():
                called.append(name)

            return _reset

        tracked = {
            key: _tracker(key) for key in cache_control._SOURCE_RUNTIME_RESETS
        }
        with patch.dict(cache_control._SOURCE_RUNTIME_RESETS, tracked, clear=True):
            refresh_award_source_cache('hugo')
        self.assertEqual(called, ['hugo'])
        self.assertNotIn('nebula', called)
        self.assertNotIn('locus', called)


class UnknownSourceKeyTests(CacheControlTestCase):
    def test_unknown_key_raises_and_does_not_invalidate(self):
        _save_archive('nebula')
        stray = self.cache_dir / 'foobar.json'
        stray.write_text('{}', encoding='utf-8')
        with patch.object(cache, 'invalidate_source_cache') as invalidate:
            with self.assertRaises(ValueError):
                refresh_award_source_cache('foobar')
            invalidate.assert_not_called()
        self.assertTrue(stray.is_file())
        self.assertTrue((self.cache_dir / 'nebula.json').is_file())

    def test_unknown_key_does_not_reset_registered_runtime_state(self):
        nebula._pages_cache['best-novel'] = (('https://example.test/n', 'html'),)
        hugo._archive_records_cache = ()
        with self.assertRaises(ValueError):
            refresh_award_source_cache('not_a_source')
        self.assertIn('best-novel', nebula._pages_cache)
        self.assertEqual(hugo._archive_records_cache, ())

    def test_non_string_and_blank_keys_are_rejected(self):
        _save_archive('nebula')
        for bad in ('', '   ', None, 12, 'Locus Awards'):
            with self.assertRaises(ValueError):
                refresh_award_source_cache(bad)
        self.assertTrue((self.cache_dir / 'nebula.json').is_file())


class IdempotentAndMissingDirTests(CacheControlTestCase):
    def test_repeated_refresh_of_same_source_is_harmless(self):
        _save_archive('nebula')
        nebula._pages_cache['best-novel'] = (('https://example.test/n', 'html'),)
        refresh_award_source_cache('nebula')
        refresh_award_source_cache('nebula')
        self.assertFalse((self.cache_dir / 'nebula.json').exists())
        self.assertEqual(nebula._pages_cache, {})

    def test_missing_cache_directory_is_harmless(self):
        cache.set_cache_directory(self.cache_dir / 'missing')
        nebula._pages_cache['best-novel'] = (('https://example.test/n', 'html'),)
        self.assertTrue(refresh_award_source_cache('nebula'))
        self.assertEqual(nebula._pages_cache, {})

    def test_unconfigured_cache_still_resets_ram(self):
        cache.set_cache_directory(None)
        nebula._pages_cache['best-novel'] = (('https://example.test/n', 'html'),)
        self.assertTrue(refresh_award_source_cache('nebula'))
        self.assertEqual(nebula._pages_cache, {})

    def test_missing_source_file_is_success(self):
        nebula._pages_cache['best-novel'] = (('https://example.test/n', 'html'),)
        self.assertTrue(refresh_award_source_cache('nebula'))
        self.assertEqual(nebula._pages_cache, {})
        self.assertFalse((self.cache_dir / 'nebula.json').exists())

    def test_unrelated_files_in_cache_directory_survive(self):
        _save_archive('nebula')
        notes = self.cache_dir / 'notes.txt'
        notes.write_text('keep me', encoding='utf-8')
        leftover = self.cache_dir / 'nebula.partial.json.tmp'
        leftover.write_text('tmp', encoding='utf-8')
        self.assertTrue(refresh_award_source_cache('nebula'))
        self.assertFalse((self.cache_dir / 'nebula.json').exists())
        self.assertTrue(notes.is_file())
        self.assertEqual(notes.read_text(encoding='utf-8'), 'keep me')
        self.assertTrue(leftover.is_file())

    def test_ram_reset_runs_when_persistent_deletion_fails(self):
        _save_archive('nebula')
        nebula._pages_cache['best-novel'] = (('https://example.test/n', 'html'),)
        with patch.object(Path, 'unlink', _fail_unlink_for('nebula.json')):
            self.assertFalse(refresh_award_source_cache('nebula'))
        self.assertEqual(nebula._pages_cache, {})
        self.assertTrue((self.cache_dir / 'nebula.json').is_file())

    def test_ram_reset_runs_when_disk_invalidation_raises(self):
        nebula._pages_cache['best-novel'] = (('https://example.test/n', 'html'),)
        with patch.object(
            cache,
            'invalidate_source_cache',
            side_effect=OSError('disk busy'),
        ):
            with self.assertRaises(OSError):
                refresh_award_source_cache('nebula')
        self.assertEqual(nebula._pages_cache, {})


class NoNetworkTests(CacheControlTestCase):
    def test_refresh_performs_no_source_lookup_or_http(self):
        _save_archive('nebula')
        _save_locus_entry('authors', _AUTHOR_URL)
        with (
            patch('awards.engine.lookup_awards') as engine_lookup,
            patch.object(nebula, 'lookup') as nebula_lookup,
            patch.object(hugo, 'lookup') as hugo_lookup,
            patch.object(locus, 'lookup') as locus_lookup,
            patch.object(newbery, 'lookup') as newbery_lookup,
            patch('urllib.request.urlopen') as urlopen,
            patch.object(locus, '_request_html') as locus_http,
        ):
            refresh_award_source_cache('nebula')
            refresh_award_source_cache('locus')
            refresh_award_source_cache('newbery')
        engine_lookup.assert_not_called()
        nebula_lookup.assert_not_called()
        hugo_lookup.assert_not_called()
        locus_lookup.assert_not_called()
        newbery_lookup.assert_not_called()
        urlopen.assert_not_called()
        locus_http.assert_not_called()


class PreferencesIsolationTests(CacheControlTestCase):
    def test_refresh_does_not_mutate_preference_mapping(self):
        prefs = {
            'disabled_source_keys': ['nebula'],
            'award_output_template': '<award>',
            'max_qualifying_rank': 3,
            'writeback_enabled': True,
            'writeback_field': '#awards',
            'writeback_mode': 'append',
        }
        snapshot = dict(prefs)
        self.assertTrue(refresh_award_source_cache('nebula'))
        self.assertEqual(prefs, snapshot)


class ConfirmedRefreshHelperTests(CacheControlTestCase):
    def test_cancel_does_not_call_refresh(self):
        _save_archive('nebula')
        nebula._pages_cache['best-novel'] = (('https://example.test/n', 'html'),)
        with patch.object(cache_control, 'refresh_award_source_cache') as refresh:
            outcome = run_source_cache_refresh_if_confirmed(
                'nebula',
                'Nebula Awards',
                confirmed=False,
            )
        refresh.assert_not_called()
        self.assertIsNone(outcome)
        self.assertTrue((self.cache_dir / 'nebula.json').is_file())
        self.assertIn('best-novel', nebula._pages_cache)

    def test_confirm_calls_refresh_once_for_that_source(self):
        with patch.object(
            cache_control,
            'refresh_award_source_cache',
            return_value=True,
        ) as refresh:
            outcome = run_source_cache_refresh_if_confirmed(
                'nebula',
                'Nebula Awards',
                confirmed=True,
            )
        refresh.assert_called_once_with('nebula')
        self.assertTrue(outcome)

    def test_success_copy_is_used_only_when_persistent_clear_succeeds(self):
        _save_archive('nebula')
        self.assertTrue(refresh_award_source_cache('nebula'))
        self.assertIn(
            'Nebula Awards cached data cleared.',
            source_cache_refresh_status_text('Nebula Awards'),
        )
        self.assertNotIn(
            'cached data cleared',
            source_cache_refresh_failure_text('Nebula Awards'),
        )

    def test_persistent_failure_returns_false_not_success_copy(self):
        _save_archive('nebula')
        nebula._pages_cache['best-novel'] = (('https://example.test/n', 'html'),)
        with patch.object(Path, 'unlink', _fail_unlink_for('nebula.json')):
            outcome = run_source_cache_refresh_if_confirmed(
                'nebula',
                'Nebula Awards',
                confirmed=True,
            )
        self.assertIs(outcome, False)
        self.assertEqual(nebula._pages_cache, {})
        self.assertTrue((self.cache_dir / 'nebula.json').is_file())
        failure = source_cache_refresh_failure_text('Nebula Awards')
        self.assertIn('in-memory cache was cleared', failure)
        self.assertIn('could not be removed', failure)
        self.assertNotIn('cached data cleared', failure)


class PersistentFailureNoNetworkTests(CacheControlTestCase):
    def test_failure_path_performs_no_source_lookup_or_http(self):
        _save_archive('nebula')
        _save_locus_entry('authors', _AUTHOR_URL)
        with (
            patch.object(Path, 'unlink', _fail_unlink_for('nebula.json')),
            patch('awards.engine.lookup_awards') as engine_lookup,
            patch.object(nebula, 'lookup') as nebula_lookup,
            patch.object(locus, 'lookup') as locus_lookup,
            patch('urllib.request.urlopen') as urlopen,
            patch.object(locus, '_request_html') as locus_http,
        ):
            self.assertFalse(refresh_award_source_cache('nebula'))
            self.assertTrue(refresh_award_source_cache('locus'))
        engine_lookup.assert_not_called()
        nebula_lookup.assert_not_called()
        locus_lookup.assert_not_called()
        urlopen.assert_not_called()
        locus_http.assert_not_called()
