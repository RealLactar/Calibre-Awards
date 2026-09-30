"""Offline coverage for the Wolfson History Prize all-winners archive."""

from __future__ import annotations

import io
import json
import unittest
import urllib.error
import urllib.request
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.sources import wolfson_history as wolfson

_UTC = timezone.utc

GRAND_STRATEGY = (
    'Grand Strategy, vol. IV: August 1942 \u2013 September 1943'
)
DECLINE_OF_MAGIC = (
    'Religion and the Decline of Magic: Studies in Popular Beliefs in '
    'Sixteenth and Seventeenth-Century England'
)
DEATH_IN_PARIS = 'Death in Paris , 1795-1801'
DEATH_IN_PARIS_AUTHOR = 'Richard Cobb'
BOUNDLESS_DEEP = (
    'The Boundless Deep: Young Tennyson, Science and the Crisis of Belief'
)
EUROPE_TITLE = 'Europe\u2019s War \u2013 A History'
EUROPE_AUTHOR = 'O\u2019Brien'
MEETINGS = 'Meetings with Remarkable Manuscripts'
MEETINGS_AUTHOR = 'Christopher de Hamel'


def _book(title: str, author: str, publisher: str = 'Example Press', *,
          br_inside_strong: bool = False) -> str:
    if br_inside_strong:
        return (
            f'<p><strong>{title}<br /></strong>{author}'
            f'<br />({publisher})</p>'
        )
    return (
        f'<p><strong>{title}</strong><br />{author}<br />({publisher})</p>'
    )


def _shorts(year: int, count: int) -> str:
    return ''.join(
        _book(f'Shortlist {year} {index}', f'Shortlist Author {year} {index}')
        for index in range(1, count + 1)
    )


def _year_html(year: int) -> str:
    if year == 1972:
        return (
            '<h5>1972</h5>'
            + _book(
                'Grand Strategy, vol. IV: August 1942 &#8211; September 1943',
                'Michael Howard',
                'HMSO',
            )
            + _book(DECLINE_OF_MAGIC, 'Keith Thomas', 'Weidenfeld &amp; Nicolson')
        )
    if year == 1979:
        return (
            '<h5>1979</h5>'
            + _book(DEATH_IN_PARIS, DEATH_IN_PARIS_AUTHOR)
            + _book('Second 1979 Winner', 'Second 1979 Author')
            + _book('Third 1979 Winner', 'Third 1979 Author')
        )
    if year == 2002:
        return (
            '<h5>2002</h5>'
            + _book('Facing the Ocean', 'Barry Cunliffe', 'Oxford University Press')
            + _book('London in the Twentieth Century', 'Jerry White', 'Viking')
            + '<p><strong>For distinguished contribution to the writing of '
            'history:</strong><br />Roy Jenkins</p>'
            + '<p><strong>For distinguished contribution to the writing of '
            'history<br /></strong>Christopher Bayly</p>'
        )
    if year == 2007:
        return (
            '<h5>2007</h5>'
            + _book('Winner 2007 1', 'Author 2007 1')
            + _book('Winner 2007 2', 'Author 2007 2')
            + _book('Winner 2007 3', 'Author 2007 3')
        )
    if year == 2016:
        return (
            '<h5>\u200b2016</h5>'
            + _book('Winner 2016 1', 'Author 2016 1', br_inside_strong=True)
            + _book('Winner 2016 2', 'Author 2016 2')
        )
    if year == 2017:
        winner = _book(MEETINGS, MEETINGS_AUTHOR, 'Allen Lane', br_inside_strong=True)
        return (
            '<h5>2017</h5>'
            + winner
            + '<p>Shortlist:</p>'
            + winner
            + _shorts(2017, 5)
        )
    if year == 2025:
        return (
            '<h5>2025</h5>'
            + _book('Winner 2025', 'Author 2025')
            + '<p>2025 Shortlist:</p>'
            + _shorts(2025, 5)
        )
    if year == 2026:
        return (
            '<h5>2026</h5>'
            + '<p>2026 Shortlist:</p>'
            + '<p><strong>The Boundless Deep:</strong> <strong>Young Tennyson, '
            'Science and the Crisis of Belief</strong><br />Richard Holmes'
            '<br />(William Collins)</p>'
            + '<p><strong>Europe&#8217;s War &#8211; A History</strong><br />'
            'O&#8217;Brien<br />(Smith &amp; Co)</p>'
            + _book('Smith &amp; Jones', 'Ada Author')
            + _shorts(2026, 3)
        )
    if year < 2017:
        return f'<h5>{year}</h5>' + _book(f'Winner {year}', f'Author {year}')
    return (
        f'<h5>{year}</h5>'
        + _book(f'Winner {year}', f'Author {year}')
        + f'<p>{year} Shortlist:</p>'
        + _shorts(year, 5)
    )


