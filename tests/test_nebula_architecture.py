"""Offline coverage for Nebula v1 architecture, cache, and fail-closed rules."""

from __future__ import annotations

import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from awards.formatter import format_award_result
from awards.qualifier import QualificationDecision, qualify_award_result
from awards.source_registry import AWARD_SOURCES
from awards.sources import nebula

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'nebula'


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding='utf-8')


def _year_page(year: int, body: str) -> str:
    return f'<h2>{year}</h2><ul class="award_list">{body}</ul>'


def _novel_winner_li(year: int, title: str, author: str, slug: str) -> str:
    return (
        f'<li><i class="fa fa-star" alt="Winner" title="Winner"></i>'
        f'<a href="https://nebulas.sfwa.org/nominated-work/{slug}/">'
        f'<em>{title}</em></a> by '
        f'<a href="https://nebulas.sfwa.org/nominees/{slug}-author/">{author}</a>. '
        f'Winner, <a href="https://nebulas.sfwa.org/award/best-novel/" rel="tag">'
        f'Best Novel</a> in '
        f'<a href="https://nebulas.sfwa.org/award-year/{year}/" rel="tag">'
        f'{year}</a></li>'
    )


class NebulaArchitectureTests(unittest.TestCase):
    def test_v1_configs_are_exactly_the_supported_awards(self):
        identities = [
            (config.award_name, config.category, config.archive_url)
            for config in nebula._AWARD_CONFIGS
        ]
        self.assertEqual(
            identities,
            [
                (
                    'Nebula Award',
                    'Best Novel',
                    'https://nebulas.sfwa.org/award/best-novel/',
                ),
                (
                    'Nebula Award',
                    'Best Novella',
                    'https://nebulas.sfwa.org/award/best-novella/',
                ),
                (
                    'Nebula Award',
                    'Best Novelette',
                    'https://nebulas.sfwa.org/award/best-novelette/',
                ),
                (
                    'Nebula Award',
                    'Best Short Story',
                    'https://nebulas.sfwa.org/award/best-short-story/',
                ),
                (
                    'Nebula Award',
                    'Best Poem',
                    'https://nebulas.sfwa.org/award/best-poem/',
                ),
                (
                    'Andre Norton Award',
                    'Middle Grade and Young Adult Fiction',
                    'https://nebulas.sfwa.org/award/andre-norton-award/',
                ),
            ],
        )
        joined = ' '.join(
            f'{config.award_name} {config.category} {config.archive_url}'
            for config in nebula._AWARD_CONFIGS
        )
        self.assertNotIn('Best Comic', joined)
        self.assertNotIn('Best Script', joined)
        self.assertNotIn('Bradbury', joined)
        self.assertNotIn('Game Writing', joined)
        self.assertNotIn('Dramatic Presentation', joined)

    def test_source_registry_still_includes_nebula(self):
        keys = tuple(source.key for source in AWARD_SOURCES)
        self.assertIn('nebula', keys)
        nebula_source = [source for source in AWARD_SOURCES if source.key == 'nebula'][0]
        self.assertIs(nebula_source.lookup, nebula.lookup)

    def test_cache_is_category_local(self):
        nebula._clear_caches_for_tests()
        novel_pages = (('https://example.test/novel', _load('best_novel_1965.html')),)
        poem_pages = (('https://example.test/poem', _load('best_poem_2025.html')),)
        nebula._pages_cache[nebula._BEST_NOVEL_CONFIG.key] = novel_pages
        nebula._pages_cache[nebula._BEST_POEM_CONFIG.key] = poem_pages
        self.assertIs(
            nebula._get_category_pages(nebula._BEST_NOVEL_CONFIG),
            novel_pages,
        )
        self.assertIs(
            nebula._get_category_pages(nebula._BEST_POEM_CONFIG),
            poem_pages,
        )
        nebula._clear_caches_for_tests()

    def test_rel_next_pagination_still_follows_official_link(self):
        html = (
            '<link rel="next" href="https://nebulas.sfwa.org/award/best-novel/page/2/">'
        )
        self.assertEqual(
            nebula._next_page_url(html),
            'https://nebulas.sfwa.org/award/best-novel/page/2/',
        )

    def test_fetch_follows_rel_next_and_stops(self):
        pages = {
            nebula.BEST_NOVEL_URL: (
                '<link rel="next" href="https://nebulas.sfwa.org/award/best-novel/page/2/">'
                '<h2>2025</h2>'
            ),
            'https://nebulas.sfwa.org/award/best-novel/page/2/': '<h2>1965</h2>',
        }

        def _fake_fetch(_opener, url):
            return pages[url]

        with patch.object(nebula, '_fetch_html', side_effect=_fake_fetch):
            fetched = nebula._fetch_category_pages(
                object(), nebula._BEST_NOVEL_CONFIG
            )
        self.assertEqual(
            [url for url, _html in fetched],
            [
                nebula.BEST_NOVEL_URL,
                'https://nebulas.sfwa.org/award/best-novel/page/2/',
            ],
        )

    def test_source_urls_are_absolutized_against_category_archive(self):
        html = """
        <h2>1965</h2><ul class="award_list"><li>
        <i class="fa fa-star" alt="Winner" title="Winner"></i>
        <a href="/nominated-work/dune/"><em>Dune</em></a>
        by <a href="/nominees/frank-herbert/">Frank Herbert</a>.
        Winner, Best Novel in 1965
        </li></ul>
        """
        record = nebula._parse_best_novel_html(html)[0]
        self.assertEqual(
            record.source_url,
            'https://nebulas.sfwa.org/nominated-work/dune/',
        )
        novella_html = """
        <h2>1965</h2><ul class="award_list"><li>
        <i class="fa fa-star" alt="Winner" title="Winner"></i>
        <a href="/nominated-work/the-saliva-tree/">&ldquo;The Saliva Tree&rdquo;</a>
        by <a href="/nominees/brian-w-aldiss/">Brian W. Aldiss</a>.
        Winner, Best Novella in 1965
        </li></ul>
        """
        novella = nebula._parse_category_html(
            novella_html, nebula._BEST_NOVELLA_CONFIG
        )[0]
        self.assertEqual(
            novella.source_url,
            'https://nebulas.sfwa.org/nominated-work/the-saliva-tree/',
        )
        self.assertFalse(novella.source_url.startswith(nebula.BEST_NOVEL_URL))

    def test_lookup_dedupe_includes_category_identity(self):
        html = _load('best_novel_1965.html')
        nebula._clear_caches_for_tests()
        for config in nebula._AWARD_CONFIGS:
            if config is nebula._BEST_NOVEL_CONFIG:
                continue
            nebula._records_cache[config.key] = ()
        nebula._pages_cache[nebula._BEST_NOVEL_CONFIG.key] = (
            ('https://nebulas.sfwa.org/award/best-novel/', html),
            ('https://nebulas.sfwa.org/award/best-novel/page/2/', html),
        )
        try:
            results = nebula.lookup('Dune', 'Frank Herbert')
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].category, 'Best Novel')
        finally:
            nebula._clear_caches_for_tests()


