"""Offline coverage for Locus persistent annual-page cache (Phase L2)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.sources import locus

_UTC = timezone.utc
_TESTS_DIR = Path(__file__).resolve().parent
_CANONICAL_1990 = 'https://www.sfadb.com/Locus_Awards_1990'
_CANONICAL_1971 = 'https://www.sfadb.com/Locus_Awards_1971'
_CANONICAL_2026 = 'https://www.sfadb.com/Locus_Awards_2026'
_AUTHOR_SIMMONS = 'https://www.sfadb.com/Dan_Simmons'


def _load_parser_fixtures():
    path = _TESTS_DIR / 'test_locus_parser.py'
    spec = importlib.util.spec_from_file_location(
        '_locus_parser_fixture_source', path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FX = _load_parser_fixtures()


def _author_path(cache_dir: Path, canonical_url: str) -> Path:
    digest = hashlib.sha256(canonical_url.encode('utf-8')).hexdigest()
    return cache_dir / 'locus' / 'authors' / f'{digest}.json'


def _annual_path(cache_dir: Path, canonical_url: str) -> Path:
    digest = hashlib.sha256(canonical_url.encode('utf-8')).hexdigest()
    return cache_dir / 'locus' / 'annuals' / f'{digest}.json'


def _save_author_disk(
    page,
    canonical_url,
    *,
    generated_at=None,
    ttl_seconds=None,
    version=None,
):
    persistable = locus._author_page_for_cache(page, canonical_url)
    if persistable is None:
        persistable = page
    cache.save_cache_entry(
        locus.SOURCE_KEY,
        locus.AUTHOR_ENTRY_KIND,
        canonical_url,
        locus.AUTHOR_CACHE_VERSION if version is None else version,
        records=[locus._author_page_to_cache_dict(persistable)],
        source_urls=[canonical_url],
        coverage=locus._author_coverage(persistable),
        ttl_seconds=(
            locus.AUTHOR_CACHE_TTL_SECONDS
            if ttl_seconds is None
            else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _save_annual_disk(
    records,
    canonical_url,
    *,
    generated_at=None,
    ttl_seconds=None,
    version=None,
):
    cache.save_cache_entry(
        locus.SOURCE_KEY,
        locus.ANNUAL_ENTRY_KIND,
        canonical_url,
        locus.ANNUAL_CACHE_VERSION if version is None else version,
        records=[
            locus._annual_record_to_cache_dict(record) for record in records
        ],
        source_urls=[canonical_url],
        coverage=locus._annual_coverage(
            tuple(records),
            locus._award_year_from_canonical_annual_url(canonical_url),
        ),
        ttl_seconds=(
            locus.ANNUAL_CACHE_TTL_SECONDS
            if ttl_seconds is None
            else ttl_seconds
        ),
        generated_at=generated_at,
    )


class _HttpTracker:
    def __init__(self, pages, *, boom_annual=False):
        self.pages = pages
        self.author = []
        self.annual = []
        self.boom_annual = boom_annual

    def __call__(self, _opener, url: str):
        if locus._canonical_annual_url(url) is not None:
            self.annual.append(url)
            if self.boom_annual:
                raise locus.LocusSourceError('annual HTTP disabled')
        else:
            self.author.append(url)
        body = self.pages.get(url)
        if body is None:
            return 404, ''
        return 200, body


class LocusAnnualCacheTests(unittest.TestCase):
    def setUp(self):
        locus._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        locus._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _lookup(self, title, author, tracker=None, **patch_kwargs):
        http = tracker or _HttpTracker(_FX.PAGES)
        with patch.object(locus, '_request_html', side_effect=http):
            results = locus.lookup(title, author)
        return results, http

    def test_cache_identity_constants(self):
        self.assertEqual(locus.SOURCE_KEY, 'locus')
        self.assertEqual(locus.ANNUAL_ENTRY_KIND, 'annuals')
        self.assertEqual(locus.ANNUAL_CACHE_VERSION, 1)
        self.assertEqual(locus.ANNUAL_CACHE_TTL_SECONDS, 7 * 24 * 60 * 60)
        self.assertEqual(locus.ANNUAL_CACHE_TTL_SECONDS, 604800)
        self.assertEqual(locus.AUTHOR_ENTRY_KIND, 'authors')
        self.assertEqual(locus.AUTHOR_CACHE_VERSION, 1)
        self.assertEqual(locus.AUTHOR_CACHE_TTL_SECONDS, 7 * 24 * 60 * 60)
        self.assertEqual(locus.AUTHOR_CACHE_TTL_SECONDS, 604800)

    def test_annual_record_serialization_round_trip(self):
        original = locus._parse_annual_page(
            _FX.HTML_1990, 1990, _CANONICAL_1990
        )
        self.assertGreaterEqual(len(original), 2)
        restored = tuple(
            locus._annual_record_from_cache_dict(
                locus._annual_record_to_cache_dict(record)
            )
            for record in original
        )
        self.assertEqual(restored, original)
        for record in restored:
            self.assertIsInstance(record.linked_authors, tuple)
            self.assertTrue(record.linked_authors)
            self.assertEqual(
                record.work_author, ' & '.join(record.linked_authors)
            )
            self.assertEqual(record.source_url, _CANONICAL_1990)
        rama = next(
            record
            for record in restored
            if record.work_title == 'Rama II'
        )
        self.assertEqual(
            rama.linked_authors, ('Arthur C. Clarke', 'Gentry Lee')
        )
        self.assertEqual(rama.work_author, 'Arthur C. Clarke & Gentry Lee')

    def test_canonical_annual_url_variants(self):
        expected = _CANONICAL_1990
        variants = (
            'http://sfadb.com/Locus_Awards_1990',
            'https://sfadb.com/Locus_Awards_1990',
            'http://www.sfadb.com/Locus_Awards_1990',
            'https://www.sfadb.com/Locus_Awards_1990',
            'https://www.sfadb.com/Locus_Awards_1990/',
            'https://WWW.SFADB.COM/Locus_Awards_1990',
            'https://www.sfadb.com/Locus_Awards_1990?x=1',
            'https://www.sfadb.com/Locus_Awards_1990#frag',
            'https://www.sfadb.com/Locus_Awards_1990/?utm=1#top',
            'https://sfadb.com/Locus_Awards_1990/?q=1#x',
        )
        for url in variants:
            with self.subTest(url=url):
                self.assertEqual(locus._canonical_annual_url(url), expected)

    def test_canonical_annual_url_rejects_unusable(self):
        rejected = (
            'https://example.com/Locus_Awards_1990',
            'https://www.example.com/Locus_Awards_1990',
            'ftp://www.sfadb.com/Locus_Awards_1990',
            'https://www.sfadb.com/Dan_Simmons',
            'https://www.sfadb.com/Hugo_Awards_1990',
            'https://www.sfadb.com/Locus_Awards_1990/extra',
            'https://www.sfadb.com/foo/Locus_Awards_1990',
            'https://www.sfadb.com/Locus_Awards_0000',
            'https://www.sfadb.com/Locus_Awards',
            'Locus_Awards_1990',
            '',
        )
        for url in rejected:
            with self.subTest(url=url):
                self.assertIsNone(locus._canonical_annual_url(url))

    def test_off_host_annual_url_is_source_error(self):
        with self.assertRaises(locus.LocusSourceError):
            locus._get_annual_records(
                object(), 'https://example.com/Locus_Awards_1990'
            )

    def test_non_locus_annual_path_is_source_error(self):
        with self.assertRaises(locus.LocusSourceError):
            locus._get_annual_records(
                object(), 'https://www.sfadb.com/Dan_Simmons'
            )

    def test_url_variants_reuse_one_keyed_file(self):
        tracker = _HttpTracker(_FX.PAGES)
        with patch.object(locus, '_request_html', side_effect=tracker):
            first = locus._get_annual_records(
                object(), 'http://sfadb.com/Locus_Awards_1990/'
            )
        path = _annual_path(self.cache_dir, _CANONICAL_1990)
        self.assertTrue(path.is_file())
        self.assertEqual(tracker.annual, [_CANONICAL_1990])
        locus._reset_runtime_state()
        tracker2 = _HttpTracker(_FX.PAGES, boom_annual=True)
        with patch.object(
            locus, '_load_live_annual', side_effect=AssertionError('live')
        ):
            with patch.object(locus, '_request_html', side_effect=tracker2):
                second = locus._get_annual_records(
                    object(),
                    'https://www.sfadb.com/Locus_Awards_1990?ref=1#x',
                )
        self.assertEqual(second, first)
        self.assertEqual(tracker2.annual, [])
        annual_files = list(
            (self.cache_dir / 'locus' / 'annuals').glob('*.json')
        )
        self.assertEqual(len(annual_files), 1)
        self.assertEqual(annual_files[0], path)

    def test_live_lookup_writes_keyed_annual_file(self):
        results, http = self._lookup('Hyperion', 'Dan Simmons')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].rank, 1)
        self.assertEqual(results[0].status, 'Winner')
        path = _annual_path(self.cache_dir, _CANONICAL_1990)
        self.assertTrue(path.is_file())
        payload = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(payload['source_key'], 'locus')
        self.assertEqual(payload['entry_kind'], 'annuals')
        self.assertEqual(payload['entry_key'], _CANONICAL_1990)
        self.assertEqual(payload['source_cache_version'], 1)
        self.assertEqual(payload['source_urls'], [_CANONICAL_1990])
        self.assertGreaterEqual(payload['record_count'], 1)
        self.assertEqual(http.author, [_AUTHOR_SIMMONS])
        self.assertEqual(http.annual, [_CANONICAL_1990])
        author_path = _author_path(self.cache_dir, _AUTHOR_SIMMONS)
        self.assertTrue(author_path.is_file())
        author_payload = json.loads(author_path.read_text(encoding='utf-8'))
        self.assertEqual(author_payload['entry_kind'], 'authors')
        self.assertEqual(author_payload['entry_key'], _AUTHOR_SIMMONS)

    def test_restart_uses_disk_annual_and_live_author(self):
        records = locus._parse_annual_page(
            _FX.HTML_1990, 1990, _CANONICAL_1990
        )
        _save_annual_disk(records, _CANONICAL_1990)
        tracker = _HttpTracker(_FX.PAGES)
        with patch.object(
            locus, '_load_live_annual', side_effect=AssertionError('annual live')
        ):
            with patch.object(locus, '_request_html', side_effect=tracker):
                results = locus.lookup('Hyperion', 'Dan Simmons')
        self.assertEqual(results[0].rank, 1)
        self.assertEqual(tracker.author, [_AUTHOR_SIMMONS])
        self.assertEqual(tracker.annual, [])

    def test_same_annual_reused_from_disk_after_ram_reset(self):
        self._lookup('Hyperion', 'Dan Simmons')
        locus._reset_runtime_state()
        tracker = _HttpTracker(_FX.PAGES)
        with patch.object(
            locus, '_load_live_annual', side_effect=AssertionError('annual live')
        ):
            with patch.object(locus, '_request_html', side_effect=tracker):
                cherryh = locus.lookup('Rimrunners', 'C. J. Cherryh')
                simmons = locus.lookup('Hyperion', 'Dan Simmons')
        self.assertEqual(cherryh[0].rank, 2)
        self.assertEqual(simmons[0].rank, 1)
        self.assertEqual(tracker.annual, [])
        self.assertEqual(
            tracker.author,
            ['https://www.sfadb.com/C_J_Cherryh'],
        )

    def test_source_specific_corrupt_annual_disk_falls_back_to_live(self):
        records = locus._parse_annual_page(
            _FX.HTML_1990, 1990, _CANONICAL_1990
        )
        _save_annual_disk(records, _CANONICAL_1990)
        sibling = locus._parse_annual_page(
            _FX.HTML_1971, 1971, _CANONICAL_1971
        )
        _save_annual_disk(sibling, _CANONICAL_1971)
        sibling_path = _annual_path(self.cache_dir, _CANONICAL_1971)
        sibling_before = sibling_path.read_text(encoding='utf-8')

        cases = {
            'bad_year': lambda data: data.__setitem__('award_year', 0),
            'year_mismatch': lambda data: data.__setitem__('award_year', 1989),
            'unsupported_category': lambda data: data.__setitem__(
                'category', 'Anthology'
            ),
            'rank_zero': lambda data: data.__setitem__('rank', 0),
            'rank_bool': lambda data: data.__setitem__('rank', True),
            'rank_string': lambda data: data.__setitem__('rank', '1'),
            'winner_not_rank_one': lambda data: (
                data.__setitem__('rank', 2),
                data.__setitem__('winner', True),
            ),
            'rank_one_not_winner': lambda data: data.__setitem__(
                'winner', False
            ),
            'linked_authors_string': lambda data: data.__setitem__(
                'linked_authors', 'Dan Simmons'
            ),
            'empty_linked_authors': lambda data: data.__setitem__(
                'linked_authors', []
            ),
            'work_author_mismatch': lambda data: data.__setitem__(
                'work_author', 'Someone Else'
            ),
            'malformed_field': lambda data: data.pop('work_title'),
            'off_host_source_url': lambda data: data.__setitem__(
                'source_url', 'https://example.com/Locus_Awards_1990'
            ),
        }
        path = _annual_path(self.cache_dir, _CANONICAL_1990)
        original = path.read_text(encoding='utf-8')
        for name, mutator in cases.items():
            with self.subTest(case=name):
                locus._reset_runtime_state()
                envelope = json.loads(original)
                mutator(envelope['records'][0])
                path.write_text(
                    json.dumps(envelope, indent=2) + '\n', encoding='utf-8'
                )
                tracker = _HttpTracker(_FX.PAGES)
                with patch.object(locus, '_request_html', side_effect=tracker):
                    results = locus.lookup('Hyperion', 'Dan Simmons')
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0].rank, 1)
                self.assertEqual(tracker.annual, [_CANONICAL_1990])
                self.assertEqual(
                    sibling_path.read_text(encoding='utf-8'), sibling_before
                )

    def test_duplicate_identity_on_disk_falls_back_to_live(self):
        records = locus._parse_annual_page(
            _FX.HTML_1990, 1990, _CANONICAL_1990
        )
        _save_annual_disk(records, _CANONICAL_1990)
        path = _annual_path(self.cache_dir, _CANONICAL_1990)
        envelope = json.loads(path.read_text(encoding='utf-8'))
        envelope['records'].append(dict(envelope['records'][0]))
        path.write_text(json.dumps(envelope, indent=2) + '\n', encoding='utf-8')
        tracker = _HttpTracker(_FX.PAGES)
        with patch.object(locus, '_request_html', side_effect=tracker):
            results = locus.lookup('Hyperion', 'Dan Simmons')
        self.assertEqual(results[0].rank, 1)
        self.assertEqual(tracker.annual, [_CANONICAL_1990])

    def test_cache_version_mismatch_uses_live_annual(self):
        records = locus._parse_annual_page(
            _FX.HTML_1990, 1990, _CANONICAL_1990
        )
        _save_annual_disk(records, _CANONICAL_1990, version=2)
        tracker = _HttpTracker(_FX.PAGES)
        with patch.object(locus, '_request_html', side_effect=tracker):
            results = locus.lookup('Hyperion', 'Dan Simmons')
        self.assertEqual(results[0].rank, 1)
        self.assertEqual(tracker.annual, [_CANONICAL_1990])

    def test_stale_valid_annual_loads_without_http_or_refresh_claim(self):
        records = locus._parse_annual_page(
            _FX.HTML_1990, 1990, _CANONICAL_1990
        )
        _save_annual_disk(
            records,
            _CANONICAL_1990,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        payload = cache.load_cache_entry(
            'locus', 'annuals', _CANONICAL_1990, 1
        )
        self.assertIsNotNone(payload)
        self.assertFalse(cache.cache_is_fresh(payload))
        claims = {'n': 0}
        real_claim = cache.try_claim_stale_refresh

        def wrapped_claim():
            claims['n'] += 1
            return real_claim()

        tracker = _HttpTracker(_FX.PAGES)
        with cache.lookup_refresh_budget():
            with patch.object(
                cache, 'try_claim_stale_refresh', side_effect=wrapped_claim
            ):
                with patch.object(
                    locus,
                    '_load_live_annual',
                    side_effect=AssertionError('annual live'),
                ):
                    with patch.object(
                        locus, '_request_html', side_effect=tracker
                    ):
                        results = locus.lookup('Hyperion', 'Dan Simmons')
            self.assertTrue(cache.try_claim_stale_refresh())
        self.assertEqual(results[0].rank, 1)
        self.assertEqual(tracker.annual, [])
        self.assertEqual(tracker.author, [_AUTHOR_SIMMONS])
        self.assertEqual(claims['n'], 0)

    def test_save_oserror_does_not_fail_lookup(self):
        tracker = _HttpTracker(_FX.PAGES)
        with patch.object(
            cache, 'save_cache_entry', side_effect=OSError('disk full')
        ):
            with patch.object(locus, '_request_html', side_effect=tracker):
                results = locus.lookup('Hyperion', 'Dan Simmons')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].rank, 1)
        self.assertFalse(_annual_path(self.cache_dir, _CANONICAL_1990).exists())

    def test_ram_reset_does_not_delete_annual_disk(self):
        self._lookup('Hyperion', 'Dan Simmons')
        path = _annual_path(self.cache_dir, _CANONICAL_1990)
        self.assertTrue(path.is_file())
        before = path.read_text(encoding='utf-8')
        self.assertIn(_CANONICAL_1990, locus._annual_page_cache)
        locus._reset_runtime_state()
        self.assertEqual(locus._annual_page_cache, {})
        self.assertEqual(locus._author_page_cache, {})
        self.assertTrue(_author_path(self.cache_dir, _AUTHOR_SIMMONS).is_file())
        self.assertEqual(path.read_text(encoding='utf-8'), before)

    def test_malformed_live_annual_does_not_write_disk(self):
        def fake(_opener, url):
            if url == _AUTHOR_SIMMONS:
                return 200, _FX.HTML_SIMMONS
            if url == _CANONICAL_1990:
                return 200, _FX.HTML_MISSING_VALUE
            return 404, ''

        with patch.object(locus, '_request_html', side_effect=fake):
            with self.assertRaises(locus.LocusSourceError):
                locus.lookup('Hyperion', 'Dan Simmons')
        annuals_dir = self.cache_dir / 'locus' / 'annuals'
        if annuals_dir.exists():
            self.assertEqual(list(annuals_dir.glob('*.json')), [])
        self.assertNotIn(_CANONICAL_1990, locus._annual_page_cache)

    def test_rank_and_tie_preservation(self):
        records_1990 = locus._parse_annual_page(
            _FX.HTML_1990, 1990, _CANONICAL_1990
        )
        records_1971 = locus._parse_annual_page(
            _FX.HTML_1971, 1971, _CANONICAL_1971
        )
        records_2026 = locus._parse_annual_page(
            _FX.HTML_2026, 2026, _CANONICAL_2026
        )
        _save_annual_disk(records_1990, _CANONICAL_1990)
        _save_annual_disk(records_1971, _CANONICAL_1971)
        _save_annual_disk(records_2026, _CANONICAL_2026)
        locus._reset_runtime_state()
        with patch.object(
            locus, '_load_live_annual', side_effect=AssertionError('annual live')
        ):
            restored_1990 = locus._get_annual_records(object(), _CANONICAL_1990)
            restored_1971 = locus._get_annual_records(object(), _CANONICAL_1971)
            restored_2026 = locus._get_annual_records(object(), _CANONICAL_2026)
        self.assertEqual(restored_1990, records_1990)
        self.assertEqual(restored_1971, records_1971)
        self.assertEqual(restored_2026, records_2026)

        by_title_1990 = {
            record.work_title: record for record in restored_1990
        }
        self.assertEqual(by_title_1990['Hyperion'].rank, 1)
        self.assertTrue(by_title_1990['Hyperion'].winner)
        self.assertEqual(by_title_1990['A Fire in the Sun'].rank, 5)
        self.assertFalse(by_title_1990['A Fire in the Sun'].winner)
        self.assertEqual(by_title_1990['The Boat of a Million Years'].rank, 6)
        self.assertEqual(
            by_title_1990['Rama II'].linked_authors,
            ('Arthur C. Clarke', 'Gentry Lee'),
        )

        novels = [
            record for record in restored_1971 if record.category == 'Novel'
        ]
        self.assertEqual([record.rank for record in novels], [1, 2, 2, 4, 5, 5, 7])
        ties = [
            (record.work_title, record.rank)
            for record in novels
            if record.tied
        ]
        self.assertEqual(
            ties,
            [
                ('Tower of Glass', 2),
                ('The Year of the Quiet Sun', 2),
                ('Downward to the Earth', 5),
                ('Fourth Mansions', 5),
            ],
        )

        fantasy = {
            record.work_title: record
            for record in restored_2026
            if record.category == 'Fantasy Novel'
        }
        self.assertEqual(fantasy['Hemlock & Silver'].rank, 3)
        self.assertTrue(fantasy['Hemlock & Silver'].tied)
        self.assertEqual(fantasy['Katabasis'].rank, 3)
        self.assertTrue(fantasy['Katabasis'].tied)
        self.assertEqual(fantasy['A Drop of Corruption'].rank, 5)
        self.assertFalse(fantasy['A Drop of Corruption'].tied)
        self.assertEqual(fantasy['Queen Demon'].rank, 6)
        self.assertEqual(
            [record.source_url for record in restored_2026],
            [_CANONICAL_2026] * len(restored_2026),
        )

        tracker = _HttpTracker(_FX.PAGES)
        with patch.object(
            locus, '_load_live_annual', side_effect=AssertionError('annual live')
        ):
            with patch.object(locus, '_request_html', side_effect=tracker):
                rank1 = locus.lookup('Hyperion', 'Dan Simmons')
                rank5 = locus.lookup('A Fire in the Sun', 'George Alec Effinger')
                rank6 = locus.lookup(
                    'The Boat of a Million Years', 'Poul Anderson'
                )
                tied = locus.lookup('Hemlock & Silver', 'T. Kingfisher')
        self.assertEqual(rank1[0].rank, 1)
        self.assertEqual(rank5[0].rank, 5)
        self.assertEqual(rank6[0].rank, 6)
        self.assertEqual(tied[0].rank, 3)
        self.assertEqual(tied[0].notes, 'tie')
        self.assertEqual(tracker.annual, [])

    def test_discovery_disagrees_with_disk_annual(self):
        records = locus._parse_annual_page(
            _FX.HTML_1990, 1990, _CANONICAL_1990
        )
        _save_annual_disk(records, _CANONICAL_1990)
        locus._reset_runtime_state()
        bad_author = _FX._author_page(
            'Dan Simmons',
            _FX._entry(1990, 'Hyperion', 'sf novel', '4th place'),
        )

        def fake(_opener, url):
            if url == _AUTHOR_SIMMONS:
                return 200, bad_author
            raise AssertionError(f'unexpected request {url}')

        with patch.object(
            locus, '_load_live_annual', side_effect=AssertionError('annual live')
        ):
            with patch.object(locus, '_request_html', side_effect=fake):
                with self.assertRaises(locus.LocusSourceError) as ctx:
                    locus.lookup('Hyperion', 'Dan Simmons')
        self.assertIn('disagreed', str(ctx.exception))

    def test_author_and_discovery_serialization_round_trip(self):
        original = locus._parse_author_page(_FX.HTML_SIMMONS, _AUTHOR_SIMMONS)
        persistable = locus._author_page_for_cache(original, _AUTHOR_SIMMONS)
        self.assertIsNotNone(persistable)
        restored = locus._author_page_from_cache_dict(
            locus._author_page_to_cache_dict(persistable),
            _AUTHOR_SIMMONS,
        )
        self.assertEqual(restored, persistable)
        self.assertIsInstance(restored.entries, tuple)
        self.assertEqual(len(restored.entries), len(original.entries))
        hyperion = next(
            entry for entry in restored.entries if entry.work_title == 'Hyperion'
        )
        self.assertEqual(hyperion.award_year, 1990)
        self.assertEqual(hyperion.annual_url, _CANONICAL_1990)
        self.assertEqual(hyperion.rank, 1)
        self.assertTrue(hyperion.winner)
        self.assertEqual(hyperion.category_text.casefold(), 'sf novel')
        self.assertEqual(
            [entry.work_title for entry in restored.entries],
            [entry.work_title for entry in original.entries],
        )

    def test_canonical_author_url_variants(self):
        expected = _AUTHOR_SIMMONS
        variants = (
            'http://sfadb.com/Dan_Simmons',
            'https://sfadb.com/Dan_Simmons',
            'http://www.sfadb.com/Dan_Simmons',
            'https://www.sfadb.com/Dan_Simmons',
            'https://www.sfadb.com/Dan_Simmons/',
            'https://WWW.SFADB.COM/Dan_Simmons',
            'https://www.sfadb.com/Dan_Simmons?x=1',
            'https://www.sfadb.com/Dan_Simmons#frag',
            'https://www.sfadb.com/Dan_Simmons/?utm=1#top',
        )
        for url in variants:
            with self.subTest(url=url):
                self.assertEqual(locus._canonical_author_url(url), expected)

    def test_canonical_author_url_preserves_unicode_and_rejects_annual(self):
        unicode_url = locus._author_page_url('China_Miéville')
        self.assertEqual(
            locus._canonical_author_url(unicode_url), unicode_url
        )
        self.assertEqual(
            locus._canonical_author_url(
                'http://sfadb.com/China_Miéville/?q=1#x'
            ),
            unicode_url,
        )
        rejected = (
            'https://example.com/Dan_Simmons',
            'https://www.sfadb.com/Dan_Simmons/extra',
            'https://www.sfadb.com/foo/Dan_Simmons',
            _CANONICAL_1990,
            'https://www.sfadb.com/Locus_Awards_1990/',
            'https://www.sfadb.com/',
            'https://www.sfadb.com',
            'ftp://www.sfadb.com/Dan_Simmons',
            'Dan_Simmons',
            '',
        )
        for url in rejected:
            with self.subTest(url=url):
                self.assertIsNone(locus._canonical_author_url(url))
        self.assertEqual(
            locus._canonical_annual_url(_CANONICAL_1990), _CANONICAL_1990
        )

    def test_full_restart_zero_locus_http(self):
        first, first_http = self._lookup('Hyperion', 'Dan Simmons')
        self.assertEqual(first[0].award_year, 1990)
        self.assertEqual(first[0].award_name, 'Locus Award')
        self.assertEqual(first[0].category, 'Sf Novel')
        self.assertEqual(first[0].rank, 1)
        self.assertEqual(first[0].status, 'Winner')
        self.assertEqual(first_http.author, [_AUTHOR_SIMMONS])
        self.assertEqual(first_http.annual, [_CANONICAL_1990])
        self.assertTrue(_author_path(self.cache_dir, _AUTHOR_SIMMONS).is_file())
        self.assertTrue(_annual_path(self.cache_dir, _CANONICAL_1990).is_file())
        locus._reset_runtime_state()

        def boom(_opener, url):
            raise AssertionError(f'Locus HTTP disabled: {url}')

        with patch.object(
            locus, '_load_live_annual', side_effect=AssertionError('annual live')
        ):
            with patch.object(
                locus, '_load_live_author_page', side_effect=AssertionError('author live')
            ):
                with patch.object(locus, '_request_html', side_effect=boom):
                    second = locus.lookup('Hyperion', 'Dan Simmons')
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0].award_year, 1990)
        self.assertEqual(second[0].award_name, 'Locus Award')
        self.assertEqual(second[0].category, 'Sf Novel')
        self.assertEqual(second[0].rank, 1)
        self.assertEqual(second[0].status, 'Winner')
        self.assertEqual(second[0].source_name, 'Science Fiction Awards Database')

    def test_same_author_different_title_reuses_author_disk(self):
        self._lookup('Hyperion', 'Dan Simmons')
        locus._reset_runtime_state()
        tracker = _HttpTracker(_FX.PAGES)
        with patch.object(
            locus, '_load_live_author_page', side_effect=AssertionError('author live')
        ):
            with patch.object(locus, '_request_html', side_effect=tracker):
                comfort = locus.lookup('Carrion Comfort', 'Dan Simmons')
                muse = locus.lookup('Muse of Fire', 'Dan Simmons')
        self.assertEqual(comfort[0].award_year, 1990)
        self.assertEqual(comfort[0].category, 'Horror Novel')
        self.assertEqual(comfort[0].rank, 1)
        self.assertEqual(muse[0].award_year, 2008)
        self.assertEqual(muse[0].rank, 5)
        self.assertEqual(tracker.author, [])
        self.assertEqual(tracker.annual, [_FX.URL_2008])

    def test_multi_slug_restart_skips_earlier_404(self):
        cherryh_omitted = 'https://www.sfadb.com/C_Cherryh'
        requested = []

        def first_run(_opener, url):
            requested.append(url)
            if url == 'https://www.sfadb.com/C_J_Cherryh':
                return 404, ''
            if url == cherryh_omitted:
                return 200, _FX.HTML_CHERRYH_LIVE_SHAPE
            if url == _CANONICAL_1990:
                return 200, _FX.HTML_1990
            return 404, ''

        with patch.object(locus, '_request_html', side_effect=first_run):
            first = locus.lookup('Rimrunners', 'C. J. Cherryh')
        self.assertEqual(first[0].rank, 2)
        self.assertIn('https://www.sfadb.com/C_J_Cherryh', requested)
        self.assertTrue(_author_path(self.cache_dir, cherryh_omitted).is_file())
        self.assertFalse(
            _author_path(self.cache_dir, 'https://www.sfadb.com/C_J_Cherryh').exists()
        )
        locus._reset_runtime_state()

        def boom(_opener, url):
            raise AssertionError(f'Locus HTTP disabled: {url}')

        with patch.object(locus, '_request_html', side_effect=boom):
            second = locus.lookup('Rimrunners', 'C. J. Cherryh')
        self.assertEqual(second[0].rank, 2)
        self.assertEqual(second[0].work_title, 'Rimrunners')

    def test_valid_empty_author_page_persists(self):
        def fake(_opener, url):
            if url == _AUTHOR_SIMMONS:
                return 200, _FX.HTML_NO_LOCUS
            raise AssertionError(f'unexpected request {url}')

        with patch.object(locus, '_request_html', side_effect=fake):
            self.assertEqual(locus.lookup('Hyperion', 'Dan Simmons'), [])
        path = _author_path(self.cache_dir, _AUTHOR_SIMMONS)
        self.assertTrue(path.is_file())
        payload = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(payload['records'][0]['entries'], [])
        locus._reset_runtime_state()

        def boom(_opener, url):
            raise AssertionError(f'Locus HTTP disabled: {url}')

        with patch.object(locus, '_request_html', side_effect=boom):
            self.assertEqual(locus.lookup('Hyperion', 'Dan Simmons'), [])

    def test_404_does_not_persist_author(self):
        def fake(_opener, url):
            return 404, ''

        with patch.object(locus, '_request_html', side_effect=fake):
            self.assertEqual(locus.lookup('Hyperion', 'Nobody Known'), [])
        authors_dir = self.cache_dir / 'locus' / 'authors'
        if authors_dir.exists():
            self.assertEqual(list(authors_dir.glob('*.json')), [])

    def test_wrong_person_disk_is_skipped(self):
        wrong = locus._AuthorPage(
            page_url='https://www.sfadb.com/C_J_Cherryh',
            page_name='Someone Else',
            entries=(),
        )
        _save_author_disk(wrong, 'https://www.sfadb.com/C_J_Cherryh')
        tracker = _HttpTracker(_FX.PAGES)
        with patch.object(locus, '_request_html', side_effect=tracker):
            results = locus.lookup('Rimrunners', 'C. J. Cherryh')
        self.assertEqual(results[0].rank, 2)
        self.assertEqual(
            tracker.author, ['https://www.sfadb.com/C_J_Cherryh']
        )

    def test_malformed_author_page_does_not_persist(self):
        def fake(_opener, url):
            if url == _AUTHOR_SIMMONS:
                return 200, _FX.HTML_MALFORMED_LOCUS
            return 404, ''

        with patch.object(locus, '_request_html', side_effect=fake):
            with self.assertRaises(locus.LocusSourceError):
                locus.lookup('Hyperion', 'Dan Simmons')
        authors_dir = self.cache_dir / 'locus' / 'authors'
        if authors_dir.exists():
            self.assertEqual(list(authors_dir.glob('*.json')), [])

    def test_stale_author_loads_without_http_or_refresh_claim(self):
        page = locus._parse_author_page(_FX.HTML_SIMMONS, _AUTHOR_SIMMONS)
        _save_author_disk(
            page,
            _AUTHOR_SIMMONS,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        records = locus._parse_annual_page(
            _FX.HTML_1990, 1990, _CANONICAL_1990
        )
        _save_annual_disk(
            records,
            _CANONICAL_1990,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        author_payload = cache.load_cache_entry(
            'locus', 'authors', _AUTHOR_SIMMONS, 1
        )
        self.assertIsNotNone(author_payload)
        self.assertFalse(cache.cache_is_fresh(author_payload))
        claims = {'n': 0}
        real_claim = cache.try_claim_stale_refresh

        def wrapped_claim():
            claims['n'] += 1
            return real_claim()

        def boom(_opener, url):
            raise AssertionError(f'Locus HTTP disabled: {url}')

        with cache.lookup_refresh_budget():
            with patch.object(
                cache, 'try_claim_stale_refresh', side_effect=wrapped_claim
            ):
                with patch.object(locus, '_request_html', side_effect=boom):
                    results = locus.lookup('Hyperion', 'Dan Simmons')
            self.assertTrue(cache.try_claim_stale_refresh())
        self.assertEqual(results[0].rank, 1)
        self.assertEqual(claims['n'], 0)

    def test_corrupt_author_disk_falls_back_to_live(self):
        page = locus._parse_author_page(_FX.HTML_SIMMONS, _AUTHOR_SIMMONS)
        _save_author_disk(page, _AUTHOR_SIMMONS)
        cherryh = locus._parse_author_page(
            _FX.HTML_CHERRYH_LIVE_SHAPE, _FX.URL_CHERRYH
        )
        _save_author_disk(cherryh, _FX.URL_CHERRYH)
        records = locus._parse_annual_page(
            _FX.HTML_1990, 1990, _CANONICAL_1990
        )
        _save_annual_disk(records, _CANONICAL_1990)
        sibling_author = _author_path(self.cache_dir, _FX.URL_CHERRYH).read_text(
            encoding='utf-8'
        )
        sibling_annual = _annual_path(self.cache_dir, _CANONICAL_1990).read_text(
            encoding='utf-8'
        )
        path = _author_path(self.cache_dir, _AUTHOR_SIMMONS)
        original = json.loads(path.read_text(encoding='utf-8'))

        def mutate_page(mutator):
            envelope = json.loads(json.dumps(original))
            mutator(envelope)
            path.write_text(
                json.dumps(envelope, indent=2) + '\n', encoding='utf-8'
            )

        cases = {
            'off_host_page_url': lambda env: env['records'][0].__setitem__(
                'page_url', 'https://example.com/Dan_Simmons'
            ),
            'page_url_mismatch': lambda env: env['records'][0].__setitem__(
                'page_url', 'https://www.sfadb.com/C_J_Cherryh'
            ),
            'wrong_source_urls': lambda env: env.__setitem__(
                'source_urls', ['https://www.sfadb.com/C_J_Cherryh']
            ),
            'empty_page_name': lambda env: env['records'][0].__setitem__(
                'page_name', ''
            ),
            'zero_records': lambda env: env.__setitem__('records', []),
            'multiple_records': lambda env: env.__setitem__(
                'records', env['records'] + env['records']
            ),
            'entries_not_list': lambda env: env['records'][0].__setitem__(
                'entries', 'Hyperion'
            ),
            'missing_field': lambda env: env['records'][0].pop('page_name'),
            'extra_field': lambda env: env['records'][0].__setitem__(
                'html', '<html>'
            ),
            'bad_award_year': lambda env: env['records'][0]['entries'][0].__setitem__(
                'award_year', 0
            ),
            'annual_year_mismatch': lambda env: env['records'][0]['entries'][0].__setitem__(
                'award_year', 1989
            ),
            'off_host_annual_url': lambda env: env['records'][0]['entries'][0].__setitem__(
                'annual_url', 'https://example.com/Locus_Awards_1990'
            ),
            'rank_zero': lambda env: env['records'][0]['entries'][0].__setitem__(
                'rank', 0
            ),
            'rank_bool': lambda env: env['records'][0]['entries'][0].__setitem__(
                'rank', True
            ),
            'winner_non_bool': lambda env: env['records'][0]['entries'][0].__setitem__(
                'winner', 'yes'
            ),
            'empty_title': lambda env: env['records'][0]['entries'][0].__setitem__(
                'work_title', ''
            ),
            'padded_category': lambda env: env['records'][0]['entries'][0].__setitem__(
                'category_text', ' sf novel '
            ),
            'duplicate_identity': lambda env: env['records'][0]['entries'].append(
                dict(env['records'][0]['entries'][0])
            ),
        }
        for name, mutator in cases.items():
            with self.subTest(case=name):
                locus._reset_runtime_state()
                mutate_page(mutator)
                tracker = _HttpTracker(_FX.PAGES)
                with patch.object(locus, '_request_html', side_effect=tracker):
                    results = locus.lookup('Hyperion', 'Dan Simmons')
                self.assertEqual(results[0].rank, 1)
                self.assertEqual(tracker.author, [_AUTHOR_SIMMONS])
                self.assertEqual(
                    _author_path(self.cache_dir, _FX.URL_CHERRYH).read_text(
                        encoding='utf-8'
                    ),
                    sibling_author,
                )
                self.assertEqual(
                    _annual_path(self.cache_dir, _CANONICAL_1990).read_text(
                        encoding='utf-8'
                    ),
                    sibling_annual,
                )

    def test_author_cache_version_mismatch_uses_live(self):
        page = locus._parse_author_page(_FX.HTML_SIMMONS, _AUTHOR_SIMMONS)
        _save_author_disk(page, _AUTHOR_SIMMONS, version=2)
        records = locus._parse_annual_page(
            _FX.HTML_1990, 1990, _CANONICAL_1990
        )
        _save_annual_disk(records, _CANONICAL_1990)
        tracker = _HttpTracker(_FX.PAGES)
        with patch.object(
            locus, '_load_live_annual', side_effect=AssertionError('annual live')
        ):
            with patch.object(locus, '_request_html', side_effect=tracker):
                results = locus.lookup('Hyperion', 'Dan Simmons')
        self.assertEqual(results[0].rank, 1)
        self.assertEqual(tracker.author, [_AUTHOR_SIMMONS])
        self.assertEqual(tracker.annual, [])

    def test_author_save_oserror_does_not_fail_lookup(self):
        real_save = cache.save_cache_entry

        def save_or_raise(
            source_key, entry_kind, entry_key, version, **kwargs
        ):
            if entry_kind == 'authors':
                raise OSError('disk full')
            return real_save(
                source_key, entry_kind, entry_key, version, **kwargs
            )

        tracker = _HttpTracker(_FX.PAGES)
        with patch.object(cache, 'save_cache_entry', side_effect=save_or_raise):
            with patch.object(locus, '_request_html', side_effect=tracker):
                results = locus.lookup('Hyperion', 'Dan Simmons')
        self.assertEqual(results[0].rank, 1)
        self.assertFalse(_author_path(self.cache_dir, _AUTHOR_SIMMONS).exists())
        self.assertTrue(_annual_path(self.cache_dir, _CANONICAL_1990).is_file())

    def test_annual_canonicalization_bridge(self):
        page = locus._parse_author_page(_FX.HTML_SIMMONS, _AUTHOR_SIMMONS)
        persistable = locus._author_page_for_cache(page, _AUTHOR_SIMMONS)
        self.assertIsNotNone(persistable)
        annuals = {entry.annual_url for entry in persistable.entries}
        self.assertIn(_CANONICAL_1990, annuals)
        for url in annuals:
            self.assertEqual(locus._canonical_annual_url(url), url)
        _save_author_disk(persistable, _AUTHOR_SIMMONS)
        records = locus._parse_annual_page(
            _FX.HTML_1990, 1990, _CANONICAL_1990
        )
        _save_annual_disk(records, _CANONICAL_1990)
        locus._reset_runtime_state()
        annual_files_before = {
            path.name
            for path in (self.cache_dir / 'locus' / 'annuals').glob('*.json')
        }
        with patch.object(
            locus, '_request_html', side_effect=AssertionError('http')
        ):
            results = locus.lookup('Hyperion', 'Dan Simmons')
        self.assertEqual(results[0].rank, 1)
        annual_files_after = {
            path.name
            for path in (self.cache_dir / 'locus' / 'annuals').glob('*.json')
        }
        self.assertEqual(annual_files_after, annual_files_before)
        self.assertEqual(len(annual_files_after), 1)

    def test_disk_author_and_annual_disagreement_raises(self):
        page = locus._parse_author_page(_FX.HTML_SIMMONS, _AUTHOR_SIMMONS)
        persistable = locus._author_page_for_cache(page, _AUTHOR_SIMMONS)
        entries = []
        for entry in persistable.entries:
            if entry.work_title == 'Hyperion':
                entry = locus._DiscoveryEntry(
                    award_year=entry.award_year,
                    annual_url=entry.annual_url,
                    work_title=entry.work_title,
                    category_text=entry.category_text,
                    rank=4,
                    winner=False,
                )
            entries.append(entry)
        disagreed = locus._AuthorPage(
            page_url=persistable.page_url,
            page_name=persistable.page_name,
            entries=tuple(entries),
        )
        _save_author_disk(disagreed, _AUTHOR_SIMMONS)
        records = locus._parse_annual_page(
            _FX.HTML_1990, 1990, _CANONICAL_1990
        )
        _save_annual_disk(records, _CANONICAL_1990)
        locus._reset_runtime_state()
        with patch.object(
            locus, '_request_html', side_effect=AssertionError('http')
        ):
            with self.assertRaises(locus.LocusSourceError) as ctx:
                locus.lookup('Hyperion', 'Dan Simmons')
        self.assertIn('disagreed', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()


if __name__ == '__main__':
    unittest.main()