def _archive_page(inner: str) -> str:
    return (
        '<html><body><h5>Menu</h5>'
        '<div class="entry-content">'
        '<p>The Wolfson History Prize was first awarded in 1972.</p>'
        '<img src="cover.png" alt="" />'
        f'{inner}'
        '</div><h5>Footer</h5></body></html>'
    )


def _complete_inner() -> str:
    parts: list[str] = []
    for year in range(1972, 2027):
        if year == 1988:
            continue
        if year == 2016:
            parts.append('<h5></h5>')
        parts.append(_year_html(year))
        if year == 2016:
            parts.append('<p>&nbsp;</p>')
    return ''.join(parts)


COMPLETE_HTML = _archive_page(_complete_inner())
COMPLETE_RECORDS, COMPLETE_YEARS = wolfson._parse_archive_html(COMPLETE_HTML)


def _records_for(year: int, status: str | None = None) -> list:
    found = []
    for record in COMPLETE_RECORDS:
        if record.award_year != year:
            continue
        if status is not None and record.status != status:
            continue
        found.append(record)
    return found


class WolfsonArchiveParseTests(unittest.TestCase):
    def test_archive_validates_without_1988(self):
        wolfson._validate_archive(COMPLETE_RECORDS, COMPLETE_YEARS)
        self.assertNotIn(1988, COMPLETE_YEARS)
        self.assertIn(1972, COMPLETE_YEARS)
        self.assertEqual(COMPLETE_YEARS[-1], 2026)

    def test_1972_preserves_subtitle_en_dash_and_has_no_shortlist(self):
        winners = _records_for(1972, 'Winner')
        shortlisted = _records_for(1972, 'Shortlisted')
        self.assertEqual(len(winners), 2)
        self.assertEqual(shortlisted, [])
        grand = winners[0]
        self.assertEqual(grand.work_title, GRAND_STRATEGY)
        self.assertIn('\u2013', grand.work_title)
        self.assertNotIn('&#8211;', grand.work_title)
        self.assertEqual(grand.work_author, 'Michael Howard')
        self.assertNotIn('HMSO', grand.work_author)
        self.assertIsNone(grand.category)
        magic = winners[1]
        self.assertEqual(magic.work_title, DECLINE_OF_MAGIC)
        self.assertEqual(magic.work_author, 'Keith Thomas')
        self.assertNotIn('Weidenfeld', magic.work_author)
        self.assertNotIn('&', magic.work_author)
        for record in winners:
            self.assertEqual(record.source_url, wolfson.SOURCE_HOME_URL)

    def test_1979_keeps_three_winners_and_the_official_spaced_title(self):
        winners = _records_for(1979, 'Winner')
        self.assertEqual(len(winners), 3)
        self.assertEqual(_records_for(1979, 'Shortlisted'), [])
        self.assertEqual(winners[0].work_title, DEATH_IN_PARIS)
        self.assertIn(' , ', winners[0].work_title)
        self.assertEqual(
            [record.work_title for record in winners],
            [DEATH_IN_PARIS, 'Second 1979 Winner', 'Third 1979 Winner'],
        )

    def test_contribution_rows_are_skipped(self):
        winners = _records_for(2002, 'Winner')
        self.assertEqual(
            [record.work_author for record in winners],
            ['Barry Cunliffe', 'Jerry White'],
        )
        blob = ' '.join(record.work_title for record in COMPLETE_RECORDS)
        self.assertNotIn('distinguished contribution', blob.casefold())
        authors = {record.work_author for record in COMPLETE_RECORDS}
        self.assertNotIn('Roy Jenkins', authors)
        self.assertNotIn('Christopher Bayly', authors)

    def test_2016_is_winner_only(self):
        self.assertEqual(len(_records_for(2016, 'Winner')), 2)
        self.assertEqual(_records_for(2016, 'Shortlisted'), [])
        self.assertEqual(_records_for(2016, 'Winner')[0].work_author, 'Author 2016 1')

    def test_2017_has_one_winner_and_five_shortlisted(self):
        winners = _records_for(2017, 'Winner')
        shortlisted = _records_for(2017, 'Shortlisted')
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].work_title, MEETINGS)
        self.assertEqual(winners[0].work_author, MEETINGS_AUTHOR)
        self.assertEqual(len(shortlisted), 5)
        self.assertNotIn(MEETINGS, [record.work_title for record in shortlisted])

    def test_2025_completed_shortlist_year(self):
        self.assertEqual(len(_records_for(2025, 'Winner')), 1)
        self.assertEqual(len(_records_for(2025, 'Shortlisted')), 5)
        self.assertEqual(_records_for(2025, 'Winner')[0].work_title, 'Winner 2025')

    def test_2026_is_six_shortlisted_and_no_winner(self):
        self.assertEqual(_records_for(2026, 'Winner'), [])
        shortlisted = _records_for(2026, 'Shortlisted')
        self.assertEqual(len(shortlisted), 6)
        wolfson._validate_archive(COMPLETE_RECORDS, COMPLETE_YEARS)

    def test_split_strong_subtitle_is_one_title(self):
        titles = [record.work_title for record in _records_for(2026)]
        self.assertEqual(titles[0], BOUNDLESS_DEEP)
        self.assertEqual(_records_for(2026)[0].work_author, 'Richard Holmes')

    def test_html_entities_decode_and_publisher_stays_out_of_author(self):
        europe = _records_for(2026)[1]
        self.assertEqual(europe.work_title, EUROPE_TITLE)
        self.assertIn('\u2019', europe.work_title)
        self.assertIn('\u2013', europe.work_title)
        self.assertEqual(europe.work_author, EUROPE_AUTHOR)
        self.assertNotIn('Smith', europe.work_author)
        self.assertNotIn('&', europe.work_author)
        ampersand = _records_for(2026)[2]
        self.assertEqual(ampersand.work_title, 'Smith & Jones')
        self.assertEqual(ampersand.work_author, 'Ada Author')

    def test_duplicate_rows_collapse(self):
        html = _archive_page(
            '<h5>1972</h5>'
            + _book('Same Book', 'Same Author')
            + _book('Same Book', 'Same Author')
        )
        records, _years = wolfson._parse_archive_html(html)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].status, 'Winner')
        self.assertEqual(records[0].work_title, 'Same Book')

    def test_winner_precedes_shortlisted_for_the_same_work(self):
        html = _archive_page(
            '<h5>2017</h5>'
            + _book('Shared Title', 'Shared Author')
            + '<p>Shortlist:</p>'
            + _book('Shared Title', 'Shared Author')
            + _book('Other Shortlist', 'Other Author')
        )
        records, _years = wolfson._parse_archive_html(html)
        shared = [record for record in records if record.work_title == 'Shared Title']
        self.assertEqual(len(shared), 1)
        self.assertEqual(shared[0].status, 'Winner')
        self.assertEqual(shared[0].work_author, 'Shared Author')