class NebulaFailClosedTests(unittest.TestCase):
    def test_missing_middle_year_heading_fails_closed(self):
        pages = [
            (
                'https://example.test/1',
                _year_page(1965, _novel_winner_li(1965, 'Dune', 'Frank Herbert', 'dune'))
                + _year_page(1967, _novel_winner_li(1967, 'Babel', 'Delany', 'babel')),
            )
        ]
        records = nebula._records_from_pages(nebula._BEST_NOVEL_CONFIG, pages)
        with self.assertRaises(nebula.NebulaSourceError) as ctx:
            nebula._validate_category_archive(
                nebula._BEST_NOVEL_CONFIG, pages, records
            )
        self.assertIn('year heading', str(ctx.exception).casefold())
        self.assertIn('1966', str(ctx.exception))

    def test_pagination_stopping_early_fails_closed(self):
        pages = [
            (
                'https://example.test/latest-only',
                _year_page(
                    2025,
                    _novel_winner_li(
                        2025,
                        'The Buffalo Hunter Hunter',
                        'Stephen Graham Jones',
                        'buffalo',
                    ),
                ),
            )
        ]
        records = nebula._records_from_pages(nebula._BEST_NOVEL_CONFIG, pages)
        with self.assertRaises(nebula.NebulaSourceError) as ctx:
            nebula._validate_category_archive(
                nebula._BEST_NOVEL_CONFIG, pages, records
            )
        self.assertIn('1965', str(ctx.exception))

    def test_missing_winner_fails_closed(self):
        nominated = (
            '<li><a href="https://nebulas.sfwa.org/nominated-work/dune/">'
            '<em>Dune</em></a> by '
            '<a href="https://nebulas.sfwa.org/nominees/frank-herbert/">'
            'Frank Herbert</a>. Nominated for Best Novel in 1965</li>'
        )
        pages = [('https://example.test/1965', _year_page(1965, nominated))]
        records = nebula._records_from_pages(nebula._BEST_NOVEL_CONFIG, pages)
        with self.assertRaises(nebula.NebulaSourceError) as ctx:
            nebula._validate_category_archive(
                nebula._BEST_NOVEL_CONFIG, pages, records
            )
        self.assertIn('Winner', str(ctx.exception))

    def test_ties_do_not_fail_validation(self):
        pages = [
            (
                'https://example.test/novella-1965',
                _load('best_novella_1965.html'),
            )
        ]
        records = nebula._records_from_pages(nebula._BEST_NOVELLA_CONFIG, pages)
        nebula._validate_category_archive(
            nebula._BEST_NOVELLA_CONFIG, pages, records
        )
        winners = [record for record in records if record.status == 'Winner']
        self.assertEqual(len(winners), 2)

    def test_duplicate_overlap_rows_do_not_fake_coverage(self):
        html_1965 = _year_page(
            1965, _novel_winner_li(1965, 'Dune', 'Frank Herbert', 'dune')
        )
        html_1967 = _year_page(
            1967, _novel_winner_li(1967, 'The Einstein Intersection', 'Samuel R. Delany', 'einstein')
        )
        pages = [
            ('https://example.test/1', html_1965),
            ('https://example.test/2', html_1965 + html_1967),
        ]
        records = nebula._records_from_pages(nebula._BEST_NOVEL_CONFIG, pages)
        self.assertEqual(len(records), 2)
        with self.assertRaises(nebula.NebulaSourceError) as ctx:
            nebula._validate_category_archive(
                nebula._BEST_NOVEL_CONFIG, pages, records
            )
        self.assertIn('1966', str(ctx.exception))

    def test_failed_validation_does_not_cache(self):
        nebula._clear_caches_for_tests()
        pages = [
            (
                'https://nebulas.sfwa.org/award/best-poem/',
                _year_page(
                    2025,
                    '<li><a href="/nominated-work/x/">&ldquo;X&rdquo;, by A (Z)</a>'
                    '. Nominated for Best Poem in 2025</li>',
                ),
            )
        ]
        with patch.object(
            nebula, '_fetch_category_pages', return_value=pages
        ):
            with self.assertRaises(nebula.NebulaSourceError):
                nebula._get_category_pages(nebula._BEST_POEM_CONFIG)
        self.assertNotIn(nebula._BEST_POEM_CONFIG.key, nebula._pages_cache)
        self.assertNotIn(nebula._BEST_POEM_CONFIG.key, nebula._records_cache)


