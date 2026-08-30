"""Offline coverage for static award-source help metadata."""

from __future__ import annotations

import unittest
from urllib.parse import urlparse
from unittest.mock import patch

from awards.source_info import (
    SOURCE_INFOS,
    SourceInfo,
    format_identity_scopes,
    format_source_info,
)
from awards.source_registry import AWARD_SOURCES
from awards.sources import (
    booker,
    german_book_prize,
    hugo,
    locus,
    miles_franklin,
    nebula,
    newbery,
    nobel,
    prix_goncourt,
    pulitzer,
    world_fantasy,
)


def _info(key: str) -> SourceInfo:
    matches = [item for item in SOURCE_INFOS if item.key == key]
    if len(matches) != 1:
        raise AssertionError(f'expected one SourceInfo for {key!r}')
    return matches[0]


class SourceInfoModelTests(unittest.TestCase):
    def test_rejects_empty_required_fields(self):
        with self.assertRaises(ValueError):
            SourceInfo(
                key='',
                display_name='Pulitzer Prizes',
                categories=('Fiction',),
                identity_scopes=('work',),
                homepage_url='https://www.pulitzer.org/',
                description='A description.',
            )
        with self.assertRaises(ValueError):
            SourceInfo(
                key='pulitzer',
                display_name='',
                categories=('Fiction',),
                identity_scopes=('work',),
                homepage_url='https://www.pulitzer.org/',
                description='A description.',
            )
        with self.assertRaises(ValueError):
            SourceInfo(
                key='pulitzer',
                display_name='Pulitzer Prizes',
                categories=(),
                identity_scopes=('work',),
                homepage_url='https://www.pulitzer.org/',
                description='A description.',
            )
        with self.assertRaises(ValueError):
            SourceInfo(
                key='pulitzer',
                display_name='Pulitzer Prizes',
                categories=('Fiction',),
                identity_scopes=(),
                homepage_url='https://www.pulitzer.org/',
                description='A description.',
            )
        with self.assertRaises(ValueError):
            SourceInfo(
                key='pulitzer',
                display_name='Pulitzer Prizes',
                categories=('Fiction',),
                identity_scopes=('volume',),
                homepage_url='https://www.pulitzer.org/',
                description='A description.',
            )
        with self.assertRaises(ValueError):
            SourceInfo(
                key='pulitzer',
                display_name='Pulitzer Prizes',
                categories=('Fiction',),
                identity_scopes=('work',),
                homepage_url='http://www.pulitzer.org/',
                description='A description.',
            )
        with self.assertRaises(ValueError):
            SourceInfo(
                key='pulitzer',
                display_name='Pulitzer Prizes',
                categories=('Fiction',),
                identity_scopes=('work',),
                homepage_url='https://www.pulitzer.org/',
                description='',
            )
        with self.assertRaises(ValueError):
            SourceInfo(
                key='pulitzer',
                display_name='Pulitzer Prizes',
                categories=('Fiction',),
                identity_scopes=('work',),
                homepage_url='https://www.pulitzer.org/',
                description='A description.',
                limitation='   ',
            )