class WolfsonValidationTests(unittest.TestCase):
    def test_no_year_headings_fail(self):
        _records, years = wolfson._parse_archive_html(
            _archive_page('<p>No years here.</p>')
        )
        with self.assertRaises(wolfson.WolfsonSourceError) as caught:
            wolfson._validate_archive(_records, years)
        self.assertIn('year headings', str(caught.exception))

    def test_missing_entry_content_fails(self):
        with self.assertRaises(wolfson.WolfsonSourceError) as caught:
            wolfson._parse_archive_html('<h5>1972</h5>' + _book('Title', 'Author'))
        self.assertIn('entry-content', str(caught.exception))

    def test_shortlist_label_before_2017_fails_during_parse(self):
        html = _archive_page(
            '<h5>2016</h5>'
            + _book('Winner 2016', 'Author 2016')
            + '<p>Shortlist:</p>'
        )
        with self.assertRaises(wolfson.WolfsonSourceError) as caught:
            wolfson._parse_archive_html(html)
        message = str(caught.exception)
        self.assertIn('2016', message)
        self.assertIn('shortlist label', message)
        self.assertIn('2017', message)

    def test_unexpected_heading_fails(self):
        html = _archive_page(_complete_inner() + '<h5>Judges</h5>')
        with self.assertRaises(wolfson.WolfsonSourceError) as caught:
            wolfson._parse_archive_html(html)
        self.assertIn('Judges', str(caught.exception))

    def test_missing_anchor_year_fails(self):
        records = tuple(
            record for record in COMPLETE_RECORDS if record.award_year != 1979
        )
        years = tuple(year for year in COMPLETE_YEARS if year != 1979)
        with self.assertRaises(wolfson.WolfsonSourceError) as caught:
            wolfson._validate_archive(records, years)
        self.assertIn('1979', str(caught.exception))

    def test_malformed_completed_shortlist_year_fails(self):
        records = tuple(
            record
            for record in COMPLETE_RECORDS
            if not (record.award_year == 2017 and record.status == 'Shortlisted')
        )
        with self.assertRaises(wolfson.WolfsonSourceError) as caught:
            wolfson._validate_archive(records, COMPLETE_YEARS)
        self.assertIn('2017', str(caught.exception))

    def test_newest_year_may_also_be_complete(self):
        shortlisted = _records_for(2026, 'Shortlisted')
        dropped = shortlisted[-1]
        winner = replace(
            dropped,
            status='Winner',
            work_title='Winner 2026',
            work_author='Author 2026',
        )
        records = tuple(
            record for record in COMPLETE_RECORDS if record != dropped
        ) + (winner,)
        wolfson._validate_archive(records, COMPLETE_YEARS)

    def test_present_1988_with_one_winner_is_accepted(self):
        extra = wolfson._ParsedRecord(
            award_year=1988,
            category=None,
            status='Winner',
            work_title='Winner 1988',
            work_author='Author 1988',
            source_url=wolfson.SOURCE_HOME_URL,
        )
        years = tuple(sorted(set(COMPLETE_YEARS) | {1988}))
        wolfson._validate_archive(COMPLETE_RECORDS + (extra,), years)

    def test_no_book_records_fail(self):
        with self.assertRaises(wolfson.WolfsonSourceError) as caught:
            wolfson._validate_archive((), COMPLETE_YEARS)
        self.assertIn('no book records', str(caught.exception))


