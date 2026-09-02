"""Offline coverage for Romantic Novel of the Year Awards keyed caches."""

from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.cache_control import refresh_award_source_cache
from awards.sources import edgar, hugo, romantic_novel_awards as src
from tests.test_romantic_novel_awards_parser import (
    ARCHIVE,
    NEWS_CAT_ID,
    SHORTLIST_2018,
    SHORTLIST_2020,
    SHORTLIST_2026,
    WINNERS_2026,
    LookupIntegrationTests,
    _card,
    _news_item,
    _taxonomy_payload,
    archive_html,
)

_UTC = timezone.utc
_STALE_AT = datetime(2020, 1, 1, tzinfo=_UTC)


def _entry_path(cache_dir: Path, entry_kind: str, entry_key: str) -> Path:
    digest = hashlib.sha256(entry_key.encode('utf-8')).hexdigest()
    return cache_dir / src.SOURCE_KEY / entry_kind / f'{digest}.json'


def _record(year, title, author, category=None, status='Winner', slug=None):
    if slug is None:
        slug = title.casefold().replace(' ', '-')
    source_url = (
        f'{ARCHIVE}/{slug}'
        if status == 'Winner'
        else SHORTLIST_2026
    )
    if year == 2018 and status == 'Shortlisted':
        source_url = SHORTLIST_2018
    return src._ParsedRecord(
        award_year=year,
        category=category,
        status=status,
        work_title=title,
        work_author=author,
        source_url=source_url,
    )