class NebulaMatchingRegressionTests(unittest.TestCase):
    def test_title_and_author_are_both_required(self):
        record = nebula._parse_best_novel_html(_load('best_novel_1965.html'))[0]
        self.assertFalse(nebula._record_matches(record, '', 'Frank Herbert'))
        self.assertFalse(nebula._record_matches(record, 'Dune', ''))
        self.assertTrue(nebula._record_matches(record, 'Dune', 'Frank Herbert'))
        self.assertFalse(nebula._record_matches(record, 'Dune', 'Frank Herberts'))
        self.assertFalse(nebula._record_matches(record, 'Dune Messiah', 'Frank Herbert'))

    def test_calibre_two_author_ampersand_matches_official_and(self):
        self.assertTrue(
            nebula._authors_match(
                'Amal El-Mohtar & Max Gladstone',
                'Amal El-Mohtar and Max Gladstone',
            )
        )

    def test_reversed_or_partial_author_lists_do_not_match(self):
        official = 'Amal El-Mohtar and Max Gladstone'
        self.assertFalse(
            nebula._authors_match('Max Gladstone & Amal El-Mohtar', official)
        )
        self.assertFalse(nebula._authors_match('Amal El-Mohtar', official))

    def test_three_author_oxford_comma_matches_calibre_list(self):
        self.assertTrue(
            nebula._authors_match(
                'Gardner Dozois & Jack Dann & Michael Swanwick',
                'Gardner Dozois, Jack Dann, and Michael Swanwick',
            )
        )

    def test_four_author_official_list_matches_calibre_list(self):
        self.assertTrue(
            nebula._authors_match(
                'Ann Leckie & Nisi Shawl & Ruthanna Emrys & Fran Wilde',
                'Ann Leckie, Nisi Shawl, Ruthanna Emrys, and Fran Wilde',
            )
        )

    def test_literal_calibre_ampersand_is_not_an_author_separator(self):
        self.assertEqual(
            nebula._split_calibre_author_query('Smith && Jones'),
            ('Smith & Jones',),
        )
        self.assertTrue(
            nebula._authors_match('Smith && Jones', 'Smith & Jones')
        )
        self.assertFalse(
            nebula._authors_match('Smith && Jones', 'Smith and Jones')
        )

    def test_role_prose_falls_back_to_whole_string(self):
        self.assertFalse(
            nebula._authors_match(
                'Jane Doe & John Smith',
                'Jane Doe with John Smith',
            )
        )

    def test_typography_subtitle_and_conjunction_regressions(self):
        self.assertTrue(
            nebula._titles_match('Don’t Look Now', "Don't Look Now")
        )
        self.assertTrue(
            nebula._titles_match('Seveneves', 'Seveneves: A Novel')
        )
        self.assertTrue(
            nebula._titles_match(
                'Jonathan Strange and Mr Norrell',
                'Jonathan Strange & Mr Norrell',
            )
        )

    def test_lookup_rejects_empty_title_or_author(self):
        with self.assertRaises(ValueError):
            nebula.lookup('', 'Frank Herbert')
        with self.assertRaises(ValueError):
            nebula.lookup('Dune', '')