class WolfsonLookupTests(unittest.TestCase):
    def setUp(self):
        wolfson._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        cache.set_cache_directory(Path(self._temp.name))

    def tearDown(self):
        wolfson._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _lookup(self, title: str, author: str, series: str | None = None):
        with patch.object(wolfson, '_fetch_html', return_value=COMPLETE_HTML):
            if series is None:
                return wolfson.lookup(title, author)
            return wolfson.lookup(title, author, series)

    def test_exact_winner_lookup(self):
        results = self._lookup(DECLINE_OF_MAGIC, 'Keith Thomas')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, DECLINE_OF_MAGIC)
        self.assertEqual(result.work_author, 'Keith Thomas')
        self.assertEqual(result.award_name, 'Wolfson History Prize')
        self.assertEqual(result.award_year, 1972)
        self.assertIsNone(result.category)
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'Wolfson History Prize')
        self.assertEqual(result.source_url, wolfson.SOURCE_HOME_URL)
        self.assertEqual(result.identity_kind, 'work')

    def test_exact_shortlisted_lookup(self):
        results = self._lookup(BOUNDLESS_DEEP, 'Richard Holmes')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Shortlisted')
        self.assertEqual(results[0].award_year, 2026)
        self.assertIsNone(results[0].category)
        self.assertIsNone(results[0].rank)

    def test_spaced_comma_matches_without_changing_display_title(self):
        results = self._lookup('Death in Paris, 1795-1801', DEATH_IN_PARIS_AUTHOR)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, DEATH_IN_PARIS)
        self.assertIn(' , ', results[0].work_title)
        self.assertIsNone(results[0].rank)

    def test_ampersand_title_matches_and(self):
        results = self._lookup('Smith and Jones', 'Ada Author', series='ignored')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'Smith & Jones')

    def test_wrong_author_and_wrong_title_miss(self):
        self.assertEqual(self._lookup(DEATH_IN_PARIS, 'Someone Else'), [])
        self.assertEqual(self._lookup('Not A Wolfson Book', DEATH_IN_PARIS_AUTHOR), [])

    def test_ranks_stay_absent_on_co_equal_winners(self):
        results = []
        for title, author in (
            (DEATH_IN_PARIS, DEATH_IN_PARIS_AUTHOR),
            ('Second 1979 Winner', 'Second 1979 Author'),
            ('Third 1979 Winner', 'Third 1979 Author'),
        ):
            results.extend(self._lookup(title, author))
        self.assertEqual(len(results), 3)
        self.assertEqual({result.rank for result in results}, {None})
        self.assertEqual({result.status for result in results}, {'Winner'})

    def test_empty_title_or_author_is_rejected(self):
        with self.assertRaises(ValueError):
            wolfson.lookup('  ', 'Keith Thomas')
        with self.assertRaises(ValueError):
            wolfson.lookup(DECLINE_OF_MAGIC, '  ')