class SourceInfoRegistryConsistencyTests(unittest.TestCase):
    def test_one_info_record_per_award_source_in_registry_order(self):
        self.assertEqual(
            tuple(info.key for info in SOURCE_INFOS),
            tuple(source.key for source in AWARD_SOURCES),
        )
        self.assertEqual(
            tuple(info.display_name for info in SOURCE_INFOS),
            tuple(source.display_name for source in AWARD_SOURCES),
        )
        self.assertEqual(len(SOURCE_INFOS), len(AWARD_SOURCES))
        self.assertEqual(len(SOURCE_INFOS), 11)
        self.assertNotIn(
            'national_book_awards',
            [info.key for info in SOURCE_INFOS],
        )
        self.assertNotIn(
            'National Book Awards',
            [info.display_name for info in SOURCE_INFOS],
        )

    def test_keys_are_unique(self):
        keys = [info.key for info in SOURCE_INFOS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_every_record_has_required_help_fields(self):
        for info in SOURCE_INFOS:
            with self.subTest(key=info.key):
                self.assertTrue(info.categories)
                self.assertTrue(info.identity_scopes)
                parsed = urlparse(info.homepage_url)
                self.assertEqual(parsed.scheme, 'https')
                self.assertTrue(parsed.netloc)
                self.assertTrue(info.description.strip())


class SourceInfoCategoryTests(unittest.TestCase):
    def test_pulitzer_categories_and_limitation(self):
        info = _info('pulitzer')
        self.assertEqual(
            info.categories,
            tuple(category for category, _url in pulitzer._CATEGORY_URLS),
        )
        self.assertEqual(info.categories, ('Fiction', 'Novel'))
        self.assertIsNotNone(info.limitation)
        self.assertIn('unavailable', info.limitation.casefold())
        self.assertNotIn('403', info.limitation)
        self.assertNotIn('cloudflare', info.limitation.casefold())

    def test_nebula_categories_follow_award_configs(self):
        info = _info('nebula')
        expected = []
        for config in nebula._AWARD_CONFIGS:
            if config.award_name == nebula.AWARD_NAME_NEBULA:
                expected.append(config.category)
            else:
                expected.append(f'{config.award_name} — {config.category}')
        self.assertEqual(info.categories, tuple(expected))
        self.assertIn(nebula.CATEGORY_BEST_NOVEL, info.categories)
        self.assertIn(nebula.CATEGORY_BEST_POEM, info.categories)
        self.assertIn(
            f'{nebula.NORTON_AWARD_NAME} — {nebula.NORTON_CATEGORY}',
            info.categories,
        )

    def test_hugo_categories_include_work_and_series_labels(self):
        info = _info('hugo')
        self.assertEqual(info.categories, hugo._PARSED_CATEGORIES)
        self.assertIn(hugo.CATEGORY_BEST_NOVEL, info.categories)
        self.assertIn(hugo.CATEGORY_BEST_SERIES, info.categories)
        self.assertIn(hugo.CATEGORY_BEST_ALL_TIME_SERIES, info.categories)
        self.assertEqual(
            info.categories[-2:],
            (hugo.CATEGORY_BEST_SERIES, hugo.CATEGORY_BEST_ALL_TIME_SERIES),
        )

    def test_locus_categories_match_supported_labels_only(self):
        info = _info('locus')
        self.assertEqual(info.categories, tuple(locus._SUPPORTED_CATEGORY_LABELS))
        self.assertIn('Collection', info.categories)
        advertised = {label.casefold() for label in info.categories}
        for unsupported in ('anthology', 'editor', 'publisher'):
            self.assertNotIn(unsupported, advertised)
            self.assertIn(unsupported, locus._RECOGNIZED_UNSUPPORTED_KEYS)

    def test_world_fantasy_categories_match_canonical_labels(self):
        info = _info('world_fantasy')
        self.assertEqual(info.categories, world_fantasy._CANONICAL_CATEGORIES)
        self.assertEqual(
            info.categories,
            ('Novel', 'Novella', 'Short Fiction', 'Collection'),
        )

    def test_nobel_literature_only(self):
        info = _info('nobel')
        self.assertEqual(info.display_name, 'Nobel Award')
        self.assertEqual(info.categories, (nobel.CATEGORY_LITERATURE,))
        self.assertEqual(info.categories, ('Literature',))

    def test_newbery_childrens_literature_only(self):
        info = _info('newbery')
        self.assertEqual(info.categories, (newbery.CATEGORY,))
        self.assertEqual(info.categories, ("Children's Literature",))

    def test_booker_fiction_only(self):
        info = _info('booker')
        self.assertEqual(info.categories, (booker.CATEGORY,))
        self.assertEqual(info.categories, ('Fiction',))
        self.assertNotIn('International', info.description)
        self.assertNotIn('International', info.limitation or '')

    def test_german_book_prize_fiction_only(self):
        info = _info('german_book_prize')
        self.assertEqual(info.categories, (german_book_prize.CATEGORY,))
        self.assertEqual(info.categories, ('Fiction',))
        self.assertEqual(info.display_name, 'Deutscher Buchpreis')
        self.assertNotIn('English-language', info.description)


class SourceInfoScopeAndHomepageTests(unittest.TestCase):
    def test_identity_scopes(self):
        expected = {
            'pulitzer': ('work',),
            'nebula': ('work',),
            'hugo': ('work', 'series'),
            'locus': ('work',),
            'world_fantasy': ('work',),
            'nobel': ('author', 'work'),
            'booker': ('work',),
            'german_book_prize': ('work',),
            'prix_goncourt': ('work',),
            'miles_franklin': ('work',),
            'newbery': ('work',),
        }
        self.assertEqual(
            {info.key: info.identity_scopes for info in SOURCE_INFOS},
            expected,
        )

    def test_homepage_hosts(self):
        hosts = {
            info.key: urlparse(info.homepage_url).hostname
            for info in SOURCE_INFOS
        }
        self.assertEqual(hosts['pulitzer'], 'www.pulitzer.org')
        self.assertEqual(hosts['nebula'], 'nebulas.sfwa.org')
        self.assertEqual(hosts['hugo'], 'www.thehugoawards.org')
        self.assertEqual(hosts['locus'], 'www.sfadb.com')
        self.assertEqual(hosts['world_fantasy'], 'worldfantasy.org')
        self.assertEqual(hosts['nobel'], 'www.nobelprize.org')
        self.assertEqual(hosts['booker'], 'thebookerprizes.com')
        self.assertEqual(hosts['german_book_prize'], 'www.deutscher-buchpreis.de')
        self.assertEqual(hosts['prix_goncourt'], 'www.academiegoncourt.com')
        self.assertEqual(hosts['miles_franklin'], 'www.perpetual.com.au')
        self.assertEqual(hosts['newbery'], 'www.ala.org')
        self.assertEqual(_info('pulitzer').homepage_url, pulitzer.SOURCE_HOME_URL)
        self.assertEqual(_info('nebula').homepage_url, nebula.SOURCE_HOME_URL)
        self.assertEqual(_info('hugo').homepage_url, hugo.SOURCE_HOME_URL)
        self.assertEqual(_info('locus').homepage_url, locus.SFADB_ORIGIN)
        self.assertEqual(
            _info('world_fantasy').homepage_url,
            world_fantasy.SOURCE_HOME_URL,
        )
        self.assertEqual(_info('nobel').homepage_url, nobel.SOURCE_HOME_URL)
        self.assertEqual(_info('booker').homepage_url, booker.SOURCE_HOME_URL)
        self.assertEqual(
            _info('german_book_prize').homepage_url,
            german_book_prize.ARCHIVE_INDEX_URL,
        )
        self.assertEqual(
            _info('prix_goncourt').homepage_url,
            prix_goncourt.SOURCE_HOME_URL,
        )
        self.assertEqual(
            _info('miles_franklin').homepage_url,
            miles_franklin.SOURCE_HOME_URL,
        )
        self.assertEqual(_info('newbery').homepage_url, newbery.SOURCE_HOME_URL)

    def test_only_documented_sources_have_limitations(self):
        for info in SOURCE_INFOS:
            if info.key in {
                'pulitzer',
                'booker',
                'german_book_prize',
                'prix_goncourt',
                'miles_franklin',
                'newbery',
            }:
                self.assertIsNotNone(info.limitation)
            else:
                self.assertIsNone(info.limitation)

    def test_booker_description_and_limitation_cover_shortlist_not_longlist(self):
        info = _info('booker')
        description = info.description.casefold()
        self.assertIn('booker prize', description)
        self.assertIn('winner', description)
        self.assertIn('shortlist', description)
        self.assertNotIn('international', description)
        self.assertNotIn('the booker prizes', description)
        limitation = info.limitation.casefold()
        self.assertIn('longlisted-only', limitation)
        self.assertNotIn('international', limitation)

    def test_german_book_prize_description_and_limitation(self):
        info = _info('german_book_prize')
        description = info.description.casefold()
        self.assertIn('deutscher buchpreis', description)
        self.assertIn('german book prize', description)
        self.assertIn('winner', description)
        self.assertIn('shortlist', description)
        self.assertNotIn('english-language', description)
        limitation = info.limitation.casefold()
        self.assertIn('longlisted-only', limitation)

    def test_prix_goncourt_fiction_only(self):
        info = _info('prix_goncourt')
        self.assertEqual(info.categories, (prix_goncourt.CATEGORY,))
        self.assertEqual(info.categories, ('Fiction',))
        self.assertEqual(info.display_name, 'Prix Goncourt')
        self.assertNotIn('Goncourt Prize', info.description)
        self.assertNotIn('Lycéens', info.description)

    def test_miles_franklin_fiction_only(self):
        info = _info('miles_franklin')
        self.assertEqual(info.categories, (miles_franklin.CATEGORY,))
        self.assertEqual(info.categories, ('Fiction',))
        self.assertEqual(info.display_name, 'Miles Franklin Literary Award')
        self.assertNotIn('1957-present', info.description)

    def test_prix_goncourt_description_and_limitation(self):
        info = _info('prix_goncourt')
        description = info.description.casefold()
        self.assertIn('prix goncourt', description)
        self.assertIn('winner', description)
        self.assertIn('académie goncourt', description)
        self.assertIn('fiction', description)
        self.assertNotIn('lycéens', description)
        limitation = info.limitation.casefold()
        self.assertIn('1903', limitation)
        self.assertIn('2018', limitation)
        self.assertIn('3ème', limitation)
        self.assertIn('finalist', limitation)
        self.assertIn('first', limitation)
        self.assertIn('second', limitation)
        self.assertIn('not returned', limitation)
        self.assertNotIn('2008', limitation)
        self.assertNotIn('top 4', limitation)
        self.assertNotIn('this version', limitation)

    def test_miles_franklin_description_and_limitation(self):
        info = _info('miles_franklin')
        description = info.description.casefold()
        self.assertIn('miles franklin', description)
        self.assertIn('winner', description)
        self.assertIn('shortlist', description)
        self.assertIn('perpetual', description)
        limitation = info.limitation.casefold()
        self.assertIn('2007', limitation)
        self.assertIn('2025', limitation)
        self.assertIn('finalist', limitation)
        self.assertIn('longlist', limitation)
        self.assertIn('pre-2007', limitation)
        self.assertNotIn('1957-present', limitation)
        self.assertNotIn('goodreads', limitation)

    def test_nobel_description_covers_author_and_cited_work_scope(self):
        text = _info('nobel').description.casefold()
        self.assertIn('author', text)
        self.assertIn('[author: name]', text)
        self.assertIn('work', text)
        self.assertNotIn('sholokhov', text)

    def test_newbery_description_and_limitation_cover_1930_2023(self):
        info = _info('newbery')
        description = info.description.casefold()
        self.assertIn('newbery medal', description)
        self.assertIn('honor', description)
        self.assertIn('ala', description)
        self.assertNotIn('1922', description)
        self.assertNotIn('2024', description)
        self.assertNotIn('2026', description)
        limitation = info.limitation.casefold()
        self.assertIn('1930', limitation)
        self.assertIn('2023', limitation)
        self.assertNotIn('1922', limitation)
        self.assertNotIn('2024', limitation)
        self.assertNotIn('2026', limitation)


class SourceInfoImportAndFormatTests(unittest.TestCase):
    def test_reading_source_infos_does_not_open_the_network(self):
        import importlib
        import urllib.request

        import awards.source_info as source_info

        with patch.object(urllib.request, 'urlopen') as mocked_open:
            reloaded = importlib.reload(source_info)
            infos = reloaded.SOURCE_INFOS
            self.assertEqual(len(infos), 11)
            self.assertEqual(infos[0].key, 'pulitzer')
            self.assertEqual(infos[-1].key, 'newbery')
            mocked_open.assert_not_called()

    def test_format_identity_scopes_uses_user_facing_labels(self):
        self.assertEqual(format_identity_scopes(('work',)), 'Work awards')
        self.assertEqual(
            format_identity_scopes(('work', 'series')),
            'Work awards, Series awards',
        )
        self.assertEqual(
            format_identity_scopes(('author', 'work')),
            'Author awards, Work awards',
        )

    def test_format_source_info_includes_categories_scope_and_note(self):
        formatted = format_source_info(_info('pulitzer'))
        self.assertEqual(
            formatted.splitlines()[0],
            'Pulitzer Prizes',
        )
        self.assertIn('Categories: Fiction, Novel', formatted)
        self.assertIn('Scope: Work awards', formatted)
        self.assertIn('Fiction and Novel awards from Pulitzer.org.', formatted)
        self.assertIn('Note: Pulitzer.org sometimes blocks automated checks', formatted)
        self.assertNotIn('<', formatted)

    def test_format_source_info_omits_note_when_unlimited(self):
        formatted = format_source_info(_info('hugo'))
        self.assertIn('Scope: Work awards, Series awards', formatted)
        self.assertNotIn('Note:', formatted)

    def test_format_source_info_includes_booker_longlist_limitation(self):
        formatted = format_source_info(_info('booker'))
        self.assertEqual(formatted.splitlines()[0], 'The Booker Prize')
        self.assertIn('Categories: Fiction', formatted)
        self.assertIn('Scope: Work awards', formatted)
        self.assertIn('official Booker Prize archive', formatted)
        self.assertIn('Note: Longlisted-only works are not returned.', formatted)
        self.assertNotIn('International', formatted)
        self.assertNotIn('The Booker Prizes', formatted)

    def test_format_source_info_includes_german_book_prize_limitation(self):
        formatted = format_source_info(_info('german_book_prize'))
        self.assertEqual(formatted.splitlines()[0], 'Deutscher Buchpreis')
        self.assertIn('Categories: Fiction', formatted)
        self.assertIn('Scope: Work awards', formatted)
        self.assertIn('German Book Prize', formatted)
        self.assertIn('Deutscher Buchpreis', formatted)
        self.assertIn('Note: Longlisted-only works are not returned.', formatted)
        self.assertNotIn('English-language', formatted)

    def test_format_source_info_includes_prix_goncourt_limitation(self):
        formatted = format_source_info(_info('prix_goncourt'))
        self.assertEqual(formatted.splitlines()[0], 'Prix Goncourt')
        self.assertIn('Categories: Fiction', formatted)
        self.assertIn('Scope: Work awards', formatted)
        self.assertIn('Académie Goncourt', formatted)
        self.assertIn('Note:', formatted)
        self.assertIn('1903', formatted)
        self.assertIn('2018', formatted)
        self.assertIn('3ème', formatted)
        self.assertIn('not returned', formatted.casefold())
        self.assertNotIn('this version', formatted)
        self.assertNotIn('top 4', formatted)
        self.assertNotIn('Goncourt Prize', formatted)
        self.assertNotIn('Lycéens', formatted)

    def test_format_source_info_includes_miles_franklin_limitation(self):
        formatted = format_source_info(_info('miles_franklin'))
        self.assertEqual(formatted.splitlines()[0], 'Miles Franklin Literary Award')
        self.assertIn('Categories: Fiction', formatted)
        self.assertIn('Scope: Work awards', formatted)
        self.assertIn('2007', formatted)
        self.assertIn('2025', formatted)
        self.assertIn('longlist', formatted.casefold())
        self.assertNotIn('1957-present', formatted)


if __name__ == '__main__':
    unittest.main()
