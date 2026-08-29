"""Offline coverage for Newbery persistent listing-archive cache."""

from __future__ import annotations

import importlib.util
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.engine import lookup_awards
from awards.sources import hugo, nebula, newbery, world_fantasy

_UTC = timezone.utc
_TESTS_DIR = Path(__file__).resolve().parent

CRISPIN_URL = 'https://www.ala.org/winner/crispin-cross-lead'
WRINKLE_URL = 'https://www.ala.org/winner/a-wrinkle-in-time'
ATUAN_URL = 'https://www.ala.org/winner/tombs-atuan'


def _load_test_module(name: str):
    path = _TESTS_DIR / f'{name}.py'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _listing_url_for_year(year: int) -> str:
    for url, start, end in newbery._ARCHIVE_PAGE_SPECS:
        if start <= year <= end:
            return url
    raise AssertionError(f'no listing page for {year}')


def _listing_record(year, status, title, slug, source_url=None):
    return newbery._ListingRecord(
        work_title=title,
        award_year=year,
        status=status,
        detail_url=f'https://www.ala.org/winner/{slug}',
        source_url=_listing_url_for_year(year) if source_url is None else source_url,
    )


def _complete_archive(*, crispin=True):
    records: list[newbery._ListingRecord] = []
    for year in range(newbery.ARCHIVE_MIN_YEAR, newbery.ARCHIVE_MAX_YEAR + 1):
        if year == 1963:
            records.append(
                _listing_record(
                    year, 'Winner', 'A Wrinkle in Time', 'a-wrinkle-in-time'
                )
            )
        elif year == 2003 and crispin:
            records.append(
                _listing_record(
                    year,
                    'Winner',
                    'Crispin: The Cross of Lead',
                    'crispin-cross-lead',
                )
            )
        else:
            records.append(
                _listing_record(
                    year,
                    'Winner',
                    f'Archive Winner {year}',
                    f'archive-winner-{year}',
                )
            )
        if year == 1972:
            records.append(
                _listing_record(
                    year, 'Honor', 'The Tombs of Atuan', 'tombs-atuan'
                )
            )
    return tuple(records)


