"""Offline coverage for the static award source registry."""

from __future__ import annotations

import unittest

from awards.source_registry import AWARD_SOURCES, AwardSource
from awards.sources import booker, newbery


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
                'NobelPrize.org',
                'The Booker Prize',
                'John Newbery Medal',
            ),
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


if __name__ == '__main__':
    unittest.main()
