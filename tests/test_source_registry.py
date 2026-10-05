"""Offline coverage for the static award source registry."""

from __future__ import annotations

import unittest

from awards.source_registry import AWARD_SOURCES, AwardSource
from awards.sources import (
    booker,
    bram_stoker,
    edgar,
    international_booker,
    german_book_prize,
    wolfson_history,
    ipaf,
    miles_franklin,
    national_book_critics_circle,
    newbery,
    pen_faulkner,
    pen_hemingway,
    prix_goncourt,
    romantic_novel_awards,
    womens_prize_fiction,
)


class AwardSourceRegistryTests(unittest.TestCase):
    def test_supported_source_keys_in_order(self):
        self.assertEqual(
            tuple(source.key for source in AWARD_SOURCES),
            (
                'pulitzer',
                'nebula',
                'hugo',
                'locus',
                'world_fantasy',
                'balrog',
                'bram_stoker',
                'edgar',
                'romantic_novel_awards',
                'nobel',
                'booker',
                'international_booker',
                'wolfson_history',
                'german_book_prize',
                'prix_goncourt',
                'miles_franklin',
                'womens_prize_fiction',
                'national_book_critics_circle',
                'pen_faulkner',
                'pen_hemingway',
                'ipaf',
                'bad_sex_fiction',
                'diagram',
                'newbery',
                'dublin',
                'akutagawa',
                'naoki',
            ),
        )

    def test_display_names(self):
        self.assertEqual(
            tuple(source.display_name for source in AWARD_SOURCES),
            (
                'Pulitzer Prizes',
                'Nebula Awards',
                'Hugo Awards',
                'Locus Awards',
                'World Fantasy Awards',
                'Balrog Award',
                'Bram Stoker Awards',
                'Edgar Awards',
                'Romantic Novel of the Year Awards',
                'Nobel Award',
                'The Booker Prize',
                'International Booker Prize',
                'Wolfson History Prize',
                'Deutscher Buchpreis',
                'Prix Goncourt',
                'Miles Franklin Literary Award',
                "Women's Prize for Fiction",
                'National Book Critics Circle Awards',
                'PEN/Faulkner Award for Fiction',
                'PEN/Hemingway Award for Debut Novel',
                'International Prize for Arabic Fiction',
                'Bad Sex in Fiction Award',
                'Diagram Prize for Oddest Title of the Year',
                'John Newbery Medal',
                'Dublin Literary Award',
                'Akutagawa Prize',
                'Naoki Prize',
            ),
        )

    def test_executable_registry_count_excludes_national_book_awards(self):
        keys = [source.key for source in AWARD_SOURCES]
        self.assertEqual(len(AWARD_SOURCES), 27)
        self.assertNotIn('national_book_awards', keys)
        self.assertNotIn(
            'National Book Awards',
            [source.display_name for source in AWARD_SOURCES],
        )

    def test_keys_are_unique(self):
        keys = [source.key for source in AWARD_SOURCES]
        self.assertEqual(len(keys), len(set(keys)))

    def test_display_names_are_non_empty(self):
        for source in AWARD_SOURCES:
            with self.subTest(key=source.key):
                self.assertTrue(source.display_name.strip())

    def test_each_lookup_is_callable(self):
        for source in AWARD_SOURCES:
            with self.subTest(key=source.key):
                self.assertTrue(callable(source.lookup))

    def test_registry_entries_are_award_sources(self):
        self.assertTrue(AWARD_SOURCES)
        for source in AWARD_SOURCES:
            self.assertIsInstance(source, AwardSource)

    def test_newbery_uses_the_public_lookup_function(self):
        newbery_source = [
            source for source in AWARD_SOURCES if source.key == 'newbery'
        ][0]
        self.assertIs(newbery_source.lookup, newbery.lookup)

    def test_booker_uses_the_public_lookup_function(self):
        booker_source = [
            source for source in AWARD_SOURCES if source.key == 'booker'
        ][0]
        self.assertIs(booker_source.lookup, booker.lookup)

    def test_international_booker_uses_the_public_lookup_function(self):
        source = [
            item for item in AWARD_SOURCES if item.key == 'international_booker'
        ][0]
        self.assertIs(source.lookup, international_booker.lookup)

    def test_wolfson_history_uses_the_public_lookup_function(self):
        source = [
            item for item in AWARD_SOURCES if item.key == 'wolfson_history'
        ][0]
        self.assertIs(source.lookup, wolfson_history.lookup)
        self.assertEqual(source.display_name, 'Wolfson History Prize')

    def test_german_book_prize_uses_the_public_lookup_function(self):
        german_source = [
            source for source in AWARD_SOURCES if source.key == 'german_book_prize'
        ][0]
        self.assertIs(german_source.lookup, german_book_prize.lookup)

    def test_prix_goncourt_uses_the_public_lookup_function(self):
        goncourt_source = [
            source for source in AWARD_SOURCES if source.key == 'prix_goncourt'
        ][0]
        self.assertIs(goncourt_source.lookup, prix_goncourt.lookup)

    def test_miles_franklin_uses_the_public_lookup_function(self):
        miles_source = [
            source for source in AWARD_SOURCES if source.key == 'miles_franklin'
        ][0]
        self.assertIs(miles_source.lookup, miles_franklin.lookup)

    def test_womens_prize_fiction_uses_the_public_lookup_function(self):
        womens_source = [
            source
            for source in AWARD_SOURCES
            if source.key == 'womens_prize_fiction'
        ][0]
        self.assertIs(womens_source.lookup, womens_prize_fiction.lookup)

    def test_nbcc_uses_the_public_lookup_function(self):
        nbcc_source = [
            source
            for source in AWARD_SOURCES
            if source.key == 'national_book_critics_circle'
        ][0]
        self.assertIs(nbcc_source.lookup, national_book_critics_circle.lookup)

    def test_pen_faulkner_uses_the_public_lookup_function(self):
        source = [
            item for item in AWARD_SOURCES if item.key == 'pen_faulkner'
        ][0]
        self.assertIs(source.lookup, pen_faulkner.lookup)

    def test_pen_hemingway_uses_the_public_lookup_function(self):
        source = [
            item for item in AWARD_SOURCES if item.key == 'pen_hemingway'
        ][0]
        self.assertIs(source.lookup, pen_hemingway.lookup)

    def test_ipaf_uses_the_public_lookup_function(self):
        source = [item for item in AWARD_SOURCES if item.key == 'ipaf'][0]
        self.assertIs(source.lookup, ipaf.lookup)

    def test_bram_stoker_uses_the_public_lookup_function(self):
        source = [
            item for item in AWARD_SOURCES if item.key == 'bram_stoker'
        ][0]
        self.assertIs(source.lookup, bram_stoker.lookup)

    def test_edgar_uses_the_public_lookup_function(self):
        source = [item for item in AWARD_SOURCES if item.key == 'edgar'][0]
        self.assertIs(source.lookup, edgar.lookup)

    def test_romantic_novel_awards_uses_the_public_lookup_function(self):
        source = [
            item for item in AWARD_SOURCES if item.key == 'romantic_novel_awards'
        ][0]
        self.assertIs(source.lookup, romantic_novel_awards.lookup)


if __name__ == '__main__':
    unittest.main()