class _FakeResponse:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body.encode('utf-8')
        self.exited = False

    def read(self) -> bytes:
        return self.body

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        self.exited = True
        return False


class WolfsonFetchTests(unittest.TestCase):
    def test_successful_response_returns_body_inside_with_block(self):
        response = _FakeResponse(200, '<html>ok</html>')
        seen = {}

        def _open(request, timeout=None):
            seen['url'] = request.full_url
            seen['ua'] = request.get_header('User-agent')
            seen['timeout'] = timeout
            return response

        with patch.object(urllib.request, 'urlopen', side_effect=_open):
            html = wolfson._fetch_html(wolfson.SOURCE_HOME_URL)
        self.assertEqual(html, '<html>ok</html>')
        self.assertEqual(seen['url'], wolfson.SOURCE_HOME_URL)
        self.assertIn('Chrome/122', seen['ua'])
        self.assertEqual(seen['timeout'], wolfson.TIMEOUT_SECONDS)
        self.assertTrue(response.exited)

    def test_http_500_includes_body_and_closes(self):
        fp = io.BytesIO(b'nope')
        http_error = urllib.error.HTTPError(
            wolfson.SOURCE_HOME_URL,
            500,
            'Error',
            hdrs=None,
            fp=fp,
        )
        with patch.object(urllib.request, 'urlopen', side_effect=http_error):
            with self.assertRaises(wolfson.WolfsonSourceError) as caught:
                wolfson._fetch_html(wolfson.SOURCE_HOME_URL)
        self.assertIn('HTTP 500', str(caught.exception))
        self.assertIn('nope', str(caught.exception))
        self.assertIs(caught.exception.__cause__, http_error)
        self.assertTrue(fp.closed)

    def test_http_error_closes_when_body_read_fails(self):
        fp = io.BytesIO(b'nope')
        http_error = urllib.error.HTTPError(
            wolfson.SOURCE_HOME_URL,
            500,
            'Error',
            hdrs=None,
            fp=fp,
        )
        with patch.object(urllib.request, 'urlopen', side_effect=http_error):
            with patch.object(
                wolfson,
                '_read_response_body',
                side_effect=OSError('unreadable body'),
            ):
                with self.assertRaises(OSError):
                    wolfson._fetch_html(wolfson.SOURCE_HOME_URL)
        self.assertTrue(fp.closed)

    def test_url_error_becomes_source_error(self):
        url_error = urllib.error.URLError('offline')
        with patch.object(urllib.request, 'urlopen', side_effect=url_error):
            with self.assertRaises(wolfson.WolfsonSourceError) as caught:
                wolfson._fetch_html(wolfson.SOURCE_HOME_URL)
        self.assertIn('offline', str(caught.exception))
        self.assertIs(caught.exception.__cause__, url_error)

    def test_non_200_response_becomes_source_error(self):
        response = _FakeResponse(203, '<html></html>')
        with patch.object(urllib.request, 'urlopen', return_value=response):
            with self.assertRaises(wolfson.WolfsonSourceError) as caught:
                wolfson._fetch_html(wolfson.SOURCE_HOME_URL)
        self.assertIn('HTTP 203', str(caught.exception))
        self.assertTrue(response.exited)


