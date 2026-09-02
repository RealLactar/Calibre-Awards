"""Offline coverage for Edgar persistent parsed-archive cache."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.cache_control import refresh_award_source_cache
from awards.sources import edgar, hugo
from tests.test_edgar_parser import _row, database_html

_UTC = timezone.utc


def _record(
    year,
    title,
    author,
    category='Best Novel',
    status='Winner',
    notes=None,
):
    return edgar._ParsedRecord(
        award_year=year,
        category=category,
        status=status,
        work_title=title,
        work_author=author,
        source_url=edgar.SEARCH_DATABASE_URL,
        notes=notes,
    )


def _minimal_archive(*extra):
    records = [
        _record(1946, 'Watchful at Night', 'Julius Fast', 'Best First Novel'),
        _record(1954, 'Beat Not the Bones', 'Charlotte Jay', 'Best Novel'),
        _record(2026, 'The Big Empty', 'Robert Crais', 'Best Novel'),
        _record(
            2026,
            'Fagin the Thief',
            'Allison Epstein',
            'Best Novel',
            'Nominee',
        ),
        _record(
            2015,
            'Invisible City',
            'Julia Dahl',
            'Best First Novel',
            'Nominee',
        ),
        _record(
            2015,
            'Invisible City',
            'Julia Dahl',
            'Mary Higgins Clark Award',
            'Nominee',
        ),
    ]
    records.extend(extra)
    return tuple(edgar._apply_status_precedence(records))


def _save_disk(records, *, generated_at=None, ttl_seconds=None, version=None, page_count=2):
    cache.save_source_cache(
        edgar.SOURCE_KEY,
        edgar.CACHE_VERSION if version is None else version,
        records=[edgar._record_to_cache_dict(record) for record in records],
        source_urls=edgar._archive_source_urls(),
        coverage=edgar._coverage_from_records(records, page_count=page_count),
        ttl_seconds=(
            edgar.CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


class EdgarPersistentCacheTests(unittest.TestCase):
    def setUp(self):
        edgar._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        edgar._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _disk_path(self):
        return self.cache_dir / 'edgar.json'

    def _rewrite(self, mutate):
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        mutate(payload)
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )

    def test_cache_identity_constants(self):
        self.assertEqual(edgar.SOURCE_KEY, 'edgar')
        self.assertEqual(edgar.CACHE_VERSION, 1)
        self.assertEqual(edgar.CACHE_BASE_TTL_SECONDS, 7 * 24 * 60 * 60)
        self.assertEqual(edgar.CACHE_REFRESH_OFFSET_SECONDS, 17 * 60 * 60)
        self.assertEqual(
            edgar.CACHE_TTL_SECONDS,
            edgar.CACHE_BASE_TTL_SECONDS + edgar.CACHE_REFRESH_OFFSET_SECONDS,
        )
        self.assertEqual(edgar.CACHE_TTL_SECONDS, 666000)

    def test_plus_17h_is_unused_by_existing_sources(self):
        from awards.sources import (
            booker,
            bram_stoker,
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
        }
        self.assertNotIn(17 * 60 * 60, offsets)

    def test_cold_complete_paginated_crawl_writes_parsed_cache(self):
        page1 = database_html(
            [
                _row(1946, 'Best First Novel', 'Watchful at Night', 'Julius Fast', winner=True),
                _row(1954, 'Best Novel', 'Beat Not the Bones', 'Charlotte Jay', winner=True),
            ],
            total=3,
            per_page=2,
        )
        page2 = database_html(
            [
                _row(2026, 'Best Novel', 'The Big Empty', 'Robert Crais', winner=True),
                _blank_and_excluded(),
            ],
            total=3,
            per_page=2,
        )

        def fetch(url):
            if url == edgar.SEARCH_DATABASE_URL:
                return page1
            if 'listpage=2' in url:
                return page2
            raise AssertionError(url)

        with patch.object(edgar, '_fetch_html', side_effect=fetch) as mocked:
            results = edgar.lookup('The Big Empty', 'Robert Crais')
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Winner')
        self.assertTrue(self._disk_path().is_file())
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        self.assertEqual(payload['source_key'], 'edgar')
        self.assertEqual(payload['source_urls'], [edgar.SEARCH_DATABASE_URL])
        self.assertNotIn('<td', json.dumps(payload))
        self.assertNotIn('edgar-winner', json.dumps(payload))
        titles = {item['work_title'] for item in payload['records']}
        self.assertIn('The Big Empty', titles)
        self.assertNotIn('End of the Line', titles)
        self.assertEqual(payload['coverage']['page_count'], 2)
        self.assertNotEqual(payload['coverage']['page_count'], 38)

    def test_fresh_cache_lookup_makes_zero_http(self):
        _save_disk(_minimal_archive(), generated_at=datetime.now(_UTC))
        edgar._reset_runtime_state()
        with patch.object(
            edgar, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            edgar, '_load_live_archive', side_effect=AssertionError('live')
        ):
            results = edgar.lookup('The Big Empty', 'Robert Crais')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].category, 'Best Novel')

    def test_ram_reset_plus_fresh_disk_makes_zero_http(self):
        archive = _minimal_archive()
        with patch.object(edgar, '_load_live_archive', return_value=archive) as live:
            first = edgar.lookup('The Big Empty', 'Robert Crais')
        self.assertEqual(live.call_count, 1)
        edgar._reset_runtime_state()
        self.assertTrue(self._disk_path().is_file())
        with patch.object(
            edgar, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            edgar, '_load_live_archive', side_effect=AssertionError('live')
        ):
            second = edgar.lookup('The Big Empty', 'Robert Crais')
        self.assertEqual(first[0].work_title, second[0].work_title)

    def test_stale_cache_successful_refresh_replaces_disk(self):
        stale = _minimal_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = json.loads(self._disk_path().read_text(encoding='utf-8'))
        refreshed = _minimal_archive(
            _record(2026, 'Dead Money', 'Jakob Kerr', 'Best First Novel')
        )
        with patch.object(edgar, '_load_live_archive', return_value=refreshed):
            edgar.lookup('The Big Empty', 'Robert Crais')
        updated = json.loads(self._disk_path().read_text(encoding='utf-8'))
        self.assertNotEqual(updated['generated_at'], original['generated_at'])
        extra = edgar.lookup('Dead Money', 'Jakob Kerr')
        self.assertEqual(len(extra), 1)

    def test_stale_without_refresh_slot_uses_stale_and_skips_network(self):
        _save_disk(
            _minimal_archive(),
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        edgar._reset_runtime_state()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                edgar, '_load_live_archive', side_effect=AssertionError('live')
            ) as mocked, patch.object(
                edgar, '_fetch_html', side_effect=AssertionError('network')
            ):
                results = edgar.lookup('The Big Empty', 'Robert Crais')
            mocked.assert_not_called()
        self.assertEqual(results[0].work_title, 'The Big Empty')

    def test_stale_refresh_failure_preserves_stale_cache(self):
        stale = _minimal_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        with patch.object(
            edgar,
            '_load_live_archive',
            side_effect=edgar.EdgarSourceError('archive down'),
        ):
            results = edgar.lookup('The Big Empty', 'Robert Crais')
        self.assertEqual(results[0].work_title, 'The Big Empty')
        self.assertEqual(self._disk_path().read_text(encoding='utf-8'), original)

    def test_missing_cache_requires_live_crawl(self):
        self.assertFalse(self._disk_path().is_file())
        live = _minimal_archive()
        with patch.object(edgar, '_load_live_archive', return_value=live) as mocked:
            edgar.lookup('The Big Empty', 'Robert Crais')
        self.assertEqual(mocked.call_count, 1)

    def test_source_cache_version_mismatch_requires_live_crawl(self):
        _save_disk(
            _minimal_archive(),
            generated_at=datetime.now(_UTC),
            version=99,
        )
        edgar._reset_runtime_state()
        live = _minimal_archive()
        with patch.object(edgar, '_load_live_archive', return_value=live) as mocked:
            edgar.lookup('The Big Empty', 'Robert Crais')
        self.assertEqual(mocked.call_count, 1)

    def test_broken_middle_page_fails_closed_and_keeps_stale(self):
        stale = _minimal_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        page1 = database_html(
            [
                _row(1946, 'Best First Novel', 'Watchful at Night', 'Julius Fast', winner=True),
                _row(1954, 'Best Novel', 'Beat Not the Bones', 'Charlotte Jay', winner=True),
            ],
            total=3,
            per_page=2,
        )

        def fetch(url):
            if url == edgar.SEARCH_DATABASE_URL:
                return page1
            return '<html><body>Just a moment...</body></html>'

        with patch.object(edgar, '_fetch_html', side_effect=fetch):
            results = edgar.lookup('The Big Empty', 'Robert Crais')
        self.assertEqual(results[0].work_title, 'The Big Empty')
        self.assertEqual(self._disk_path().read_text(encoding='utf-8'), original)

    def test_winner_nominee_category_year_title_author_survive_serialization(self):
        original = _record(
            2026,
            'Julius Katz Draws a Straight Flush',
            'Dave Zeltserman',
            'Best Short Story',
            notes='AHMM September-October',
        )
        restored = edgar._record_from_cache_dict(edgar._record_to_cache_dict(original))
        self.assertEqual(restored, original)
        payload = edgar._record_to_cache_dict(original)
        self.assertNotIn('rank', payload)
        self.assertEqual(set(payload), set(edgar._RECORD_CACHE_FIELDS))

    def test_cross_category_duplicate_facts_survive(self):
        archive = _minimal_archive()
        with patch.object(edgar, '_load_live_archive', return_value=archive):
            results = edgar.lookup('Invisible City', 'Julia Dahl')
        self.assertEqual(len(results), 2)
        self.assertEqual(
            {result.category for result in results},
            {'Best First Novel', 'Mary Higgins Clark Award'},
        )

    def test_blank_and_excluded_rows_are_not_persisted(self):
        html = database_html(
            [
                _row(1946, 'Best First Novel', 'Watchful at Night', 'Julius Fast', winner=True),
                _row(1954, 'Best Novel', 'Beat Not the Bones', 'Charlotte Jay', winner=True),
                _row(2026, 'Best Novel', 'The Big Empty', 'Robert Crais', winner=True),
                _row('', '', '', ''),
                _row(2026, 'The Grand Master', '', 'Donna Andrews', winner=True),
                _row(
                    2026,
                    'Best Episode in a TV Series',
                    'End of the Line',
                    'A. Author',
                    winner=True,
                ),
            ],
            total=6,
            per_page=100,
        )
        with patch.object(edgar, '_fetch_html', return_value=html):
            edgar.lookup('The Big Empty', 'Robert Crais')
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        titles = [item['work_title'] for item in payload['records']]
        self.assertNotIn('End of the Line', titles)
        self.assertNotIn('Donna Andrews', titles)
        authors = [item['work_author'] for item in payload['records']]
        self.assertNotIn('Donna Andrews', authors)

    def test_manual_refresh_clears_edgar_disk_and_ram_with_zero_http(self):
        archive = _minimal_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        edgar._archive_records_cache = archive
        cache.save_source_cache(
            'hugo',
            1,
            records=[{'title': 'hugo', 'year': 2020}],
            source_urls=['https://example.test/hugo'],
            coverage={'source': 'hugo'},
            ttl_seconds=3600,
            generated_at=datetime(2026, 1, 1, tzinfo=_UTC),
        )
        hugo._archive_records_cache = ()
        with patch.object(
            edgar, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            edgar, 'lookup', side_effect=AssertionError('lookup')
        ):
            self.assertTrue(refresh_award_source_cache('edgar'))
        self.assertFalse(self._disk_path().exists())
        self.assertIsNone(edgar._archive_records_cache)
        self.assertTrue((self.cache_dir / 'hugo.json').is_file())
        self.assertEqual(hugo._archive_records_cache, ())

    def test_future_nominee_only_year_does_not_promote_winner(self):
        archive = _minimal_archive(
            _record(2027, 'Future Nominee', 'Future Author', 'Best Novel', 'Nominee')
        )
        self.assertEqual(edgar._latest_year_state(archive), 'nominees')
        nominees_2027 = [
            record
            for record in archive
            if record.award_year == 2027
        ]
        self.assertEqual({record.status for record in nominees_2027}, {'Nominee'})
        _save_disk(archive, generated_at=datetime.now(_UTC))
        edgar._reset_runtime_state()
        with patch.object(edgar, '_load_live_archive', side_effect=AssertionError('live')):
            results = edgar.lookup('Future Nominee', 'Future Author')
        self.assertEqual(results[0].status, 'Nominee')

    def test_current_winner_state_year_is_complete_latest_state(self):
        archive = _minimal_archive()
        self.assertEqual(edgar._latest_year_state(archive), 'winner')
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        self.assertEqual(payload['coverage']['latest_year_state'], 'winner')
        self.assertEqual(payload['coverage']['max_year'], 2026)


def _blank_and_excluded() -> str:
    return (
        _row('', '', '', '')
        + _row(2026, 'The Grand Master', '', 'Donna Andrews', winner=True)
        + _row(
            2026,
            'Best Episode in a TV Series',
            'End of the Line',
            'A. Author',
            winner=True,
        )
    )


if __name__ == '__main__':
    unittest.main()
