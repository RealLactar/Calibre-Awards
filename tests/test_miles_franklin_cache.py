"""Offline coverage for Miles Franklin persistent parsed-archive cache."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.cache_control import refresh_award_source_cache
from awards.sources import hugo, miles_franklin as mf, pulitzer

_UTC = timezone.utc


def _record(year, title, author, status='Winner'):
    return mf._ParsedRecord(
        award_year=year,
        category=mf.CATEGORY,
        status=status,
        work_title=title,
        work_author=author,
        source_url=mf.HISTORY_URL,
    )


def _complete_archive(*, current_year=None, extra=(), include_current=None):
    if current_year is None:
        current_year = mf._current_calendar_year()
    records = []
    for year in range(mf.ARCHIVE_MIN_YEAR, current_year):
        if year == 2007:
            records.append(_record(year, 'Carpentaria', 'Alexis Wright'))
            records.append(
                _record(year, 'Theft: A Love Story', 'Peter Carey', 'Finalist')
            )
        elif year == 2025:
            records.append(_record(year, 'Ghost Cities', 'Siang Lu'))
        else:
            records.append(
                _record(year, f'Stub Winner {year}', f'Stub Author {year}')
            )
            records.append(
                _record(
                    year,
                    f'Stub Finalist Work {year}',
                    f'Stub Finalist {year}',
                    'Finalist',
                )
            )
    if include_current == 'winner':
        records.append(_record(current_year, 'Fierceland', 'Omar Musa'))
        records.append(
            _record(current_year, 'Discipline', 'Randa Abdel-Fattah', 'Finalist')
        )
    elif include_current == 'shortlist':
        records.append(
            _record(current_year, 'Discipline', 'Randa Abdel-Fattah', 'Finalist')
        )
    records.extend(extra)
    return tuple(records)


def _save_disk(records, *, generated_at=None, ttl_seconds=None, version=None, heading=None):
    cache.save_source_cache(
        mf.SOURCE_KEY,
        mf.CACHE_VERSION if version is None else version,
        records=[mf._record_to_cache_dict(record) for record in records],
        source_urls=mf._archive_source_urls(),
        coverage=mf._coverage_from_records(records, current_year_heading=heading),
        ttl_seconds=(
            mf.CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


class MilesFranklinPersistentCacheTests(unittest.TestCase):
    def setUp(self):
        mf._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        mf._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _disk_path(self):
        return self.cache_dir / 'miles_franklin.json'

    def _rewrite(self, mutate):
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        mutate(payload)
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )

    def _assert_wright(self, results):
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, 'Carpentaria')
        self.assertEqual(result.work_author, 'Alexis Wright')
        self.assertEqual(result.award_name, 'Miles Franklin Literary Award')
        self.assertEqual(result.award_year, 2007)
        self.assertEqual(result.category, 'Fiction')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'Miles Franklin Literary Award')
        self.assertEqual(result.source_url, mf.HISTORY_URL)
        self.assertIsNone(result.notes)
        self.assertEqual(result.identity_kind, 'work')

    def test_cache_identity_constants(self):
        self.assertEqual(mf.SOURCE_KEY, 'miles_franklin')
        self.assertEqual(mf.CACHE_VERSION, 1)
        self.assertEqual(mf.CACHE_BASE_TTL_SECONDS, 7 * 24 * 60 * 60)
        self.assertEqual(mf.CACHE_REFRESH_OFFSET_SECONDS, 9 * 60 * 60)
        self.assertEqual(
            mf.CACHE_TTL_SECONDS,
            mf.CACHE_BASE_TTL_SECONDS + mf.CACHE_REFRESH_OFFSET_SECONDS,
        )
        self.assertEqual(mf.CACHE_TTL_SECONDS, 637200)

    def test_complete_archive_helper_passes_source_validation(self):
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            mf._validate_cached_archive(_complete_archive(current_year=2026))

    def test_parsed_record_round_trips_all_fields(self):
        original = _record(2007, 'Carpentaria', 'Alexis Wright')
        restored = mf._record_from_cache_dict(mf._record_to_cache_dict(original))
        self.assertEqual(restored, original)
        finalist = _record(
            2007, 'Theft: A Love Story', 'Peter Carey', 'Finalist'
        )
        self.assertEqual(
            mf._record_from_cache_dict(mf._record_to_cache_dict(finalist)),
            finalist,
        )

    def test_rank_query_and_html_are_not_persisted(self):
        payload = mf._record_to_cache_dict(
            _record(2007, 'Carpentaria', 'Alexis Wright')
        )
        self.assertNotIn('rank', payload)
        self.assertNotIn('html', payload)
        self.assertNotIn('qualification', payload)
        self.assertNotIn('query_title', payload)
        self.assertEqual(set(payload), set(mf._RECORD_CACHE_FIELDS))

    def test_live_validated_archive_writes_miles_franklin_json(self):
        archive = _complete_archive(current_year=2026)
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            with patch.object(mf, '_load_live_archive', return_value=archive):
                results = mf.lookup('Carpentaria', 'Alexis Wright')
        self._assert_wright(results)
        self.assertTrue(self._disk_path().is_file())
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        self.assertEqual(payload['source_key'], 'miles_franklin')
        self.assertEqual(payload['source_urls'], [mf.HISTORY_URL])
        self.assertNotIn('<html', json.dumps(payload))
        self.assertGreater(payload['record_count'], 0)
        self.assertEqual(payload['coverage']['current_year'], 2026)

    def test_fresh_cache_lookup_makes_zero_network_calls(self):
        archive = _complete_archive(current_year=2026)
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC))
            mf._reset_runtime_state()
            with patch.object(
                mf, '_fetch_html', side_effect=AssertionError('network')
            ), patch.object(
                mf, '_load_live_archive', side_effect=AssertionError('live')
            ):
                results = mf.lookup('Carpentaria', 'Alexis Wright')
        self._assert_wright(results)

    def test_ram_reset_plus_fresh_disk_makes_zero_http(self):
        archive = _complete_archive(current_year=2026)
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            with patch.object(mf, '_load_live_archive', return_value=archive) as live:
                first = mf.lookup('Carpentaria', 'Alexis Wright')
            self._assert_wright(first)
            self.assertEqual(live.call_count, 1)
            mf._reset_runtime_state()
            self.assertTrue(self._disk_path().is_file())
            with patch.object(
                mf, '_fetch_html', side_effect=AssertionError('network')
            ), patch.object(
                mf, '_load_live_archive', side_effect=AssertionError('live')
            ):
                second = mf.lookup('Carpentaria', 'Alexis Wright')
        self._assert_wright(second)

    def test_stale_cache_successful_refresh_replaces_disk(self):
        stale = _complete_archive(current_year=2026)
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            _save_disk(
                stale,
                generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
                ttl_seconds=60,
            )
            original_generated = json.loads(
                self._disk_path().read_text(encoding='utf-8')
            )['generated_at']
            refreshed = stale + (
                _record(2026, 'Fierceland', 'Omar Musa'),
            )
            with cache.lookup_refresh_budget():
                with patch.object(mf, '_load_live_archive', return_value=refreshed):
                    results = mf.lookup('Carpentaria', 'Alexis Wright')
            self._assert_wright(results)
            updated = json.loads(self._disk_path().read_text(encoding='utf-8'))
            self.assertNotEqual(updated['generated_at'], original_generated)
            extra = mf.lookup('Fierceland', 'Omar Musa')
            self.assertEqual(len(extra), 1)
            self.assertEqual(extra[0].status, 'Winner')

    def test_stale_cache_live_failure_keeps_file_unchanged(self):
        stale = _complete_archive(current_year=2026)
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            _save_disk(
                stale,
                generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
                ttl_seconds=60,
            )
            original = self._disk_path().read_text(encoding='utf-8')
            with cache.lookup_refresh_budget():
                with patch.object(
                    mf,
                    '_load_live_archive',
                    side_effect=mf.MilesFranklinSourceError('archive down'),
                ):
                    results = mf.lookup('Carpentaria', 'Alexis Wright')
            self._assert_wright(results)
            self.assertEqual(self._disk_path().read_text(encoding='utf-8'), original)

    def test_stale_cache_without_refresh_slot_uses_stale_and_skips_network(self):
        stale = _complete_archive(current_year=2026)
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            _save_disk(
                stale,
                generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
                ttl_seconds=60,
            )
            mf._reset_runtime_state()
            with cache.lookup_refresh_budget():
                self.assertTrue(cache.try_claim_stale_refresh())
                with patch.object(
                    mf, '_load_live_archive', side_effect=AssertionError('live')
                ) as mocked, patch.object(
                    mf, '_fetch_html', side_effect=AssertionError('network')
                ):
                    results = mf.lookup('Carpentaria', 'Alexis Wright')
                mocked.assert_not_called()
        self._assert_wright(results)

    def test_missing_cache_requires_live(self):
        self.assertFalse(self._disk_path().is_file())
        live = _complete_archive(current_year=2026)
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            with patch.object(mf, '_load_live_archive', return_value=live) as mocked:
                results = mf.lookup('Carpentaria', 'Alexis Wright')
            self.assertEqual(mocked.call_count, 1)
        self._assert_wright(results)

    def test_malformed_live_does_not_write_cache(self):
        self.assertFalse(self._disk_path().is_file())
        with patch.object(
            mf, '_fetch_html', return_value='<html><h1>Unrelated</h1></html>'
        ):
            with self.assertRaises(mf.MilesFranklinSourceError):
                mf.lookup('Carpentaria', 'Alexis Wright')
        self.assertFalse(self._disk_path().is_file())

    def test_malformed_disk_requires_live(self):
        archive = _complete_archive(current_year=2026)
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC))
            self._rewrite(
                lambda payload: payload['records'][0].__setitem__('award_year', 0)
            )
            live = _complete_archive(current_year=2026)
            with patch.object(mf, '_load_live_archive', return_value=live) as mocked:
                mf.lookup('Carpentaria', 'Alexis Wright')
            self.assertEqual(mocked.call_count, 1)

    def test_version_mismatch_uses_live_path(self):
        archive = _complete_archive(current_year=2026)
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC), version=2)
            live = _complete_archive(current_year=2026)
            with patch.object(mf, '_load_live_archive', return_value=live) as mocked:
                results = mf.lookup('Carpentaria', 'Alexis Wright')
            self.assertEqual(mocked.call_count, 1)
        self._assert_wright(results)

    def test_completed_year_missing_winner_is_rejected(self):
        archive = [
            record
            for record in _complete_archive(current_year=2026)
            if not (record.award_year == 2010 and record.status == 'Winner')
        ]
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            with self.assertRaises(mf.MilesFranklinSourceError) as raised:
                mf._validate_cached_archive(tuple(archive))
            self.assertIn('2010', str(raised.exception))
            cache.save_source_cache(
                mf.SOURCE_KEY,
                mf.CACHE_VERSION,
                records=[mf._record_to_cache_dict(record) for record in archive],
                source_urls=mf._archive_source_urls(),
                coverage={'winner_count': 0},
                ttl_seconds=mf.CACHE_TTL_SECONDS,
                generated_at=datetime.now(_UTC),
            )
            live = _complete_archive(current_year=2026)
            with patch.object(mf, '_load_live_archive', return_value=live) as mocked:
                results = mf.lookup('Carpentaria', 'Alexis Wright')
            self.assertEqual(mocked.call_count, 1)
        self._assert_wright(results)

    def test_current_year_states_are_valid(self):
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            absent = _complete_archive(current_year=2026)
            mf._validate_cached_archive(absent)
            self.assertEqual(
                mf._coverage_from_records(absent)['current_year_state'],
                'absent',
            )
            longlist = absent
            coverage = mf._coverage_from_records(
                longlist, current_year_heading=True
            )
            self.assertEqual(coverage['current_year_state'], 'longlist')
            shortlist = _complete_archive(
                current_year=2026, include_current='shortlist'
            )
            mf._validate_cached_archive(shortlist)
            self.assertEqual(
                mf._coverage_from_records(shortlist)['current_year_state'],
                'shortlist',
            )
            winner = _complete_archive(
                current_year=2026, include_current='winner'
            )
            mf._validate_cached_archive(winner)
            self.assertEqual(
                mf._coverage_from_records(winner)['current_year_state'],
                'winner',
            )

    def test_january_rollover_invalidates_incomplete_prior_year(self):
        incomplete = _complete_archive(
            current_year=2026, include_current='shortlist'
        )
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            _save_disk(incomplete, generated_at=datetime.now(_UTC))
            mf._validate_cached_archive(
                incomplete,
                json.loads(self._disk_path().read_text(encoding='utf-8'))['coverage'],
            )
        live = _complete_archive(current_year=2027, include_current='absent')
        # 2027 archive needs 2026 winner
        live = _complete_archive(current_year=2027) + (
            _record(2026, 'Fierceland', 'Omar Musa'),
        )
        with patch.object(mf, '_current_calendar_year', return_value=2027):
            mf._reset_runtime_state()
            with patch.object(mf, '_load_live_archive', return_value=live) as mocked:
                results = mf.lookup('Carpentaria', 'Alexis Wright')
            self.assertEqual(mocked.call_count, 1)
        self._assert_wright(results)

    def test_zero_labeled_finalists_in_a_completed_year_is_valid(self):
        archive = [
            record
            for record in _complete_archive(current_year=2026)
            if record.award_year != 2025 or record.status == 'Winner'
        ]
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            mf._validate_cached_archive(tuple(archive))

    def test_manual_refresh_removes_miles_franklin_json_and_ram_only(self):
        archive = _complete_archive(current_year=2026)
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC))
        mf._archive_records_cache = archive
        hugo._archive_records_cache = ()
        cache.save_source_cache(
            'hugo',
            1,
            records=[{'title': 'hugo', 'year': 2020}],
            source_urls=['https://example.test/hugo'],
            coverage={'source': 'hugo'},
            ttl_seconds=3600,
            generated_at=datetime(2026, 1, 1, tzinfo=_UTC),
        )
        pulitzer_path = self.cache_dir / 'pulitzer.json'
        cache.save_source_cache(
            'pulitzer',
            1,
            records=[{'title': 'pulitzer', 'year': 2020}],
            source_urls=['https://example.test/pulitzer'],
            coverage={'source': 'pulitzer'},
            ttl_seconds=3600,
            generated_at=datetime(2026, 1, 1, tzinfo=_UTC),
        )
        with patch.object(
            mf, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            mf, '_load_live_archive', side_effect=AssertionError('live')
        ):
            self.assertTrue(refresh_award_source_cache('miles_franklin'))
        self.assertFalse(self._disk_path().exists())
        self.assertIsNone(mf._archive_records_cache)
        self.assertTrue((self.cache_dir / 'hugo.json').is_file())
        self.assertTrue(pulitzer_path.is_file())
        self.assertEqual(hugo._archive_records_cache, ())

    def test_manual_refresh_makes_zero_http(self):
        archive = _complete_archive(current_year=2026)
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC))
        mf._archive_records_cache = archive
        with patch.object(
            mf, '_fetch_html', side_effect=AssertionError('network')
        ) as fetch, patch.object(
            mf, 'lookup', side_effect=AssertionError('lookup')
        ):
            self.assertTrue(refresh_award_source_cache('miles_franklin'))
        fetch.assert_not_called()

    def test_ram_reset_does_not_delete_disk_cache(self):
        archive = _complete_archive(current_year=2026)
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC))
            mf._archive_records_cache = archive
            self.assertTrue(self._disk_path().is_file())
            mf._reset_runtime_state()
            self.assertTrue(self._disk_path().is_file())
            self.assertIsNone(mf._archive_records_cache)
            with patch.object(
                mf, '_load_live_archive', side_effect=AssertionError('live')
            ), patch.object(
                mf, '_fetch_html', side_effect=AssertionError('network')
            ):
                results = mf.lookup('Carpentaria', 'Alexis Wright')
        self._assert_wright(results)


if __name__ == '__main__':
    unittest.main()