def _save_winners(records, *, generated_at=None, ttl_seconds=None, urls=None):
    cache.save_cache_entry(
        src.SOURCE_KEY,
        src.WINNERS_ENTRY_KIND,
        src.WINNERS_ENTRY_KEY,
        src.WINNERS_CACHE_VERSION,
        records=[src._record_to_cache_dict(record) for record in records],
        source_urls=urls or [ARCHIVE],
        coverage={
            'min_year': min((record.award_year for record in records), default=None),
            'max_year': max((record.award_year for record in records), default=None),
            'record_count': len(records),
        },
        ttl_seconds=(
            src.HISTORICAL_CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _save_news_index(posts, *, generated_at=None, ttl_seconds=None, category_id=NEWS_CAT_ID):
    cache.save_cache_entry(
        src.SOURCE_KEY,
        src.NEWS_INDEX_ENTRY_KIND,
        src.NEWS_INDEX_ENTRY_KEY,
        src.NEWS_INDEX_CACHE_VERSION,
        records=[
            {
                'post_id': post.post_id,
                'award_year': post.award_year,
                'kind': post.kind,
                'url': post.url,
                'slug': post.slug,
                'title': post.title,
                'date': post.date,
                'combined': post.combined,
            }
            for post in posts
        ],
        source_urls=[src.NEWS_CATEGORIES_REST_URL, src.NEWS_REST_URL],
        coverage={'category_id': category_id, 'post_count': len(posts)},
        ttl_seconds=(
            src.CURRENT_CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _save_year(snapshot, *, generated_at=None, ttl_seconds=None):
    cache.save_cache_entry(
        src.SOURCE_KEY,
        src.YEAR_ENTRY_KIND,
        str(snapshot.award_year),
        src.YEAR_CACHE_VERSION,
        records=[src._record_to_cache_dict(record) for record in snapshot.records],
        source_urls=list(snapshot.source_urls),
        coverage={
            'award_year': snapshot.award_year,
            'state': snapshot.state,
        },
        ttl_seconds=(
            src._year_ttl_seconds(snapshot.award_year, snapshot.state)
            if ttl_seconds is None
            else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _classified_posts():
    raw = [
        _news_item(1, 'RNA reveals 2026 shortlists', 'rna-reveals-2026-shortlists', '2026-02-01', 2026),
        _news_item(2, 'RNA announces the 2026 winners', 'rna-announces-the-2026-winners', '2026-03-01', 2026),
        _news_item(3, '2018 RoNA shortlists announced', '2018-rona-shortlists-announced', '2018-02-01', 2018),
        _news_item(4, 'RNA announces 2020 shortlists', 'rna-announces-2020-shortlists', '2020-02-01', 2020),
    ]
    return src._news_index_from_posts(NEWS_CAT_ID, raw).posts


def _minimal_winners():
    return (
        _record(1960, 'More Than Friendship', 'Mary Howard'),
        _record(2008, 'Pillow Talk', 'Freya North', slug='pillow-talk'),
        _record(2018, 'This Love', 'Dani Atkins'),
        _record(
            2020,
            'The Flatshare',
            "Beth O'Leary",
            'Debut Romantic Novel',
        ),
        _record(
            2020,
            'The Flatshare',
            "Beth O'Leary",
            'Popular Romantic Fiction',
        ),
        _record(
            2026,
            'Any Trope But You',
            'Victoria Lavine',
            'The Debut Romantic Novel Award',
        ),
    )


def _year_2026():
    return src._YearSnapshot(
        award_year=2026,
        state='winner',
        source_urls=(SHORTLIST_2026, WINNERS_2026),
        records=(
            _record(
                2026,
                'Any Trope But You',
                'Victoria Lavine',
                'Debut Romance Novel Award',
            ),
            _record(
                2026,
                'Onyx Storm',
                'Rebecca Yarros',
                'Romantasy/Romantic Fantasy Award',
                'Shortlisted',
            ),
            _record(
                2026,
                'An Almost Perfect Summer',
                'Jill Mansell',
                'The Romance Bestseller Award',
            ),
        ),
    )


def _year_2018():
    return src._YearSnapshot(
        award_year=2018,
        state='shortlisted',
        source_urls=(SHORTLIST_2018,),
        records=(
            _record(
                2018,
                'This Love',
                'Dani Atkins',
                'Epic Romantic Novel',
                'Shortlisted',
            ),
        ),
    )


def _year_2020():
    return src._YearSnapshot(
        award_year=2020,
        state='winner',
        source_urls=(SHORTLIST_2020,),
        records=(
            _record(
                2020,
                'The Flatshare',
                "Beth O'Leary",
                'Debut Romantic Novel',
                'Winner',
            ),
            _record(
                2020,
                'The Flatshare',
                "Beth O'Leary",
                'Popular Romantic Fiction',
                'Winner',
            ),
        ),
    )


class RomanticNovelAwardsCacheTests(unittest.TestCase):
    def setUp(self):
        src._reset_runtime_state()
        edgar._reset_runtime_state()
        hugo._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        src._reset_runtime_state()
        edgar._reset_runtime_state()
        hugo._reset_runtime_state()
        cache._reset_runtime_state()
        cache.set_cache_directory(None)
        self._temp.cleanup()

    def _seed_all_fresh(self):
        _save_winners(_minimal_winners())
        _save_news_index(_classified_posts())
        _save_year(_year_2018())
        _save_year(_year_2020())
        _save_year(_year_2026())

    def test_cache_identity_and_plus_18h(self):
        self.assertEqual(src.SOURCE_KEY, 'romantic_novel_awards')
        self.assertEqual(src.CACHE_REFRESH_OFFSET_SECONDS, 18 * 60 * 60)
        self.assertEqual(
            src.CURRENT_CACHE_TTL_SECONDS,
            src.CACHE_BASE_TTL_SECONDS + src.CACHE_REFRESH_OFFSET_SECONDS,
        )
        self.assertEqual(src.CURRENT_CACHE_TTL_SECONDS, 669600)
        self.assertEqual(src.HISTORICAL_CACHE_TTL_SECONDS, 180 * 24 * 60 * 60)
        from awards.sources import (
            booker,
            bram_stoker,
            edgar as edgar_src,
            german_book_prize,
            hugo as hugo_src,
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
            hugo_src.CACHE_REFRESH_OFFSET_SECONDS,
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
            edgar_src.CACHE_REFRESH_OFFSET_SECONDS,
        }
        self.assertNotIn(18 * 60 * 60, offsets)
        self.assertEqual(edgar_src.CACHE_REFRESH_OFFSET_SECONDS, 17 * 60 * 60)

    def test_cold_winners_archive_writes_parsed_cache(self):
        helper = LookupIntegrationTests()
        html_calls = []
        json_calls = []

        def fetch_html(url):
            html_calls.append(url)
            return helper._fetch_html(url)

        def fetch_json(url):
            json_calls.append(url)
            return helper._fetch_json(url)

        with patch.object(src, '_fetch_html', side_effect=fetch_html), patch.object(
            src, '_fetch_json', side_effect=fetch_json
        ), patch.object(src, '_current_calendar_year', return_value=2026):
            results = src.lookup('More Than Friendship', 'Mary Howard')
        self.assertEqual(len(results), 1)
        path = _entry_path(self.cache_dir, src.WINNERS_ENTRY_KIND, src.WINNERS_ENTRY_KEY)
        self.assertTrue(path.is_file())
        payload = json.loads(path.read_text(encoding='utf-8'))
        blob = json.dumps(payload)
        self.assertNotIn('<h2>', blob)
        self.assertNotIn('post-type-archive', blob)
        titles = {item['work_title'] for item in payload['records']}
        self.assertIn('More Than Friendship', titles)
        self.assertIn('Pillow Talk', titles)
        self.assertNotIn('Untagged Unknown', titles)
        self.assertNotIn('Love & Other Liabilities', titles)
        news_path = _entry_path(
            self.cache_dir, src.NEWS_INDEX_ENTRY_KIND, src.NEWS_INDEX_ENTRY_KEY
        )
        news_payload = json.loads(news_path.read_text(encoding='utf-8'))
        news_blob = json.dumps(news_payload)
        self.assertNotIn('_embed', news_blob)
        self.assertNotIn('"rendered"', news_blob)
        self.assertTrue(html_calls)
        self.assertTrue(json_calls)

    def test_fresh_caches_mean_zero_http_after_ram_reset(self):
        helper = LookupIntegrationTests()
        with patch.object(src, '_fetch_html', side_effect=helper._fetch_html), patch.object(
            src, '_fetch_json', side_effect=helper._fetch_json
        ), patch.object(src, '_current_calendar_year', return_value=2026):
            src.lookup('Any Trope But You', 'Victoria Lavine')
        src._reset_runtime_state()
        with patch.object(
            src, '_fetch_html', side_effect=AssertionError('html')
        ), patch.object(
            src, '_fetch_json', side_effect=AssertionError('json')
        ), patch.object(src, '_current_calendar_year', return_value=2026):
            second = src.lookup('Any Trope But You', 'Victoria Lavine')
        self.assertEqual(second[0].status, 'Winner')

    def test_winners_use_historical_ttl(self):
        _save_winners(_minimal_winners())
        payload = cache.load_cache_entry(
            src.SOURCE_KEY,
            src.WINNERS_ENTRY_KIND,
            src.WINNERS_ENTRY_KEY,
            src.WINNERS_CACHE_VERSION,
        )
        self.assertEqual(payload['ttl_seconds'], src.HISTORICAL_CACHE_TTL_SECONDS)

    def test_news_index_ttl_includes_plus_18h(self):
        _save_news_index(_classified_posts())
        payload = cache.load_cache_entry(
            src.SOURCE_KEY,
            src.NEWS_INDEX_ENTRY_KIND,
            src.NEWS_INDEX_ENTRY_KEY,
            src.NEWS_INDEX_CACHE_VERSION,
        )
        self.assertEqual(payload['ttl_seconds'], src.CURRENT_CACHE_TTL_SECONDS)
        self.assertEqual(
            payload['ttl_seconds'],
            7 * 24 * 60 * 60 + 18 * 60 * 60,
        )

    def test_completed_year_uses_historical_ttl(self):
        with patch.object(src, '_current_calendar_year', return_value=2026):
            self.assertEqual(
                src._year_ttl_seconds(2020, 'winner'),
                src.HISTORICAL_CACHE_TTL_SECONDS,
            )
            self.assertEqual(
                src._year_ttl_seconds(2026, 'winner'),
                src.CURRENT_CACHE_TTL_SECONDS,
            )
            self.assertEqual(
                src._year_ttl_seconds(2025, 'shortlisted'),
                src.CURRENT_CACHE_TTL_SECONDS,
            )

    def test_completed_year_survives_ram_reset(self):
        self._seed_all_fresh()
        src._reset_runtime_state()
        with patch.object(
            src, '_fetch_html', side_effect=AssertionError('html')
        ), patch.object(
            src, '_fetch_json', side_effect=AssertionError('json')
        ), patch.object(src, '_current_calendar_year', return_value=2026):
            results = src.lookup('The Flatshare', "Beth O'Leary")
        self.assertGreaterEqual(len(results), 2)

    def test_stale_news_index_with_slot_attempts_refresh(self):
        self._seed_all_fresh()
        _save_news_index(_classified_posts(), generated_at=_STALE_AT, ttl_seconds=60)
        src._reset_runtime_state()
        json_calls = []

        def fetch_json(url):
            json_calls.append(url)
            if '/news_categories' in url:
                return _taxonomy_payload(NEWS_CAT_ID)
            return [
                _news_item(
                    1,
                    'RNA reveals 2026 shortlists',
                    'rna-reveals-2026-shortlists',
                    '2026-02-01',
                    2026,
                )
            ]

        with cache.lookup_refresh_budget(), patch.object(
            src, '_fetch_json', side_effect=fetch_json
        ), patch.object(
            src, '_fetch_html', side_effect=AssertionError('html')
        ), patch.object(src, '_current_calendar_year', return_value=2026):
            src.lookup('Any Trope But You', 'Victoria Lavine')
        self.assertTrue(json_calls)

    def test_stale_without_slot_uses_stale_zero_http(self):
        self._seed_all_fresh()
        _save_news_index(_classified_posts(), generated_at=_STALE_AT, ttl_seconds=60)
        src._reset_runtime_state()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                src, '_fetch_html', side_effect=AssertionError('html')
            ), patch.object(
                src, '_fetch_json', side_effect=AssertionError('json')
            ), patch.object(src, '_current_calendar_year', return_value=2026):
                results = src.lookup('Any Trope But You', 'Victoria Lavine')
        self.assertEqual(results[0].status, 'Winner')

    def test_stale_refresh_failure_preserves_winners(self):
        _save_winners(_minimal_winners(), generated_at=_STALE_AT, ttl_seconds=60)
        _save_news_index(_classified_posts())
        _save_year(_year_2018())
        _save_year(_year_2020())
        _save_year(_year_2026())
        src._reset_runtime_state()
        with patch.object(
            src, '_fetch_html', side_effect=src.RomanticNovelAwardsSourceError('blocked')
        ), patch.object(
            src, '_fetch_json', side_effect=AssertionError('json')
        ), patch.object(src, '_current_calendar_year', return_value=2026):
            results = src.lookup('Pillow Talk', 'Freya North')
        self.assertEqual(results[0].work_title, 'Pillow Talk')
        payload = cache.load_cache_entry(
            src.SOURCE_KEY,
            src.WINNERS_ENTRY_KIND,
            src.WINNERS_ENTRY_KEY,
            src.WINNERS_CACHE_VERSION,
        )
        titles = {item['work_title'] for item in payload['records']}
        self.assertIn('Pillow Talk', titles)

    def test_malformed_archive_does_not_replace_stale_winners(self):
        _save_winners(_minimal_winners(), generated_at=_STALE_AT, ttl_seconds=60)
        _save_news_index(_classified_posts())
        _save_year(_year_2018())
        _save_year(_year_2020())
        _save_year(_year_2026())
        src._reset_runtime_state()

        def fetch_html(url):
            if ARCHIVE in url:
                return '<html><body>Just a moment Cloudflare</body></html>'
            raise AssertionError(url)

        with patch.object(src, '_fetch_html', side_effect=fetch_html), patch.object(
            src, '_current_calendar_year', return_value=2026
        ):
            results = src.lookup('More Than Friendship', 'Mary Howard')
        self.assertEqual(results[0].work_title, 'More Than Friendship')

    def test_malformed_shortlist_does_not_replace_stale_year(self):
        self._seed_all_fresh()
        _save_year(_year_2026(), generated_at=_STALE_AT, ttl_seconds=60)
        src._reset_runtime_state()

        def fetch_html(url):
            if url == SHORTLIST_2026:
                return '<html><body>Just a moment Cloudflare</body></html>'
            raise src.RomanticNovelAwardsSourceError(url)

        with patch.object(src, '_fetch_html', side_effect=fetch_html), patch.object(
            src, '_current_calendar_year', return_value=2026
        ):
            results = src.lookup('Onyx Storm', 'Rebecca Yarros')
        self.assertEqual(results[0].status, 'Shortlisted')

    def test_missing_cache_requires_live(self):
        helper = LookupIntegrationTests()
        with patch.object(src, '_fetch_html', side_effect=helper._fetch_html) as mocked_html, patch.object(
            src, '_fetch_json', side_effect=helper._fetch_json
        ), patch.object(src, '_current_calendar_year', return_value=2026):
            src.lookup('More Than Friendship', 'Mary Howard')
        self.assertTrue(mocked_html.called)

    def test_invalid_cache_requires_live(self):
        path = _entry_path(self.cache_dir, src.WINNERS_ENTRY_KIND, src.WINNERS_ENTRY_KEY)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{not-json', encoding='utf-8')
        _save_news_index(_classified_posts())
        helper = LookupIntegrationTests()
        with patch.object(src, '_fetch_html', side_effect=helper._fetch_html) as mocked, patch.object(
            src, '_fetch_json', side_effect=helper._fetch_json
        ), patch.object(src, '_current_calendar_year', return_value=2026):
            src.lookup('More Than Friendship', 'Mary Howard')
        self.assertTrue(mocked.called)

    def test_manual_refresh_clears_rona_kinds_and_ram_with_zero_http(self):
        self._seed_all_fresh()
        src._winners_cache = _minimal_winners()
        src._news_index_cache = src._NewsIndex(NEWS_CAT_ID, _classified_posts())
        src._year_cache[2026] = _year_2026()
        cache.save_source_cache(
            'hugo',
            1,
            records=[],
            source_urls=['https://www.thehugoawards.org/'],
            coverage={},
            ttl_seconds=3600,
        )
        cache.save_source_cache(
            'edgar',
            1,
            records=[],
            source_urls=['https://edgarawards.com/search-the-database/'],
            coverage={},
            ttl_seconds=3600,
        )
        with patch.object(src, '_fetch_html', side_effect=AssertionError('html')), patch.object(
            src, '_fetch_json', side_effect=AssertionError('json')
        ):
            self.assertTrue(refresh_award_source_cache(src.SOURCE_KEY))
        self.assertIsNone(src._winners_cache)
        self.assertIsNone(src._news_index_cache)
        self.assertEqual(src._year_cache, {})
        self.assertIsNone(
            cache.load_cache_entry(
                src.SOURCE_KEY,
                src.WINNERS_ENTRY_KIND,
                src.WINNERS_ENTRY_KEY,
                src.WINNERS_CACHE_VERSION,
            )
        )
        self.assertIsNone(
            cache.load_cache_entry(
                src.SOURCE_KEY,
                src.NEWS_INDEX_ENTRY_KIND,
                src.NEWS_INDEX_ENTRY_KEY,
                src.NEWS_INDEX_CACHE_VERSION,
            )
        )
        self.assertIsNone(
            cache.load_cache_entry(
                src.SOURCE_KEY,
                src.YEAR_ENTRY_KIND,
                '2026',
                src.YEAR_CACHE_VERSION,
            )
        )
        self.assertIsNotNone(cache.load_source_cache('hugo', 1))
        self.assertIsNotNone(cache.load_source_cache('edgar', 1))

    def test_cross_category_and_dual_honor_and_pillow_talk_serialize(self):
        self._seed_all_fresh()
        src._reset_runtime_state()
        with patch.object(
            src, '_fetch_html', side_effect=AssertionError('html')
        ), patch.object(
            src, '_fetch_json', side_effect=AssertionError('json')
        ), patch.object(src, '_current_calendar_year', return_value=2026):
            flatshare = src.lookup('The Flatshare', "Beth O'Leary")
            this_love = src.lookup('This Love', 'Dani Atkins')
            pillow = src.lookup('Pillow Talk', 'Freya North')
        self.assertGreaterEqual(len(flatshare), 2)
        statuses = {(item.status, item.category) for item in this_love}
        self.assertIn(('Winner', None), statuses)
        self.assertIn(('Shortlisted', 'Epic Romantic Novel'), statuses)
        self.assertEqual(pillow[0].award_year, 2008)
        self.assertIsNone(pillow[0].category)

    def test_reset_runtime_state_does_not_delete_disk(self):
        self._seed_all_fresh()
        src._reset_runtime_state()
        self.assertIsNotNone(
            cache.load_cache_entry(
                src.SOURCE_KEY,
                src.WINNERS_ENTRY_KIND,
                src.WINNERS_ENTRY_KEY,
                src.WINNERS_CACHE_VERSION,
            )
        )


class LiveArchivePaginationCacheTests(unittest.TestCase):
    def setUp(self):
        src._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        cache.set_cache_directory(Path(self._temp.name))

    def tearDown(self):
        src._reset_runtime_state()
        cache._reset_runtime_state()
        cache.set_cache_directory(None)
        self._temp.cleanup()

    def test_dynamic_archive_pagination_is_not_hardcoded_to_nine(self):
        pages = {
            ARCHIVE: archive_html(
                [_card('Book One', 'Author One', 1960, 'book-one')],
                page=1,
                of_pages=2,
            ),
            f'{ARCHIVE}/page/2/': archive_html(
                [_card('Book Two', 'Author Two', 1961, 'book-two')],
                page=2,
                of_pages=2,
            ),
        }
        fetched = []

        def fetch_html(url):
            fetched.append(url)
            return pages[url]

        with patch.object(src, '_fetch_html', side_effect=fetch_html):
            records, urls = src._load_live_winners()
        self.assertEqual(len(fetched), 2)
        self.assertNotEqual(len(fetched), 9)
        self.assertEqual(len(records), 2)
        self.assertEqual(urls, [ARCHIVE, f'{ARCHIVE}/page/2/'])


if __name__ == '__main__':
    unittest.main()