def _save_disk(records, *, generated_at=None, ttl_seconds=None, version=None):
    cache.save_source_cache(
        wolfson.SOURCE_KEY,
        wolfson.CACHE_VERSION if version is None else version,
        records=[wolfson._record_to_cache_dict(record) for record in records],
        source_urls=wolfson._archive_source_urls(),
        coverage=wolfson._coverage_from_records(records),
        ttl_seconds=(
            wolfson.CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


class WolfsonCacheTests(unittest.TestCase):
    def setUp(self):
        wolfson._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        wolfson._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _disk_path(self):
        return self.cache_dir / 'wolfson_history.json'

    def _rewrite_records(self, mutate):
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        mutate(payload)
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )

    def test_cache_identity_constants(self):
        self.assertEqual(wolfson.SOURCE_KEY, 'wolfson_history')
        self.assertEqual(wolfson.CACHE_VERSION, 1)
        self.assertEqual(wolfson.CACHE_BASE_TTL_SECONDS, 7 * 24 * 60 * 60)
        self.assertEqual(wolfson.CACHE_REFRESH_OFFSET_SECONDS, 20 * 60 * 60)
        self.assertEqual(
            wolfson.CACHE_TTL_SECONDS,
            wolfson.CACHE_BASE_TTL_SECONDS + wolfson.CACHE_REFRESH_OFFSET_SECONDS,
        )

    def test_parsed_record_round_trips_and_omits_rank(self):
        original = _records_for(1972, 'Winner')[0]
        payload = wolfson._record_to_cache_dict(original)
        self.assertNotIn('rank', payload)
        self.assertIsNone(payload['category'])
        self.assertEqual(set(payload), set(wolfson._RECORD_CACHE_FIELDS))
        self.assertEqual(wolfson._record_from_cache_dict(payload), original)
        _save_disk(COMPLETE_RECORDS, generated_at=datetime.now(_UTC))
        loaded = wolfson._load_persistent_archive()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded[0], COMPLETE_RECORDS)

    def test_wrong_version_is_rejected(self):
        _save_disk(COMPLETE_RECORDS, version=2, generated_at=datetime.now(_UTC))
        self.assertIsNone(wolfson._load_persistent_archive())

    def test_malformed_status_and_fields_are_rejected(self):
        _save_disk(COMPLETE_RECORDS, generated_at=datetime.now(_UTC))
        self._rewrite_records(
            lambda payload: payload['records'][0].__setitem__('status', 'Nominee')
        )
        self.assertIsNone(wolfson._load_persistent_archive())
        _save_disk(COMPLETE_RECORDS, generated_at=datetime.now(_UTC))
        self._rewrite_records(
            lambda payload: payload['records'][0].__setitem__('rank', 1)
        )
        self.assertIsNone(wolfson._load_persistent_archive())
        _save_disk(COMPLETE_RECORDS, generated_at=datetime.now(_UTC))
        self._rewrite_records(
            lambda payload: payload['records'][0].__setitem__('category', 'History')
        )
        self.assertIsNone(wolfson._load_persistent_archive())

    def test_fresh_cache_lookup_makes_zero_network_calls(self):
        _save_disk(COMPLETE_RECORDS, generated_at=datetime.now(_UTC))
        wolfson._reset_runtime_state()
        with patch.object(
            wolfson, '_load_live_archive', side_effect=AssertionError('live')
        ):
            results = wolfson.lookup(DECLINE_OF_MAGIC, 'Keith Thomas')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Winner')
        self.assertIsNone(results[0].rank)

    def test_stale_cache_without_refresh_slot_skips_network(self):
        _save_disk(
            COMPLETE_RECORDS,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        wolfson._reset_runtime_state()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                wolfson, '_load_live_archive', side_effect=AssertionError('live')
            ):
                results = wolfson.lookup(DECLINE_OF_MAGIC, 'Keith Thomas')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].award_year, 1972)

    def test_failed_optional_refresh_keeps_stale_archive(self):
        _save_disk(
            COMPLETE_RECORDS,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        with patch.object(
            wolfson,
            '_load_live_archive',
            side_effect=wolfson.WolfsonSourceError('archive down'),
        ):
            results = wolfson.lookup(BOUNDLESS_DEEP, 'Richard Holmes')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Shortlisted')
        self.assertEqual(self._disk_path().read_text(encoding='utf-8'), original)

    def test_reset_clears_ram_and_leaves_disk(self):
        _save_disk(COMPLETE_RECORDS, generated_at=datetime.now(_UTC))
        with patch.object(
            wolfson, '_load_live_archive', side_effect=AssertionError('live')
        ):
            wolfson.lookup(DECLINE_OF_MAGIC, 'Keith Thomas')
        self.assertIsNotNone(wolfson._archive_records_cache)
        wolfson._reset_runtime_state()
        self.assertIsNone(wolfson._archive_records_cache)
        self.assertTrue(self._disk_path().is_file())
        with patch.object(
            wolfson, '_load_live_archive', side_effect=AssertionError('live')
        ):
            results = wolfson.lookup(DECLINE_OF_MAGIC, 'Keith Thomas')
        self.assertEqual(results[0].work_author, 'Keith Thomas')


if __name__ == '__main__':
    unittest.main()
