"""Offline coverage for the static award source registry."""

from __future__ import annotations

import unittest

from awards.source_registry import AWARD_SOURCES, AwardSource
from awards.sources import (
    booker,
    german_book_prize,
    miles_franklin,
    national_book_critics_circle,
    newbery,
    prix_goncourt,
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
                'nobel',
                'booker',
                'german_book_prize',
                'prix_goncourt',
                'miles_franklin',
                'womens_prize_fiction',
                'national_book_critics_circle',
                'newbery',
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
                'Nobel Award',
                'The Booker Prize',
                'Deutscher Buchpreis',
                'Prix Goncourt',
                'Miles Franklin Literary Award',
                "Women's Prize for Fiction",
                'National Book Critics Circle Awards',
                'John Newbery Medal',
            ),
        )

    def test_executable_registry_count_excludes_national_book_awards(self):
        keys = [source.key for source in AWARD_SOURCES]
        self.assertEqual(len(AWARD_SOURCES), 13)
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


if __name__ == '__main__':
    unittest.main()