class NebulaBestNovelResultTests(unittest.TestCase):
    def test_best_novel_formatting_unchanged(self):
        record = nebula._parse_best_novel_html(_load('best_novel_1965.html'))[0]
        result = nebula._to_award_result(record)
        self.assertEqual(result.identity_kind, 'work')
        self.assertIsNone(result.rank)
        self.assertEqual(
            format_award_result(result),
            'Winner - 1965 Nebula Award - Best Novel',
        )
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )


class NebulaConcurrencyAndRecordCacheTests(unittest.TestCase):
    def tearDown(self):
        nebula._clear_caches_for_tests()

    def test_categories_load_concurrently_and_preserve_config_order(self):
        pair_barrier = threading.Barrier(2, timeout=2)
        hold = threading.Event()
        two_ready = threading.Event()
        lock = threading.Lock()
        active = 0
        max_active = 0
        ready_count = 0

        def _fake_load(config):
            nonlocal active, max_active, ready_count
            with lock:
                active += 1
                max_active = max(max_active, active)
                ready_count += 1
                if ready_count >= 2:
                    two_ready.set()
            try:
                pair_barrier.wait()
                if not hold.wait(timeout=2):
                    raise TimeoutError('category loaders were not released')
                record = nebula._ParsedRecord(
                    award_year=2015,
                    award_name=config.award_name,
                    category=config.category,
                    status='Winner',
                    work_title='Updraft',
                    work_author='Fran Wilde',
                    source_url=f'https://example.test/{config.key}',
                )
                return (), (record,)
            finally:
                with lock:
                    active -= 1

        with patch.object(nebula, '_load_category', side_effect=_fake_load):
            box = {}

            def _lookup():
                box['results'] = nebula.lookup('Updraft', 'Fran Wilde')

            thread = threading.Thread(target=_lookup)
            thread.start()
            self.assertTrue(two_ready.wait(timeout=2))
            with lock:
                observed_max = max_active
            self.assertGreaterEqual(observed_max, 2)
            self.assertLessEqual(observed_max, nebula._MAX_CATEGORY_WORKERS)
            hold.set()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            with lock:
                self.assertLessEqual(max_active, nebula._MAX_CATEGORY_WORKERS)

        results = box['results']
        self.assertEqual(
            [result.category for result in results],
            [config.category for config in nebula._AWARD_CONFIGS],
        )

    def test_second_lookup_does_not_reparse_cached_records(self):
        nebula._clear_caches_for_tests()
        html = _load('best_novel_1965.html')
        for config in nebula._AWARD_CONFIGS:
            if config is nebula._BEST_NOVEL_CONFIG:
                continue
            nebula._records_cache[config.key] = ()
        nebula._pages_cache[nebula._BEST_NOVEL_CONFIG.key] = (
            ('https://nebulas.sfwa.org/award/best-novel/', html),
        )
        parse_calls = {'count': 0}
        original = nebula._records_from_pages

        def _counting_records(config, pages):
            parse_calls['count'] += 1
            return original(config, pages)

        with patch.object(
            nebula, '_records_from_pages', side_effect=_counting_records
        ):
            first = nebula.lookup('Dune', 'Frank Herbert')
            first_count = parse_calls['count']
            second = nebula.lookup('Dune', 'Frank Herbert')
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertGreaterEqual(first_count, 1)
        self.assertEqual(parse_calls['count'], first_count)

    def test_category_failures_raise_in_configured_order(self):
        def _fake_load(config):
            if config is nebula._BEST_NOVELLA_CONFIG:
                raise nebula.NebulaSourceError('novella failed')
            if config is nebula._BEST_POEM_CONFIG:
                raise nebula.NebulaSourceError('poem failed')
            return (), ()

        with patch.object(nebula, '_load_category', side_effect=_fake_load):
            with self.assertRaises(nebula.NebulaSourceError) as ctx:
                nebula.lookup('Dune', 'Frank Herbert')
        self.assertEqual(str(ctx.exception), 'novella failed')

    def test_cached_pages_without_records_are_validated(self):
        nebula._clear_caches_for_tests()
        invalid_pages = (
            (
                'https://example.test/latest-only',
                _year_page(
                    2025,
                    _novel_winner_li(
                        2025,
                        'The Buffalo Hunter Hunter',
                        'Stephen Graham Jones',
                        'buffalo',
                    ),
                ),
            ),
        )
        nebula._pages_cache[nebula._BEST_NOVEL_CONFIG.key] = invalid_pages
        with self.assertRaises(nebula.NebulaSourceError) as ctx:
            nebula._load_category(nebula._BEST_NOVEL_CONFIG)
        self.assertIn('1965', str(ctx.exception))
        self.assertNotIn(nebula._BEST_NOVEL_CONFIG.key, nebula._records_cache)
        self.assertIs(
            nebula._pages_cache[nebula._BEST_NOVEL_CONFIG.key],
            invalid_pages,
        )


if __name__ == '__main__':
    unittest.main()
