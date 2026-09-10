"""Offline coverage for International Booker persistent parsed-archive cache."""

from __future__ import annotations

import importlib.util
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.cache_control import refresh_award_source_cache
from awards.sources import booker, international_booker as ib

_UTC = timezone.utc
_TESTS_DIR = Path(__file__).resolve().parent


def _load_parser_tests():
    path = _TESTS_DIR / 'test_international_booker_parser.py'
    spec = importlib.util.spec_from_file_location(
        'test_international_booker_parser',
        path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PARSER_TESTS = _load_parser_tests()
TAIWAN = _PARSER_TESTS.TAIWAN
YANG = _PARSER_TESTS.YANG
TAIWAN_URL = _PARSER_TESTS.TAIWAN_URL
archive_html = _PARSER_TESTS.archive_html


def _record(year, title, author, translator, slug, status='Winner'):
    return ib._ParsedRecord(
        award_year=year,
        status=status,
        work_title=title,
        work_author=author,
        source_url=f'https://thebookerprizes.com/the-booker-library/books/{slug}',
        notes=f'Translated by {translator}',
    )


def _taiwan():
    return _record(
        2026,
        TAIWAN,
        YANG,
        'Lin King',
        'taiwan-travelogue',
    )


def _complete_archive(*, extra=()):
    records = []
    for year in range(ib.ARCHIVE_MIN_YEAR, ib.ARCHIVE_MAX_YEAR + 1):
        if year == 2026:
            records.append(_taiwan())
            records.extend(
                (
                    _record(
                        2026,
                        'The Nights Are Quiet in Tehran',
                        'Shida Bazyar',
                        'Ruth Martin',
                        'the-nights-are-quiet-in-tehran',
                        'Shortlisted',
                    ),
                    _record(
                        2026,
                        'She Who Remains',
                        'Rene Karabash',
                        'Izidora Angel',
                        'she-who-remains',
                        'Shortlisted',
                    ),
                    _record(
                        2026,
                        'The Director',
                        'Daniel Kehlmann',
                        'Ross Benjamin',
                        'the-director',
                        'Shortlisted',
                    ),
                    _record(
                        2026,
                        'On Earth As It Is Beneath',
                        'Ana Paula Maia',
                        'Padma Viswanathan',
                        'on-earth-as-it-is-beneath',
                        'Shortlisted',
                    ),
                    _record(
                        2026,
                        'The Witch',
                        'Marie NDiaye',
                        'Jordan Stump',
                        'the-witch',
                        'Shortlisted',
                    ),
                )
            )
            continue
        records.append(
            _record(
                year,
                f'Stub Winner {year}',
                f'Stub Winner Author {year}',
                f'Stub Translator {year}',
                f'stub-winner-{year}',
            )
        )
        for index in range(1, 6):
            records.append(
                _record(
                    year,
                    f'Stub Short {year}-{index}',
                    f'Stub Short Author {year}-{index}',
                    f'Stub Translator {year}-{index}',
                    f'stub-short-{year}-{index}',
                    'Shortlisted',
                )
            )
    records.extend(extra)
    return tuple(records)


def _with_extra_shortlisted(archive):
    extra = _record(
        2024,
        'Replacement Short 2024-1',
        'Replacement Author',
        'Replacement Translator',
        'replacement-short-2024-1',
        'Shortlisted',
    )
    trimmed = tuple(
        record
        for record in archive
        if not (
            record.award_year == 2024
            and record.work_title == 'Stub Short 2024-1'
        )
    )
    return trimmed + (extra,)


def _save_disk(records, *, generated_at=None, ttl_seconds=None, version=None):
    cache.save_source_cache(
        ib.SOURCE_KEY,
        ib.CACHE_VERSION if version is None else version,
        records=[ib._record_to_cache_dict(record) for record in records],
        source_urls=ib._archive_source_urls(),
        coverage=ib._coverage_from_records(records),
        ttl_seconds=(
            ib.CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


class InternationalBookerPersistentCacheTests(unittest.TestCase):
    def setUp(self):
        ib._reset_runtime_state()
        booker._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        ib._reset_runtime_state()
        booker._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _disk_path(self):
        return self.cache_dir / 'international_booker.json'

    def _rewrite_records(self, mutate):
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        mutate(payload)
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )

    def _assert_taiwan(self, results):
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, TAIWAN)
        self.assertEqual(result.work_author, YANG)
        self.assertEqual(result.award_name, 'International Booker Prize')
        self.assertEqual(result.award_year, 2026)
        self.assertIsNone(result.category)
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'The Booker Prizes')
        self.assertEqual(result.source_url, TAIWAN_URL)
        self.assertEqual(result.notes, 'Translated by Lin King')
        self.assertEqual(result.identity_kind, 'work')
        self.assertFalse(result.is_specifically_cited_work)

    def test_cache_identity_constants(self):
        self.assertEqual(ib.SOURCE_KEY, 'international_booker')
        self.assertNotEqual(ib.SOURCE_KEY, booker.SOURCE_KEY)
        self.assertEqual(ib.CACHE_VERSION, 1)
        self.assertEqual(ib.CACHE_BASE_TTL_SECONDS, 7 * 24 * 60 * 60)
        self.assertEqual(ib.CACHE_REFRESH_OFFSET_SECONDS, 19 * 60 * 60)
        self.assertEqual(
            ib.CACHE_TTL_SECONDS,
            ib.CACHE_BASE_TTL_SECONDS + ib.CACHE_REFRESH_OFFSET_SECONDS,
        )
        self.assertEqual(ib.CACHE_TTL_SECONDS, 673200)

    def test_plus_19h_is_unused_by_existing_sources(self):
        from awards.sources import (
            bram_stoker,
            edgar,
            german_book_prize,
            hugo,
            ipaf,
            miles_franklin,
            national_book_critics_circle,
            nebula,
            newbery,
            nobel,
            pen_faulkner,
            pen_hemingway,
            prix_goncourt,
            pulitzer,
            romantic_novel_awards,
            womens_prize_fiction,
            world_fantasy,
        )

        offsets = {
            nebula.CACHE_REFRESH_OFFSET_SECONDS,
            world_fantasy.CACHE_REFRESH_OFFSET_SECONDS,
            hugo.CACHE_REFRESH_OFFSET_SECONDS,
            newbery.CACHE_REFRESH_OFFSET_SECONDS,
            nobel.CACHE_REFRESH_OFFSET_SECONDS,
            pulitzer.CACHE_REFRESH_OFFSET_SECONDS,
            booker.CACHE_REFRESH_OFFSET_SECONDS,
            german_book_prize.CURRENT_YEAR_CACHE_REFRESH_OFFSET_SECONDS,
            prix_goncourt.CACHE_REFRESH_OFFSET_SECONDS,
            miles_franklin.CACHE_REFRESH_OFFSET_SECONDS,
            womens_prize_fiction.CACHE_REFRESH_OFFSET_SECONDS,
            national_book_critics_circle.CURRENT_CACHE_REFRESH_OFFSET_SECONDS,
            pen_faulkner.CURRENT_CACHE_REFRESH_OFFSET_SECONDS,
            pen_hemingway.CURRENT_CACHE_REFRESH_OFFSET_SECONDS,
            ipaf.CURRENT_CACHE_REFRESH_OFFSET_SECONDS,
            bram_stoker.CURRENT_CACHE_REFRESH_OFFSET_SECONDS,
            edgar.CACHE_REFRESH_OFFSET_SECONDS,
            romantic_novel_awards.CACHE_REFRESH_OFFSET_SECONDS,
        }
        self.assertNotIn(19 * 60 * 60, offsets)

    def test_complete_archive_helper_passes_source_validation(self):
        ib._validate_cached_archive(_complete_archive())

    def test_parsed_record_round_trips_all_fields(self):
        original = _taiwan()
        restored = ib._record_from_cache_dict(ib._record_to_cache_dict(original))
        self.assertEqual(restored, original)
        shortlisted = _record(
            2026,
            'The Witch',
            'Marie NDiaye',
            'Jordan Stump',
            'the-witch',
            'Shortlisted',
        )
        self.assertEqual(
            ib._record_from_cache_dict(ib._record_to_cache_dict(shortlisted)),
            shortlisted,
        )

    def test_rank_and_category_are_not_persisted(self):
        payload = ib._record_to_cache_dict(_taiwan())
        self.assertNotIn('rank', payload)
        self.assertNotIn('category', payload)
        self.assertEqual(set(payload), set(ib._RECORD_CACHE_FIELDS))

    def test_live_validated_archive_writes_international_booker_json(self):
        archive = _complete_archive()
        with patch.object(ib, '_load_live_archive', return_value=archive):
            results = ib.lookup(TAIWAN, YANG)
        self._assert_taiwan(results)
        self.assertTrue(self._disk_path().is_file())
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        self.assertEqual(payload['source_key'], 'international_booker')
        self.assertEqual(payload['source_urls'], [ib.SOURCE_HOME_URL])
        self.assertEqual(payload['record_count'], 66)
        self.assertFalse((self.cache_dir / 'booker.json').exists())

    def test_fresh_cache_lookup_makes_zero_network_calls(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        ib._reset_runtime_state()
        with patch.object(
            ib, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            ib, '_load_live_archive', side_effect=AssertionError('live')
        ):
            results = ib.lookup(TAIWAN, YANG)
        self._assert_taiwan(results)

    def test_fresh_cache_does_not_consume_refresh_budget(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        ib._reset_runtime_state()
        with cache.lookup_refresh_budget():
            with patch.object(
                ib, '_load_live_archive', side_effect=AssertionError('live')
            ):
                results = ib.lookup(TAIWAN, YANG)
            self._assert_taiwan(results)
            self.assertTrue(cache.try_claim_stale_refresh())

    def test_ram_reset_plus_fresh_disk_makes_zero_http(self):
        archive = _complete_archive()
        with patch.object(ib, '_load_live_archive', return_value=archive) as live:
            first = ib.lookup(TAIWAN, YANG)
        self._assert_taiwan(first)
        self.assertEqual(live.call_count, 1)
        ib._reset_runtime_state()
        self.assertTrue(self._disk_path().is_file())
        with patch.object(
            ib, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            ib, '_load_live_archive', side_effect=AssertionError('live')
        ):
            second = ib.lookup(TAIWAN, YANG)
        self._assert_taiwan(second)

    def test_stale_cache_successful_refresh_replaces_disk(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original_generated = json.loads(
            self._disk_path().read_text(encoding='utf-8')
        )['generated_at']
        refreshed = _with_extra_shortlisted(stale)
        with patch.object(ib, '_load_live_archive', return_value=refreshed):
            results = ib.lookup(TAIWAN, YANG)
        self._assert_taiwan(results)
        updated = json.loads(self._disk_path().read_text(encoding='utf-8'))
        self.assertNotEqual(updated['generated_at'], original_generated)
        extra = ib.lookup('Replacement Short 2024-1', 'Replacement Author')
        self.assertEqual(len(extra), 1)
        self.assertEqual(extra[0].status, 'Shortlisted')

    def test_stale_cache_without_refresh_slot_serves_stale(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                ib, '_load_live_archive', side_effect=AssertionError('live')
            ):
                results = ib.lookup(TAIWAN, YANG)
        self._assert_taiwan(results)

    def test_stale_cache_live_failure_keeps_file_unchanged(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        with patch.object(
            ib, '_load_live_archive', side_effect=ib.InternationalBookerSourceError('blocked')
        ):
            results = ib.lookup(TAIWAN, YANG)
        self._assert_taiwan(results)
        self.assertEqual(self._disk_path().read_text(encoding='utf-8'), original)

    def test_category_in_cache_record_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        self._rewrite_records(
            lambda payload: payload['records'][0].__setitem__('category', 'Fiction')
        )
        live = _complete_archive()
        with patch.object(ib, '_load_live_archive', return_value=live) as mocked:
            ib.lookup(TAIWAN, YANG)
        self.assertEqual(mocked.call_count, 1)

    def test_2027_cache_record_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        self._rewrite_records(
            lambda payload: payload['records'][0].__setitem__('award_year', 2027)
        )
        live = _complete_archive()
        with patch.object(ib, '_load_live_archive', return_value=live) as mocked:
            results = ib.lookup(TAIWAN, YANG)
        self.assertEqual(mocked.call_count, 1)
        self._assert_taiwan(results)

    def test_wrong_source_urls_are_rejected(self):
        archive = _complete_archive()
        cache.save_source_cache(
            ib.SOURCE_KEY,
            ib.CACHE_VERSION,
            records=[ib._record_to_cache_dict(record) for record in archive],
            source_urls=['https://thebookerprizes.com/'],
            coverage=ib._coverage_from_records(archive),
            ttl_seconds=ib.CACHE_TTL_SECONDS,
            generated_at=datetime.now(_UTC),
        )
        live = _complete_archive()
        with patch.object(ib, '_load_live_archive', return_value=live) as mocked:
            ib.lookup(TAIWAN, YANG)
        self.assertEqual(mocked.call_count, 1)

    def test_version_mismatch_uses_live_path(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC), version=2)
        live = _complete_archive()
        with patch.object(ib, '_load_live_archive', return_value=live) as mocked:
            results = ib.lookup(TAIWAN, YANG)
        self.assertEqual(mocked.call_count, 1)
        self._assert_taiwan(results)

    def test_save_failure_does_not_fail_lookup(self):
        archive = _complete_archive()
        with patch.object(ib, '_load_live_archive', return_value=archive):
            with patch.object(
                ib.cache,
                'save_source_cache',
                side_effect=OSError('disk full'),
            ):
                results = ib.lookup(TAIWAN, YANG)
        self._assert_taiwan(results)

    def test_ram_reset_does_not_delete_disk_cache(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        ib._archive_records_cache = archive
        self.assertTrue(self._disk_path().is_file())
        ib._reset_runtime_state()
        self.assertTrue(self._disk_path().is_file())
        self.assertIsNone(ib._archive_records_cache)
        with patch.object(
            ib, '_load_live_archive', side_effect=AssertionError('live')
        ), patch.object(
            ib, '_fetch_html', side_effect=AssertionError('network')
        ):
            results = ib.lookup(TAIWAN, YANG)
        self._assert_taiwan(results)

    def test_manual_refresh_removes_only_international_booker_json_and_ram(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        ib._archive_records_cache = archive
        booker._archive_records_cache = ()
        cache.save_source_cache(
            'booker',
            1,
            records=[{'title': 'booker', 'year': 2020}],
            source_urls=['https://example.test/booker'],
            coverage={'source': 'booker'},
            ttl_seconds=3600,
            generated_at=datetime(2026, 1, 1, tzinfo=_UTC),
        )
        with patch.object(
            ib, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            ib, '_load_live_archive', side_effect=AssertionError('live')
        ):
            self.assertTrue(refresh_award_source_cache('international_booker'))
        self.assertFalse(self._disk_path().exists())
        self.assertIsNone(ib._archive_records_cache)
        self.assertTrue((self.cache_dir / 'booker.json').is_file())
        self.assertEqual(booker._archive_records_cache, ())

    def test_manual_refresh_makes_zero_http(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        ib._archive_records_cache = archive
        with patch.object(
            ib, '_fetch_html', side_effect=AssertionError('network')
        ) as fetch, patch.object(
            ib, 'lookup', side_effect=AssertionError('lookup')
        ):
            self.assertTrue(refresh_award_source_cache('international_booker'))
        fetch.assert_not_called()

    def test_booker_refresh_does_not_clear_international_booker(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        ib._archive_records_cache = archive
        cache.save_source_cache(
            'booker',
            1,
            records=[{'title': 'booker', 'year': 2020}],
            source_urls=['https://example.test/booker'],
            coverage={'source': 'booker'},
            ttl_seconds=3600,
            generated_at=datetime(2026, 1, 1, tzinfo=_UTC),
        )
        booker._archive_records_cache = ()
        self.assertTrue(refresh_award_source_cache('booker'))
        self.assertTrue(self._disk_path().is_file())
        self.assertIsNotNone(ib._archive_records_cache)
        self.assertFalse((self.cache_dir / 'booker.json').exists())
        self.assertIsNone(booker._archive_records_cache)


class InternationalBookerLiveHtmlCachePathTests(unittest.TestCase):
    def setUp(self):
        ib._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        cache.set_cache_directory(Path(self._temp.name))

    def tearDown(self):
        ib._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def test_parse_of_generated_archive_html_is_cacheable(self):
        html = archive_html()
        records, years = ib._parse_archive_html(html)
        ib._validate_archive(records, years)
        _save_disk(records, generated_at=datetime.now(_UTC))
        ib._reset_runtime_state()
        with patch.object(
            ib, '_fetch_html', side_effect=AssertionError('network')
        ):
            results = ib.lookup(TAIWAN, YANG)
        self.assertEqual(results[0].award_year, 2026)
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].notes, 'Translated by Lin King')


if __name__ == '__main__':
    unittest.main()