def _save_disk(records, *, generated_at=None, ttl_seconds=None, version=None):
    cache.save_source_cache(
        newbery.SOURCE_KEY,
        newbery.CACHE_VERSION if version is None else version,
        records=[newbery._record_to_cache_dict(record) for record in records],
        source_urls=newbery._archive_source_urls(),
        coverage=newbery._coverage_from_records(records),
        ttl_seconds=(
            newbery.CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _detail_html(title: str, byline: str) -> str:
    return (
        f'<h1>{title}</h1>'
        f'<div class="font-bitter text-center"><p>{byline}</p></div>'
        '<h2>About</h2><p>About the book.</p>'
    )


def _detail_pages():
    return {
        CRISPIN_URL: _detail_html(
            'Crispin: The Cross of Lead',
            'by Avi, and published by Hyperion',
        ),
        WRINKLE_URL: _detail_html(
            'A Wrinkle in Time',
            "by Madeleine L'Engle, published by Farrar",
        ),
        ATUAN_URL: _detail_html(
            'The Tombs of Atuan',
            'Written by Ursula K. LeGuin. Published by Atheneum.',
        ),
    }


class NewberyPersistentCacheTests(unittest.TestCase):
    def setUp(self):
        newbery._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)
        self.details = _detail_pages()

    def tearDown(self):
        newbery._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _disk_path(self):
        return self.cache_dir / 'newbery.json'

    def _fetch_details_only(self, opener, url: str) -> str:
        if url in newbery._archive_source_urls():
            raise AssertionError(f'listing fetch {url}')
        if url in self.details:
            return self.details[url]
        raise AssertionError(f'unexpected fetch {url}')

    def test_cache_identity_constants(self):
        self.assertEqual(newbery.SOURCE_KEY, 'newbery')
        self.assertEqual(newbery.CACHE_VERSION, 1)
        self.assertEqual(newbery.CACHE_BASE_TTL_SECONDS, 7 * 24 * 60 * 60)
        self.assertEqual(newbery.CACHE_REFRESH_OFFSET_SECONDS, 3 * 60 * 60)
        self.assertEqual(
            newbery.CACHE_TTL_SECONDS,
            newbery.CACHE_BASE_TTL_SECONDS + newbery.CACHE_REFRESH_OFFSET_SECONDS,
        )
        self.assertEqual(newbery.CACHE_TTL_SECONDS, 615600)

    def test_complete_archive_helper_passes_source_validation(self):
        newbery._validate_cached_archive(_complete_archive())

    def test_listing_record_round_trips_all_fields(self):
        original = newbery._ListingRecord(
            work_title='Crispin: The Cross of Lead',
            award_year=2003,
            status='Winner',
            detail_url=CRISPIN_URL,
            source_url=newbery.ARCHIVE_URL_1992_2003,
        )
        restored = newbery._record_from_cache_dict(
            newbery._record_to_cache_dict(original)
        )
        self.assertEqual(restored, original)

    def test_record_order_is_preserved(self):
        archive = _complete_archive()
        restored = newbery._records_from_cache_payload(
            {
                'records': [
                    newbery._record_to_cache_dict(record) for record in archive
                ],
                'source_urls': list(newbery._archive_source_urls()),
            }
        )
        self.assertEqual(restored, archive)
        self.assertEqual(
            [record.work_title for record in restored[:3]],
            [record.work_title for record in archive[:3]],
        )

    def test_fresh_cache_title_miss_makes_zero_http(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        newbery._reset_runtime_state()
        with patch.object(
            newbery, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            newbery, '_load_live_archive', side_effect=AssertionError('live')
        ):
            results = newbery.lookup('Dune', 'Frank Herbert')
        self.assertEqual(results, [])
        self.assertIsNotNone(newbery._listing_records_cache)

    def test_fresh_cache_title_hit_fetches_only_detail(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        newbery._reset_runtime_state()
        fetched: list[str] = []

        def _fetch(opener, url: str) -> str:
            fetched.append(url)
            return self._fetch_details_only(opener, url)

        with patch.object(newbery, '_fetch_html', side_effect=_fetch), patch.object(
            newbery, '_load_live_archive', side_effect=AssertionError('live')
        ):
            results = newbery.lookup('Crispin: The Cross of Lead', 'Avi')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'Crispin: The Cross of Lead')
        self.assertEqual(results[0].work_author, 'Avi')
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].award_year, 2003)
        self.assertIsNone(results[0].rank)
        self.assertEqual(results[0].source_name, 'John Newbery Medal')
        self.assertEqual(results[0].source_url, CRISPIN_URL)
        self.assertEqual(fetched, [CRISPIN_URL])

    def test_fresh_cache_does_not_consume_refresh_budget(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        newbery._reset_runtime_state()
        with cache.lookup_refresh_budget():
            with patch.object(
                newbery, '_load_live_archive', side_effect=AssertionError('live')
            ), patch.object(
                newbery, '_fetch_html', side_effect=AssertionError('network')
            ):
                results = newbery.lookup('Dune', 'Frank Herbert')
            self.assertEqual(results, [])
            self.assertTrue(cache.try_claim_stale_refresh())

    def test_restart_simulation_reloads_disk_after_ram_clear(self):
        archive = _complete_archive()
        with patch.object(
            newbery, '_load_live_archive', return_value=archive
        ) as live:
            first = newbery.lookup('Dune', 'Frank Herbert')
        self.assertEqual(first, [])
        self.assertEqual(live.call_count, 1)
        self.assertTrue(self._disk_path().is_file())
        newbery._reset_runtime_state()
        self.assertTrue(self._disk_path().is_file())
        with patch.object(
            newbery, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            newbery, '_load_live_archive', side_effect=AssertionError('live')
        ):
            second = newbery.lookup('Dune', 'Frank Herbert')
        self.assertEqual(second, [])

    def test_stale_cache_successful_refresh_replaces_disk(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        refreshed = _complete_archive(crispin=False)
        with patch.object(newbery, '_load_live_archive', return_value=refreshed):
            results = newbery.lookup('Dune', 'Frank Herbert')
        self.assertEqual(results, [])
        updated = self._disk_path().read_text(encoding='utf-8')
        self.assertNotEqual(updated, original)
        payload = json.loads(updated)
        titles = [item['work_title'] for item in payload['records']]
        self.assertIn('Archive Winner 2003', titles)
        self.assertNotIn('Crispin: The Cross of Lead', titles)

    def test_stale_cache_claims_refresh_slot_inside_lookup_budget(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        newbery._reset_runtime_state()
        refreshed = _complete_archive(crispin=False)
        with cache.lookup_refresh_budget():
            with patch.object(
                newbery, '_load_live_archive', return_value=refreshed
            ):
                newbery.lookup('Dune', 'Frank Herbert')
            self.assertFalse(cache.try_claim_stale_refresh())

    def test_stale_cache_failed_refresh_uses_stale_listing(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        fetched: list[str] = []

        def _fetch(opener, url: str) -> str:
            fetched.append(url)
            return self._fetch_details_only(opener, url)

        with patch.object(
            newbery,
            '_load_live_archive',
            side_effect=newbery.NewberySourceError('ala down'),
        ), patch.object(newbery, '_fetch_html', side_effect=_fetch):
            results = newbery.lookup('Crispin: The Cross of Lead', 'Avi')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'Crispin: The Cross of Lead')
        self.assertEqual(self._disk_path().read_text(encoding='utf-8'), original)
        self.assertEqual(fetched, [CRISPIN_URL])

    def test_stale_cache_without_refresh_slot_skips_listing_http(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        newbery._reset_runtime_state()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                newbery, '_load_live_archive', side_effect=AssertionError('live')
            ) as mocked, patch.object(
                newbery, '_fetch_html', side_effect=AssertionError('network')
            ):
                results = newbery.lookup('Dune', 'Frank Herbert')
            mocked.assert_not_called()
        self.assertEqual(results, [])

    def test_missing_cache_live_fetches_after_stale_refresh_budget_consumed(self):
        self.assertFalse(self._disk_path().is_file())
        live = _complete_archive()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                newbery, '_load_live_archive', return_value=live
            ) as mocked:
                results = newbery.lookup('Dune', 'Frank Herbert')
            self.assertEqual(mocked.call_count, 1)
        self.assertEqual(results, [])

    def test_missing_year_is_rejected(self):
        archive = [
            record
            for record in _complete_archive()
            if record.award_year != 1980
        ]
        cache.save_source_cache(
            newbery.SOURCE_KEY,
            newbery.CACHE_VERSION,
            records=[newbery._record_to_cache_dict(record) for record in archive],
            source_urls=newbery._archive_source_urls(),
            coverage={'min_year': 1930},
            ttl_seconds=newbery.CACHE_TTL_SECONDS,
            generated_at=datetime.now(_UTC),
        )
        live = _complete_archive()
        with patch.object(
            newbery, '_load_live_archive', return_value=live
        ) as mocked:
            newbery.lookup('Dune', 'Frank Herbert')
        self.assertEqual(mocked.call_count, 1)

    def test_duplicate_winner_is_rejected(self):
        archive = list(_complete_archive())
        archive.append(
            _listing_record(2003, 'Winner', 'Other Winner', 'other-winner-2003')
        )
        cache.save_source_cache(
            newbery.SOURCE_KEY,
            newbery.CACHE_VERSION,
            records=[newbery._record_to_cache_dict(record) for record in archive],
            source_urls=newbery._archive_source_urls(),
            coverage={},
            ttl_seconds=newbery.CACHE_TTL_SECONDS,
            generated_at=datetime.now(_UTC),
        )
        live = _complete_archive()
        with patch.object(
            newbery, '_load_live_archive', return_value=live
        ) as mocked:
            newbery.lookup('Dune', 'Frank Herbert')
        self.assertEqual(mocked.call_count, 1)

    def test_unsupported_status_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['status'] = 'Finalist'
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(
            newbery, '_load_live_archive', return_value=live
        ) as mocked:
            newbery.lookup('Dune', 'Frank Herbert')
        self.assertEqual(mocked.call_count, 1)

    def test_off_host_detail_url_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['detail_url'] = (
            'https://example.com/winner/archive-winner-1930'
        )
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(
            newbery, '_load_live_archive', return_value=live
        ) as mocked:
            newbery.lookup('Dune', 'Frank Herbert')
        self.assertEqual(mocked.call_count, 1)

    def test_malformed_field_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        del payload['records'][0]['work_title']
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(
            newbery, '_load_live_archive', return_value=live
        ) as mocked:
            newbery.lookup('Dune', 'Frank Herbert')
        self.assertEqual(mocked.call_count, 1)

    def test_year_outside_supported_range_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['award_year'] = 1929
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(
            newbery, '_load_live_archive', return_value=live
        ) as mocked:
            newbery.lookup('Dune', 'Frank Herbert')
        self.assertEqual(mocked.call_count, 1)

    def test_incomplete_coverage_is_rejected(self):
        cache.save_source_cache(
            newbery.SOURCE_KEY,
            newbery.CACHE_VERSION,
            records=[
                newbery._record_to_cache_dict(
                    _listing_record(
                        2003,
                        'Winner',
                        'Crispin: The Cross of Lead',
                        'crispin-cross-lead',
                    )
                )
            ],
            source_urls=newbery._archive_source_urls(),
            coverage={'min_year': 1930},
            ttl_seconds=newbery.CACHE_TTL_SECONDS,
            generated_at=datetime.now(_UTC),
        )
        live = _complete_archive()
        with patch.object(
            newbery, '_load_live_archive', return_value=live
        ) as mocked:
            newbery.lookup('Dune', 'Frank Herbert')
        self.assertEqual(mocked.call_count, 1)

    def test_version_mismatch_uses_live_path(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC), version=2)
        live = _complete_archive()
        with patch.object(
            newbery, '_load_live_archive', return_value=live
        ) as mocked:
            newbery.lookup('Dune', 'Frank Herbert')
        self.assertEqual(mocked.call_count, 1)

    def test_save_failure_does_not_fail_lookup(self):
        archive = _complete_archive()
        with patch.object(newbery, '_load_live_archive', return_value=archive):
            with patch.object(
                newbery.cache,
                'save_source_cache',
                side_effect=OSError('disk full'),
            ):
                results = newbery.lookup('Dune', 'Frank Herbert')
        self.assertEqual(results, [])

    def test_ram_reset_does_not_delete_disk_cache(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        newbery._listing_records_cache = archive
        self.assertTrue(self._disk_path().is_file())
        newbery._reset_runtime_state()
        self.assertTrue(self._disk_path().is_file())
        self.assertIsNone(newbery._listing_records_cache)
        with patch.object(
            newbery, '_load_live_archive', side_effect=AssertionError('live')
        ), patch.object(
            newbery, '_fetch_html', side_effect=AssertionError('network')
        ):
            results = newbery.lookup('Dune', 'Frank Herbert')
        self.assertEqual(results, [])

    def test_listing_disk_does_not_persist_detail_authors(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        newbery._reset_runtime_state()
        self.assertEqual(newbery._detail_author_cache, {})
        fetched: list[str] = []

        def _fetch(opener, url: str) -> str:
            fetched.append(url)
            return self._fetch_details_only(opener, url)

        with patch.object(newbery, '_fetch_html', side_effect=_fetch), patch.object(
            newbery, '_load_live_archive', side_effect=AssertionError('live')
        ):
            first = newbery.lookup('Crispin: The Cross of Lead', 'Avi')
        self.assertEqual(len(first), 1)
        self.assertEqual(fetched, [CRISPIN_URL])
        self.assertEqual(newbery._detail_author_cache[CRISPIN_URL], 'Avi')

        fetched.clear()
        with patch.object(newbery, '_fetch_html', side_effect=_fetch), patch.object(
            newbery, '_load_live_archive', side_effect=AssertionError('live')
        ):
            second = newbery.lookup('Crispin: The Cross of Lead', 'Avi')
        self.assertEqual(len(second), 1)
        self.assertEqual(fetched, [])

        newbery._reset_runtime_state()
        self.assertEqual(newbery._detail_author_cache, {})
        self.assertTrue(self._disk_path().is_file())
        fetched.clear()
        with patch.object(newbery, '_fetch_html', side_effect=_fetch), patch.object(
            newbery, '_load_live_archive', side_effect=AssertionError('live')
        ):
            third = newbery.lookup('Crispin: The Cross of Lead', 'Avi')
        self.assertEqual(len(third), 1)
        self.assertEqual(fetched, [CRISPIN_URL])

    def test_candidate_detail_http_failure_still_raises(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        newbery._reset_runtime_state()

        def _fail_detail(opener, url: str) -> str:
            if url in newbery._archive_source_urls():
                raise AssertionError(f'listing fetch {url}')
            raise newbery.NewberySourceError(
                f'Newbery request failed with HTTP 500 for {url}'
            )

        with patch.object(newbery, '_fetch_html', side_effect=_fail_detail):
            with self.assertRaises(newbery.NewberySourceError) as caught:
                newbery.lookup('Crispin: The Cross of Lead', 'Avi')
        self.assertIn('HTTP 500', str(caught.exception))
        self.assertNotIn(CRISPIN_URL, newbery._detail_author_cache)


class NewberyFourSourceRefreshBudgetTests(unittest.TestCase):
    def setUp(self):
        newbery._reset_runtime_state()
        hugo._reset_runtime_state()
        world_fantasy._reset_runtime_state()
        nebula._clear_caches_for_tests()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        cache.set_cache_directory(Path(self._temp.name))
        self._nebula_tests = _load_test_module('test_nebula_cache')
        self._wfa_tests = _load_test_module('test_world_fantasy_cache')
        self._hugo_tests = _load_test_module('test_hugo_cache')

    def tearDown(self):
        newbery._reset_runtime_state()
        hugo._reset_runtime_state()
        world_fantasy._reset_runtime_state()
        nebula._clear_caches_for_tests()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def test_one_optional_refresh_among_four_stale_sources(self):
        newbery_stale = _complete_archive()
        nebula_stale = self._nebula_tests._complete_archive()
        wfa_stale = self._wfa_tests._complete_archive()
        hugo_stale = self._hugo_tests._complete_archive()
        stale_at = datetime(2020, 1, 1, tzinfo=_UTC)
        _save_disk(newbery_stale, generated_at=stale_at, ttl_seconds=60)
        self._nebula_tests._save_disk(
            nebula_stale, generated_at=stale_at, ttl_seconds=60
        )
        self._wfa_tests._save_disk(
            wfa_stale, generated_at=stale_at, ttl_seconds=60
        )
        self._hugo_tests._save_disk(
            hugo_stale, generated_at=stale_at, ttl_seconds=60
        )
        newbery._reset_runtime_state()
        hugo._reset_runtime_state()
        world_fantasy._reset_runtime_state()
        nebula._clear_caches_for_tests()

        with patch.object(
            nebula, '_load_live_archive', return_value=nebula_stale
        ) as nebula_live, patch.object(
            world_fantasy, '_load_live_archive', return_value=wfa_stale
        ) as wfa_live, patch.object(
            hugo, '_load_live_archive', return_value=hugo_stale
        ) as hugo_live, patch.object(
            newbery, '_load_live_archive', return_value=newbery_stale
        ) as newbery_live:
            first = lookup_awards(
                'Dune',
                'Frank Herbert',
                enabled_source_keys=(
                    'nebula',
                    'world_fantasy',
                    'hugo',
                    'newbery',
                ),
            )
            self.assertEqual(len(first.failures), 0)
            first_counts = (
                nebula_live.call_count,
                wfa_live.call_count,
                hugo_live.call_count,
                newbery_live.call_count,
            )
            self.assertEqual(sum(first_counts), 1)

            newbery._reset_runtime_state()
            hugo._reset_runtime_state()
            world_fantasy._reset_runtime_state()
            nebula._clear_caches_for_tests()
            second = lookup_awards(
                'Dune',
                'Frank Herbert',
                enabled_source_keys=(
                    'nebula',
                    'world_fantasy',
                    'hugo',
                    'newbery',
                ),
            )
            self.assertEqual(len(second.failures), 0)
            second_counts = (
                nebula_live.call_count - first_counts[0],
                wfa_live.call_count - first_counts[1],
                hugo_live.call_count - first_counts[2],
                newbery_live.call_count - first_counts[3],
            )
            self.assertEqual(sum(second_counts), 1)
            for first_n, second_n in zip(first_counts, second_counts):
                if first_n:
                    self.assertEqual(second_n, 0)


if __name__ == '__main__':
    unittest.main()
