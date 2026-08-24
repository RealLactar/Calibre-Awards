"""Offline unittest coverage for the Nobel Prize in Literature source."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from awards.formatter import format_award_result
from awards.presentation import CITED_WORK_SCOPE_NOTE
from awards.qualifier import QualificationDecision, qualify_award_result
from awards.sources import nobel


def _en(text: str) -> dict[str, str]:
    return {'en': text}


def _facts_link(year: int, slug: str, name: str) -> dict:
    return {
        'rel': 'external',
        'href': f'https://www.nobelprize.org/prizes/literature/{year}/{slug}/facts/',
        'title': f'{name} - Facts',
        'action': 'GET',
        'types': 'text/html',
        'class': ['laureate facts'],
    }


def _api_prize_link(year: int) -> dict:
    return {
        'rel': 'nobelPrize',
        'href': f'https://api.nobelprize.org/2/nobelPrize/lit/{year}',
        'action': 'GET',
        'types': 'application/json',
    }


def _laureate(
    laureate_id: str,
    known: str,
    year: int,
    slug: str,
    *,
    full: str | None = None,
    given: str | None = None,
    family: str | None = None,
    prize_status: str = 'received',
    pen_name_of: str | None = None,
    extra_links: list | None = None,
) -> dict:
    prize_links = [_api_prize_link(year), _facts_link(year, slug, known)]
    if extra_links:
        prize_links.extend(extra_links)
    record = {
        'id': laureate_id,
        'knownName': _en(known),
        'fullName': _en(full or known),
        'fileName': slug,
        'links': [
            {
                'rel': 'laureate',
                'href': f'https://api.nobelprize.org/2/laureate/{laureate_id}',
                'action': 'GET',
                'types': 'application/json',
            },
            {
                'rel': 'external',
                'href': f'https://www.nobelprize.org/laureate/{laureate_id}',
                'title': f'{known} - Facts',
                'action': 'GET',
                'types': 'text/html',
                'class': ['laureate facts'],
            },
        ],
        'nobelPrizes': [
            {
                'awardYear': str(year),
                'category': _en('Literature'),
                'categoryFullName': _en('The Nobel Prize in Literature'),
                'prizeStatus': prize_status,
                'portion': '1',
                'motivation': _en('official motivation'),
                'links': prize_links,
            }
        ],
    }
    if given is not None:
        record['givenName'] = _en(given)
    if family is not None:
        record['familyName'] = _en(family)
    if pen_name_of is not None:
        record['penName'] = f'(pen-name of {pen_name_of})'
        record['penNameOf'] = {'fullName': pen_name_of}
    return record


LAUREATES = [
    _laureate(
        '625',
        'Ernest Hemingway',
        1954,
        'hemingway',
        full='Ernest Miller Hemingway',
        given='Ernest',
        family='Hemingway',
    ),
    _laureate(
        '619',
        'T.S. Eliot',
        1948,
        'eliot',
        full='Thomas Stearns Eliot',
        given='T.S.',
        family='Eliot',
    ),
    _laureate(
        '593',
        'William Butler Yeats',
        1923,
        'yeats',
        given='William Butler',
        family='Yeats',
    ),
    _laureate(
        '645',
        'Pablo Neruda',
        1971,
        'neruda',
        given='Pablo',
        family='Neruda',
        pen_name_of='Neftalí Ricardo Reyes Basoalto',
    ),
    _laureate(
        '659',
        'Gabriel García Márquez',
        1982,
        'marquez',
        given='Gabriel',
        family='García Márquez',
    ),
    _laureate(
        '675',
        'José Saramago',
        1998,
        'saramago',
        given='José',
        family='Saramago',
    ),
    _laureate(
        '947',
        'Kazuo Ishiguro',
        2017,
        'ishiguro',
        given='Kazuo',
        family='Ishiguro',
    ),
    _laureate(
        '1042',
        'Han Kang',
        2024,
        'han',
        given='Kang',
        family='Han',
    ),
    _laureate(
        '1056',
        'László Krasznahorkai',
        2025,
        'krasznahorkai',
        given='László',
        family='Krasznahorkai',
    ),
    _laureate(
        '637',
        'Jean-Paul Sartre',
        1964,
        'sartre',
        given='Jean-Paul',
        family='Sartre',
        prize_status='declined',
    ),
    _laureate(
        '629',
        'Boris Pasternak',
        1958,
        'pasternak',
        full='Boris Leonidovich Pasternak',
        given='Boris',
        family='Pasternak',
        prize_status='restricted',
    ),
    _laureate(
        '937',
        'Bob Dylan',
        2016,
        'dylan',
        given='Bob',
        family='Dylan',
    ),
    _laureate(
        '571',
        'Theodor Mommsen',
        1902,
        'mommsen',
        full='Christian Matthias Theodor Mommsen',
        given='Theodor',
        family='Mommsen',
    ),
    _laureate(
        '588',
        'Carl Spitteler',
        1919,
        'spitteler',
        full='Carl Friedrich Georg Spitteler',
        given='Carl',
        family='Spitteler',
    ),
    _laureate(
        '589',
        'Knut Hamsun',
        1920,
        'hamsun',
        full='Knut Pedersen Hamsun',
        given='Knut',
        family='Hamsun',
    ),
    _laureate(
        '594',
        'Władysław Reymont',
        1924,
        'reymont',
        full='Władysław Stanisław Reymont',
        given='Władysław',
        family='Reymont',
    ),
    _laureate(
        '602',
        'Thomas Mann',
        1929,
        'mann',
        given='Thomas',
        family='Mann',
    ),
    _laureate(
        '605',
        'John Galsworthy',
        1932,
        'galsworthy',
        given='John',
        family='Galsworthy',
    ),
    _laureate(
        '609',
        'Roger Martin du Gard',
        1937,
        'gard',
        given='Roger',
        family='Martin du Gard',
    ),
    _laureate(
        '638',
        'Mikhail Sholokhov',
        1965,
        'sholokhov',
        full='Mikhail Aleksandrovich Sholokhov',
        given='Mikhail',
        family='Sholokhov',
    ),
]

FIXTURE = {
    'laureates': LAUREATES,
    'meta': {
        'offset': 0,
        'limit': 200,
        'nobelPrizeCategory': 'lit',
        'count': len(LAUREATES),
    },
}
FIXTURE_BODY = json.dumps(FIXTURE)


def _lookup(title: str, author: str, series: str | None = None):
    with patch.object(nobel, '_request_json', return_value=(200, FIXTURE_BODY)):
        return nobel.lookup(title, author, series=series)


class NobelTestCase(unittest.TestCase):
    def setUp(self) -> None:
        nobel._reset_runtime_state()

    def tearDown(self) -> None:
        nobel._reset_runtime_state()


class LookupTests(NobelTestCase):
    def test_hemingway_arbitrary_book_is_author_level_1954(self):
        results = _lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.identity_kind, 'author')
        self.assertEqual(result.work_title, 'Ernest Hemingway')
        self.assertEqual(result.work_author, 'Ernest Hemingway')
        self.assertEqual(result.award_name, 'Nobel Prize')
        self.assertEqual(result.award_year, 1954)
        self.assertEqual(result.category, 'Literature')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'NobelPrize.org')
        self.assertEqual(
            result.source_url,
            'https://www.nobelprize.org/prizes/literature/1954/hemingway/facts/',
        )
        self.assertIsNone(result.notes)

    def test_hemingway_formats_with_author_scope(self):
        results = _lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        self.assertEqual(
            format_award_result(results[0]),
            'Winner - 1954 Nobel Prize - Literature [Author: Ernest Hemingway]',
        )

    def test_full_name_hemingway_matches(self):
        results = _lookup('A Farewell to Arms', 'Ernest Miller Hemingway')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_author, 'Ernest Hemingway')

    def test_non_laureate_is_empty(self):
        self.assertEqual(_lookup('Dune', 'Frank Herbert'), [])

    def test_ishiguro_2017(self):
        results = _lookup('Never Let Me Go', 'Kazuo Ishiguro')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].award_year, 2017)
        self.assertEqual(results[0].work_author, 'Kazuo Ishiguro')

    def test_han_kang_2024(self):
        results = _lookup('The Vegetarian', 'Han Kang')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].award_year, 2024)
        self.assertEqual(results[0].work_author, 'Han Kang')

    def test_krasznahorkai_2025(self):
        results = _lookup('Satantango', 'László Krasznahorkai')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].award_year, 2025)
        self.assertEqual(results[0].work_author, 'László Krasznahorkai')

    def test_bob_dylan_matches_known_name_only(self):
        results = _lookup('Tarantula', 'Bob Dylan')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].award_year, 2016)

    def test_empty_title_raises(self):
        with self.assertRaises(ValueError):
            nobel.lookup('  ', 'Ernest Hemingway')

    def test_empty_author_raises(self):
        with self.assertRaises(ValueError):
            nobel.lookup('For Whom the Bell Tolls', '  ')


class MatchingTests(NobelTestCase):
    def test_garcia_marquez_ascii_fold(self):
        accented = _lookup('One Hundred Years of Solitude', 'Gabriel García Márquez')
        folded = _lookup('One Hundred Years of Solitude', 'Gabriel Garcia Marquez')
        self.assertEqual(len(accented), 1)
        self.assertEqual(len(folded), 1)
        self.assertEqual(accented[0].work_author, 'Gabriel García Márquez')
        self.assertEqual(folded[0].work_author, 'Gabriel García Márquez')

    def test_saramago_ascii_fold(self):
        accented = _lookup('Blindness', 'José Saramago')
        folded = _lookup('Blindness', 'Jose Saramago')
        self.assertEqual(len(accented), 1)
        self.assertEqual(len(folded), 1)

    def test_krasznahorkai_ascii_fold(self):
        folded = _lookup('Satantango', 'Laszlo Krasznahorkai')
        self.assertEqual(len(folded), 1)
        self.assertEqual(folded[0].work_author, 'László Krasznahorkai')

    def test_eliot_initials_spacing_and_full_name(self):
        compact = _lookup('Four Quartets', 'T.S. Eliot')
        spaced = _lookup('Four Quartets', 'T. S. Eliot')
        full = _lookup('Four Quartets', 'Thomas Stearns Eliot')
        self.assertEqual(len(compact), 1)
        self.assertEqual(len(spaced), 1)
        self.assertEqual(len(full), 1)
        self.assertEqual(compact[0].work_author, 'T.S. Eliot')

    def test_yeats_full_name_matches_initials_do_not(self):
        self.assertEqual(len(_lookup('The Tower', 'William Butler Yeats')), 1)
        self.assertEqual(_lookup('The Tower', 'W. B. Yeats'), [])
        self.assertEqual(_lookup('The Tower', 'W.B. Yeats'), [])

    def test_neruda_known_and_legal_names(self):
        known = _lookup(
            'Twenty Love Poems and a Song of Despair',
            'Pablo Neruda',
        )
        legal = _lookup(
            'Twenty Love Poems and a Song of Despair',
            'Neftalí Ricardo Reyes Basoalto',
        )
        folded = _lookup(
            'Twenty Love Poems and a Song of Despair',
            'Neftali Ricardo Reyes Basoalto',
        )
        self.assertEqual(len(known), 1)
        self.assertEqual(len(legal), 1)
        self.assertEqual(len(folded), 1)
        self.assertEqual(known[0].work_author, 'Pablo Neruda')
        self.assertEqual(_lookup('Canto General', 'Neruda'), [])
        self.assertEqual(_lookup('Canto General', 'Reyes'), [])

    def test_han_kang_is_not_reversed(self):
        self.assertEqual(len(_lookup('The Vegetarian', 'Han Kang')), 1)
        self.assertEqual(_lookup('The Vegetarian', 'Kang Han'), [])
        self.assertEqual(_lookup('The Vegetarian', 'Han'), [])
        self.assertEqual(_lookup('The Vegetarian', 'Kang'), [])

    def test_pen_name_wrapper_is_not_a_match_candidate(self):
        self.assertEqual(
            _lookup('Canto General', '(pen-name of Neftalí Ricardo Reyes Basoalto)'),
            [],
        )


class MultiAuthorTests(NobelTestCase):
    def test_one_laureate_among_multiple_authors_is_enough(self):
        results = _lookup(
            'For Whom the Bell Tolls',
            'Someone Else & Ernest Hemingway',
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_author, 'Ernest Hemingway')

    def test_two_laureates_yield_two_distinct_results(self):
        results = _lookup(
            'Shared Shelf',
            'Ernest Hemingway & Pablo Neruda',
        )
        self.assertEqual(len(results), 2)
        by_author = {result.work_author: result for result in results}
        self.assertEqual(set(by_author), {'Ernest Hemingway', 'Pablo Neruda'})
        self.assertEqual(by_author['Ernest Hemingway'].award_year, 1954)
        self.assertEqual(by_author['Pablo Neruda'].award_year, 1971)

    def test_non_laureate_multi_author_is_empty(self):
        self.assertEqual(
            _lookup('No Prize Here', 'Someone Else & Another Person'),
            [],
        )

    def test_calibre_escaped_ampersand_stays_one_person(self):
        results = _lookup(
            'For Whom the Bell Tolls',
            'Acme && Co & Ernest Hemingway',
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_author, 'Ernest Hemingway')
        self.assertEqual(
            nobel._split_calibre_author_query('Acme && Co & Ernest Hemingway'),
            ('Acme & Co', 'Ernest Hemingway'),
        )

    def test_cited_work_with_laureate_among_multiple_authors(self):
        results = _lookup(
            'The Old Man and the Sea',
            'Someone Else & Ernest Hemingway',
        )
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.identity_kind, 'work')
        self.assertEqual(result.work_title, 'The Old Man and the Sea')
        self.assertEqual(result.work_author, 'Ernest Hemingway')

    def test_cited_work_does_not_suppress_another_laureate_author_result(self):
        results = _lookup(
            'The Old Man and the Sea',
            'Ernest Hemingway & Pablo Neruda',
        )
        self.assertEqual(len(results), 2)
        by_author = {result.work_author: result for result in results}
        self.assertEqual(set(by_author), {'Ernest Hemingway', 'Pablo Neruda'})
        self.assertEqual(by_author['Ernest Hemingway'].identity_kind, 'work')
        self.assertEqual(
            by_author['Ernest Hemingway'].work_title,
            'The Old Man and the Sea',
        )
        self.assertEqual(by_author['Pablo Neruda'].identity_kind, 'author')
        self.assertEqual(by_author['Pablo Neruda'].work_title, 'Pablo Neruda')


class CitedWorkTests(NobelTestCase):
    def _assert_one_cited_work(
        self,
        results,
        *,
        title: str,
        author: str,
        year: int,
        slug: str,
    ) -> None:
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.identity_kind, 'work')
        self.assertEqual(result.work_title, title)
        self.assertEqual(result.work_author, author)
        self.assertEqual(result.award_name, 'Nobel Prize')
        self.assertEqual(result.award_year, year)
        self.assertEqual(result.category, 'Literature')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'NobelPrize.org')
        self.assertEqual(
            result.source_url,
            f'https://www.nobelprize.org/prizes/literature/{year}/{slug}/facts/',
        )
        self.assertEqual(result.notes, CITED_WORK_SCOPE_NOTE)
        self.assertEqual(
            format_award_result(result),
            f'Winner - {year} Nobel Prize - Literature',
        )
        self.assertNotIn('[Author:', format_award_result(result))
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )

    def _assert_one_author_award(
        self,
        results,
        *,
        author: str,
        year: int,
    ) -> None:
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.identity_kind, 'author')
        self.assertEqual(result.work_title, author)
        self.assertEqual(result.work_author, author)
        self.assertEqual(result.award_year, year)
        self.assertEqual(result.category, 'Literature')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(
            format_award_result(result),
            f'Winner - {year} Nobel Prize - Literature [Author: {author}]',
        )

    def test_old_man_and_the_sea_is_work_level(self):
        results = _lookup('The Old Man and the Sea', 'Ernest Hemingway')
        self._assert_one_cited_work(
            results,
            title='The Old Man and the Sea',
            author='Ernest Hemingway',
            year=1954,
            slug='hemingway',
        )
        self.assertFalse(
            any(result.identity_kind == 'author' for result in results)
        )

    def test_old_man_and_the_sea_without_article_is_work_level(self):
        results = _lookup('Old Man and the Sea', 'Ernest Hemingway')
        self._assert_one_cited_work(
            results,
            title='The Old Man and the Sea',
            author='Ernest Hemingway',
            year=1954,
            slug='hemingway',
        )
        self.assertFalse(
            any(result.identity_kind == 'author' for result in results)
        )

    def test_old_man_and_the_sea_without_article_is_work_level(self):
        results = _lookup('Old Man and the Sea', 'Ernest Hemingway')
        self._assert_one_cited_work(
            results,
            title='The Old Man and the Sea',
            author='Ernest Hemingway',
            year=1954,
            slug='hemingway',
        )
        self.assertFalse(
            any(result.identity_kind == 'author' for result in results)
        )

    def test_for_whom_the_bell_tolls_remains_author_level(self):
        self._assert_one_author_award(
            _lookup('For Whom the Bell Tolls', 'Ernest Hemingway'),
            author='Ernest Hemingway',
            year=1954,
        )

    def test_growth_of_the_soil_is_work_level(self):
        self._assert_one_cited_work(
            _lookup('Growth of the Soil', 'Knut Hamsun'),
            title='Growth of the Soil',
            author='Knut Hamsun',
            year=1920,
            slug='hamsun',
        )

    def test_markens_grode_alias_is_work_level(self):
        self._assert_one_cited_work(
            _lookup('Markens Grøde', 'Knut Hamsun'),
            title='Growth of the Soil',
            author='Knut Hamsun',
            year=1920,
            slug='hamsun',
        )

    def test_hunger_remains_author_level(self):
        self._assert_one_author_award(
            _lookup('Hunger', 'Knut Hamsun'),
            author='Knut Hamsun',
            year=1920,
        )

    def test_buddenbrooks_is_work_level(self):
        self._assert_one_cited_work(
            _lookup('Buddenbrooks', 'Thomas Mann'),
            title='Buddenbrooks',
            author='Thomas Mann',
            year=1929,
            slug='mann',
        )

    def test_the_magic_mountain_remains_author_level(self):
        self._assert_one_author_award(
            _lookup('The Magic Mountain', 'Thomas Mann'),
            author='Thomas Mann',
            year=1929,
        )

    def test_forsyte_saga_is_work_level(self):
        self._assert_one_cited_work(
            _lookup('The Forsyte Saga', 'John Galsworthy'),
            title='The Forsyte Saga',
            author='John Galsworthy',
            year=1932,
            slug='galsworthy',
        )

    def test_man_of_property_volume_remains_author_level(self):
        self._assert_one_author_award(
            _lookup('The Man of Property', 'John Galsworthy'),
            author='John Galsworthy',
            year=1932,
        )

    def test_forsyte_series_value_is_not_used_for_work_mapping(self):
        results = _lookup(
            'The Man of Property',
            'John Galsworthy',
            series='The Forsyte Saga',
        )
        self._assert_one_author_award(
            results,
            author='John Galsworthy',
            year=1932,
        )

    def test_les_thibault_is_work_level(self):
        self._assert_one_cited_work(
            _lookup('Les Thibault', 'Roger Martin du Gard'),
            title='Les Thibault',
            author='Roger Martin du Gard',
            year=1937,
            slug='gard',
        )

    def test_thibault_volume_title_remains_author_level(self):
        self._assert_one_author_award(
            _lookup('The Gray Notebook', 'Roger Martin du Gard'),
            author='Roger Martin du Gard',
            year=1937,
        )

    def test_history_of_rome_is_work_level(self):
        self._assert_one_cited_work(
            _lookup('A History of Rome', 'Theodor Mommsen'),
            title='A History of Rome',
            author='Theodor Mommsen',
            year=1902,
            slug='mommsen',
        )

    def test_history_of_rome_official_aliases(self):
        for title in ('A history of Rome', 'Römische Geschichte'):
            with self.subTest(title=title):
                self._assert_one_cited_work(
                    _lookup(title, 'Theodor Mommsen'),
                    title='A History of Rome',
                    author='Theodor Mommsen',
                    year=1902,
                    slug='mommsen',
                )

    def test_olympian_spring_is_work_level(self):
        self._assert_one_cited_work(
            _lookup('Olympian Spring', 'Carl Spitteler'),
            title='Olympian Spring',
            author='Carl Spitteler',
            year=1919,
            slug='spitteler',
        )

    def test_olympischer_fruhling_is_not_mapped(self):
        self._assert_one_author_award(
            _lookup('Olympischer Frühling', 'Carl Spitteler'),
            author='Carl Spitteler',
            year=1919,
        )

    def test_the_peasants_is_work_level(self):
        self._assert_one_cited_work(
            _lookup('The Peasants', 'Władysław Reymont'),
            title='The Peasants',
            author='Władysław Reymont',
            year=1924,
            slug='reymont',
        )

    def test_chlopi_is_not_mapped(self):
        self._assert_one_author_award(
            _lookup('Chłopi', 'Władysław Reymont'),
            author='Władysław Reymont',
            year=1924,
        )

    def test_sholokhov_and_quiet_flows_the_don_remains_author_level(self):
        # Nobel's official specific-work list uses the non-title phrase
        # "his epic of the Don", so the plugin fails closed rather than
        # mapping And Quiet Flows the Don or Tikhii Don to a work result.
        self._assert_one_author_award(
            _lookup('And Quiet Flows the Don', 'Mikhail Sholokhov'),
            author='Mikhail Sholokhov',
            year=1965,
        )

    def test_old_man_and_the_sea_wrong_author_is_empty(self):
        self.assertEqual(
            _lookup('The Old Man and the Sea', 'Someone Else'),
            [],
        )

    def test_old_man_and_the_sea_alias_wrong_author_is_empty(self):
        self.assertEqual(
            _lookup('Old Man and the Sea', 'Someone Else'),
            [],
        )

    def test_old_man_and_the_sea_does_not_attach_to_another_laureate(self):
        results = _lookup('The Old Man and the Sea', 'Pablo Neruda')
        self._assert_one_author_award(
            results,
            author='Pablo Neruda',
            year=1971,
        )
        self.assertNotEqual(results[0].work_title, 'The Old Man and the Sea')
        self.assertNotEqual(results[0].work_author, 'Ernest Hemingway')

    def test_romische_geschichte_ascii_fold_matches(self):
        self._assert_one_cited_work(
            _lookup('Romische Geschichte', 'Theodor Mommsen'),
            title='A History of Rome',
            author='Theodor Mommsen',
            year=1902,
            slug='mommsen',
        )

    def test_markens_grode_without_oe_does_not_invent_an_alias(self):
        # ø does not decompose under Phase B ASCII folding, so this stays
        # author-level rather than inventing a Grode alias.
        self._assert_one_author_award(
            _lookup('Markens Grode', 'Knut Hamsun'),
            author='Knut Hamsun',
            year=1920,
        )

    def test_reymont_ascii_l_stroke_is_not_folded(self):
        # ł does not decompose under Phase B ASCII folding.
        self.assertEqual(
            _lookup('The Peasants', 'Wladyslaw Reymont'),
            [],
        )

    def test_substring_title_does_not_map_forsyte(self):
        self._assert_one_author_award(
            _lookup('The Forsyte Saga Recalled', 'John Galsworthy'),
            author='John Galsworthy',
            year=1932,
        )


class StatusTests(NobelTestCase):
    def test_sartre_declined_still_qualifies(self):
        results = _lookup('Nausea', 'Jean-Paul Sartre')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.notes, 'Nobel Prize status: declined.')
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )

    def test_pasternak_restricted_still_qualifies(self):
        results = _lookup('Doctor Zhivago', 'Boris Pasternak')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.notes, 'Nobel Prize status: restricted.')
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )


class CacheTests(NobelTestCase):
    def test_first_lookup_fetches_once(self):
        with patch.object(
            nobel, '_request_json', return_value=(200, FIXTURE_BODY)
        ) as mocked:
            nobel.lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        self.assertEqual(mocked.call_count, 1)

    def test_subsequent_lookup_reuses_cache(self):
        with patch.object(
            nobel, '_request_json', return_value=(200, FIXTURE_BODY)
        ) as mocked:
            nobel.lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
            nobel.lookup('Never Let Me Go', 'Kazuo Ishiguro')
        self.assertEqual(mocked.call_count, 1)

    def test_cited_work_lookup_does_not_add_requests(self):
        with patch.object(
            nobel, '_request_json', return_value=(200, FIXTURE_BODY)
        ) as mocked:
            nobel.lookup('The Old Man and the Sea', 'Ernest Hemingway')
            nobel.lookup('Growth of the Soil', 'Knut Hamsun')
            nobel.lookup('Hunger', 'Knut Hamsun')
        self.assertEqual(mocked.call_count, 1)

    def test_http_failure_is_not_cached(self):
        with patch.object(
            nobel,
            '_request_json',
            side_effect=nobel.NobelSourceError('HTTP 500'),
        ):
            with self.assertRaises(nobel.NobelSourceError):
                nobel.lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        with patch.object(
            nobel, '_request_json', return_value=(200, FIXTURE_BODY)
        ) as mocked:
            results = nobel.lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        self.assertEqual(len(results), 1)
        self.assertEqual(mocked.call_count, 1)

    def test_json_decode_failure_is_not_cached(self):
        with patch.object(nobel, '_request_json', return_value=(200, '{not-json')):
            with self.assertRaises(nobel.NobelSourceError):
                nobel.lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        results = _lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        self.assertEqual(len(results), 1)

    def test_empty_laureates_is_not_cached(self):
        empty = json.dumps({'laureates': [], 'meta': {'count': 0}})
        with patch.object(nobel, '_request_json', return_value=(200, empty)):
            with self.assertRaises(nobel.NobelSourceError):
                nobel.lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        results = _lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        self.assertEqual(len(results), 1)

    def test_count_mismatch_is_not_cached(self):
        mismatched = json.dumps(
            {'laureates': LAUREATES, 'meta': {'count': len(LAUREATES) + 1}}
        )
        with patch.object(nobel, '_request_json', return_value=(200, mismatched)):
            with self.assertRaises(nobel.NobelSourceError):
                nobel.lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        results = _lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        self.assertEqual(len(results), 1)

    def test_malformed_laureate_is_not_cached(self):
        bad = json.dumps(
            {
                'laureates': [{'id': '1', 'knownName': _en('No Prize')}],
                'meta': {'count': 1},
            }
        )
        with patch.object(nobel, '_request_json', return_value=(200, bad)):
            with self.assertRaises(nobel.NobelSourceError):
                nobel.lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        results = _lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        self.assertEqual(len(results), 1)

    def test_non_200_is_not_cached(self):
        with patch.object(nobel, '_request_json', return_value=(500, '{"x":1}')):
            with self.assertRaises(nobel.NobelSourceError):
                nobel.lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        results = _lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        self.assertEqual(len(results), 1)


class UrlSafetyTests(NobelTestCase):
    def test_canonical_facts_link_is_preferred_over_api_url(self):
        url = nobel._select_source_url(
            [
                {
                    'rel': 'nobelPrize',
                    'href': 'https://api.nobelprize.org/2/nobelPrize/lit/1954',
                    'class': ['laureate facts'],
                },
                {
                    'rel': 'external',
                    'href': (
                        'https://www.nobelprize.org/prizes/literature/'
                        '1954/hemingway/facts/'
                    ),
                    'class': ['laureate facts'],
                },
            ],
            [],
            '625',
        )
        self.assertEqual(
            url,
            'https://www.nobelprize.org/prizes/literature/1954/hemingway/facts/',
        )

    def test_api_url_is_not_used_as_source_url(self):
        url = nobel._select_source_url(
            [
                {
                    'rel': 'external',
                    'href': 'https://api.nobelprize.org/2/laureate/625',
                    'class': ['laureate facts'],
                }
            ],
            [],
            '625',
        )
        self.assertEqual(url, 'https://www.nobelprize.org/laureate/625')

    def test_unexpected_external_domain_is_rejected(self):
        url = nobel._select_source_url(
            [
                {
                    'rel': 'external',
                    'href': 'https://en.wikipedia.org/wiki/Ernest_Hemingway',
                    'class': ['laureate facts'],
                }
            ],
            [],
            '625',
        )
        self.assertEqual(url, 'https://www.nobelprize.org/laureate/625')
        self.assertFalse(
            nobel._is_official_nobel_html_url(
                'https://en.wikipedia.org/wiki/Ernest_Hemingway'
            )
        )

    def test_laureate_fallback_when_facts_link_missing(self):
        url = nobel._select_source_url([], [], '625')
        self.assertEqual(url, 'https://www.nobelprize.org/laureate/625')

    def test_lookup_uses_fallback_when_facts_link_absent(self):
        record = _laureate('625', 'Ernest Hemingway', 1954, 'hemingway')
        record['nobelPrizes'][0]['links'] = [_api_prize_link(1954)]
        record['links'] = []
        payload = json.dumps(
            {'laureates': [record], 'meta': {'count': 1}}
        )
        with patch.object(nobel, '_request_json', return_value=(200, payload)):
            results = nobel.lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        self.assertEqual(
            results[0].source_url,
            'https://www.nobelprize.org/laureate/625',
        )


if __name__ == '__main__':
    unittest.main()
