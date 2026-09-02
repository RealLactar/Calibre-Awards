"""Offline coverage for Calibre-free disabled-source helpers."""

from __future__ import annotations

import unittest

from awards.source_settings import (
    compute_enabled_source_keys,
    normalize_disabled_source_keys,
)

_CURRENT = (
    'pulitzer',
    'nebula',
    'hugo',
    'locus',
    'world_fantasy',
    'bram_stoker',
    'edgar',
    'nobel',
    'booker',
    'german_book_prize',
    'prix_goncourt',
    'miles_franklin',
    'womens_prize_fiction',
    'national_book_critics_circle',
    'pen_faulkner',
    'pen_hemingway',
    'ipaf',
    'newbery',
)


class NormalizeDisabledSourceKeysTests(unittest.TestCase):
    def test_none_and_empty_collections(self):
        self.assertEqual(normalize_disabled_source_keys(None), ())
        self.assertEqual(normalize_disabled_source_keys([]), ())
        self.assertEqual(normalize_disabled_source_keys(()), ())
        self.assertEqual(normalize_disabled_source_keys(''), ())
        self.assertEqual(normalize_disabled_source_keys('   '), ())

    def test_single_raw_string_is_recovered_as_one_key(self):
        self.assertEqual(normalize_disabled_source_keys('pulitzer'), ('pulitzer',))
        self.assertEqual(
            normalize_disabled_source_keys('  nobel  '),
            ('nobel',),
        )

    def test_list_and_tuple_trim_and_preserve_order(self):
        self.assertEqual(
            normalize_disabled_source_keys(['pulitzer']),
            ('pulitzer',),
        )
        self.assertEqual(
            normalize_disabled_source_keys(['pulitzer', 'nobel']),
            ('pulitzer', 'nobel'),
        )
        self.assertEqual(
            normalize_disabled_source_keys((' pulitzer ', 'nobel')),
            ('pulitzer', 'nobel'),
        )

    def test_duplicates_keep_first_occurrence(self):
        self.assertEqual(
            normalize_disabled_source_keys(['pulitzer', 'pulitzer']),
            ('pulitzer',),
        )
        self.assertEqual(
            normalize_disabled_source_keys(['nobel', 'pulitzer', 'nobel']),
            ('nobel', 'pulitzer'),
        )

    def test_invalid_entries_are_ignored(self):
        self.assertEqual(
            normalize_disabled_source_keys(
                ['pulitzer', None, 42, '', '   ', b'hugo']
            ),
            ('pulitzer',),
        )

    def test_mappings_and_unusable_scalars_are_ignored(self):
        self.assertEqual(normalize_disabled_source_keys({'pulitzer': True}), ())
        self.assertEqual(normalize_disabled_source_keys(42), ())

    def test_stale_keys_are_preserved_by_normalization(self):
        self.assertEqual(
            normalize_disabled_source_keys(['pulitzer', 'removed_old_source']),
            ('pulitzer', 'removed_old_source'),
        )


class ComputeEnabledSourceKeysTests(unittest.TestCase):
    def test_none_disabled_keeps_registry_order(self):
        self.assertEqual(
            compute_enabled_source_keys(_CURRENT, ()),
            _CURRENT,
        )
        self.assertEqual(
            compute_enabled_source_keys(_CURRENT, None),
            _CURRENT,
        )

    def test_one_disabled(self):
        self.assertEqual(
            compute_enabled_source_keys(_CURRENT, ('pulitzer',)),
            ('nebula', 'hugo', 'locus', 'world_fantasy', 'bram_stoker', 'edgar', 'nobel', 'booker', 'german_book_prize', 'prix_goncourt', 'miles_franklin', 'womens_prize_fiction', 'national_book_critics_circle', 'pen_faulkner', 'pen_hemingway', 'ipaf', 'newbery'),
        )

    def test_several_disabled(self):
        self.assertEqual(
            compute_enabled_source_keys(('pulitzer', 'nebula', 'hugo'), ('pulitzer', 'hugo')),
            ('nebula',),
        )

    def test_all_disabled(self):
        self.assertEqual(compute_enabled_source_keys(_CURRENT, _CURRENT), ())

    def test_unknown_disabled_key_is_harmless(self):
        self.assertEqual(
            compute_enabled_source_keys(
                ('pulitzer', 'nebula', 'hugo'),
                ('old_removed_source',),
            ),
            ('pulitzer', 'nebula', 'hugo'),
        )

    def test_stale_normalized_key_does_not_remove_current_sources(self):
        disabled = normalize_disabled_source_keys(
            ['pulitzer', 'removed_old_source']
        )
        self.assertEqual(disabled, ('pulitzer', 'removed_old_source'))
        self.assertEqual(
            compute_enabled_source_keys(_CURRENT, disabled),
            ('nebula', 'hugo', 'locus', 'world_fantasy', 'bram_stoker', 'edgar', 'nobel', 'booker', 'german_book_prize', 'prix_goncourt', 'miles_franklin', 'womens_prize_fiction', 'national_book_critics_circle', 'pen_faulkner', 'pen_hemingway', 'ipaf', 'newbery'),
        )

    def test_future_source_defaults_enabled(self):
        current = _CURRENT + ('future_source',)
        enabled = compute_enabled_source_keys(current, ('pulitzer',))
        self.assertIn('future_source', enabled)
        self.assertEqual(
            enabled,
            (
                'nebula',
                'hugo',
                'locus',
                'world_fantasy',
                'bram_stoker',
                'edgar',
                'nobel',
                'booker',
                'german_book_prize',
                'prix_goncourt',
                'miles_franklin',
                'womens_prize_fiction',
                'national_book_critics_circle',
                'pen_faulkner',
                'pen_hemingway',
                'ipaf',
                'newbery',
                'future_source',
            ),
        )

    def test_registry_order_preserved_and_duplicates_collapsed(self):
        self.assertEqual(
            compute_enabled_source_keys(
                ('pulitzer', 'nebula', 'pulitzer', 'hugo'),
                ('nebula',),
            ),
            ('pulitzer', 'hugo'),
        )


class SourceInfosPreferenceCompositionTests(unittest.TestCase):
    def _all_keys(self):
        from awards.source_info import SOURCE_INFOS

        return tuple(info.key for info in SOURCE_INFOS)

    def test_default_empty_disabled_enables_every_current_source(self):
        all_keys = self._all_keys()
        self.assertEqual(
            compute_enabled_source_keys(all_keys, []),
            all_keys,
        )
        self.assertEqual(all_keys[0], 'pulitzer')
        self.assertEqual(all_keys[-1], 'newbery')
        self.assertIn('newbery', all_keys)
        self.assertEqual(len(all_keys), 18)
        self.assertIn('national_book_critics_circle', all_keys)
        self.assertIn('pen_faulkner', all_keys)
        self.assertIn('pen_hemingway', all_keys)
        self.assertIn('ipaf', all_keys)
        self.assertIn('bram_stoker', all_keys)
        self.assertIn('edgar', all_keys)
        self.assertNotIn('national_book_awards', all_keys)
        self.assertNotIn(
            'national_book_awards',
            compute_enabled_source_keys(all_keys, []),
        )

    def test_german_book_prize_defaults_enabled_for_preexisting_disabled_list(self):
        all_keys = self._all_keys()
        enabled = compute_enabled_source_keys(all_keys, ['pulitzer'])
        self.assertIn('german_book_prize', enabled)
        self.assertNotIn('pulitzer', enabled)

    def test_newbery_defaults_enabled_for_preexisting_disabled_list(self):
        all_keys = self._all_keys()
        enabled = compute_enabled_source_keys(all_keys, ['pulitzer'])
        self.assertIn('newbery', enabled)
        self.assertNotIn('pulitzer', enabled)

    def test_booker_defaults_enabled_for_preexisting_disabled_list(self):
        all_keys = self._all_keys()
        enabled = compute_enabled_source_keys(all_keys, ['pulitzer'])
        self.assertIn('booker', enabled)
        self.assertIn('german_book_prize', enabled)
        self.assertNotIn('pulitzer', enabled)
        self.assertEqual(
            all_keys.index('bram_stoker'),
            all_keys.index('world_fantasy') + 1,
        )
        self.assertEqual(
            all_keys.index('edgar'),
            all_keys.index('bram_stoker') + 1,
        )
        self.assertEqual(
            all_keys.index('nobel'),
            all_keys.index('edgar') + 1,
        )
        self.assertEqual(all_keys.index('booker'), all_keys.index('nobel') + 1)
        self.assertEqual(
            all_keys.index('german_book_prize'),
            all_keys.index('booker') + 1,
        )
        self.assertEqual(
            all_keys.index('prix_goncourt'),
            all_keys.index('german_book_prize') + 1,
        )
        self.assertEqual(
            all_keys.index('miles_franklin'),
            all_keys.index('prix_goncourt') + 1,
        )
        self.assertEqual(
            all_keys.index('womens_prize_fiction'),
            all_keys.index('miles_franklin') + 1,
        )
        self.assertEqual(
            all_keys.index('national_book_critics_circle'),
            all_keys.index('womens_prize_fiction') + 1,
        )
        self.assertEqual(
            all_keys.index('pen_faulkner'),
            all_keys.index('national_book_critics_circle') + 1,
        )
        self.assertEqual(
            all_keys.index('pen_hemingway'),
            all_keys.index('pen_faulkner') + 1,
        )
        self.assertEqual(
            all_keys.index('ipaf'),
            all_keys.index('pen_hemingway') + 1,
        )
        self.assertEqual(
            all_keys.index('newbery'),
            all_keys.index('ipaf') + 1,
        )

    def test_prix_goncourt_defaults_enabled_for_preexisting_disabled_list(self):
        all_keys = self._all_keys()
        enabled = compute_enabled_source_keys(all_keys, ['pulitzer'])
        self.assertIn('prix_goncourt', enabled)
        self.assertNotIn('pulitzer', enabled)

    def test_miles_franklin_defaults_enabled_for_preexisting_disabled_list(self):
        all_keys = self._all_keys()
        enabled = compute_enabled_source_keys(all_keys, ['pulitzer'])
        self.assertIn('miles_franklin', enabled)
        self.assertNotIn('pulitzer', enabled)

    def test_womens_prize_fiction_defaults_enabled_for_preexisting_disabled_list(self):
        all_keys = self._all_keys()
        enabled = compute_enabled_source_keys(all_keys, ['pulitzer'])
        self.assertIn('womens_prize_fiction', enabled)
        self.assertNotIn('pulitzer', enabled)

    def test_nbcc_defaults_enabled_for_preexisting_disabled_list(self):
        all_keys = self._all_keys()
        enabled = compute_enabled_source_keys(all_keys, ['pulitzer'])
        self.assertIn('national_book_critics_circle', enabled)
        self.assertNotIn('pulitzer', enabled)

    def test_pen_faulkner_defaults_enabled_for_preexisting_disabled_list(self):
        all_keys = self._all_keys()
        enabled = compute_enabled_source_keys(all_keys, ['pulitzer'])
        self.assertIn('pen_faulkner', enabled)
        self.assertNotIn('pulitzer', enabled)

    def test_pen_hemingway_defaults_enabled_for_preexisting_disabled_list(self):
        all_keys = self._all_keys()
        enabled = compute_enabled_source_keys(all_keys, ['pulitzer'])
        self.assertIn('pen_hemingway', enabled)
        self.assertNotIn('pulitzer', enabled)

    def test_bram_stoker_defaults_enabled_for_preexisting_disabled_list(self):
        all_keys = self._all_keys()
        enabled = compute_enabled_source_keys(all_keys, ['pulitzer'])
        self.assertIn('bram_stoker', enabled)
        self.assertNotIn('pulitzer', enabled)

    def test_edgar_defaults_enabled_for_preexisting_disabled_list(self):
        all_keys = self._all_keys()
        enabled = compute_enabled_source_keys(all_keys, ['pulitzer'])
        self.assertIn('edgar', enabled)
        self.assertNotIn('pulitzer', enabled)

    def test_ipaf_defaults_enabled_for_preexisting_disabled_list(self):
        all_keys = self._all_keys()
        enabled = compute_enabled_source_keys(all_keys, ['pulitzer'])
        self.assertIn('ipaf', enabled)
        self.assertNotIn('pulitzer', enabled)

    def test_pulitzer_disabled_excludes_only_pulitzer(self):
        all_keys = self._all_keys()
        enabled = compute_enabled_source_keys(all_keys, ['pulitzer'])
        self.assertNotIn('pulitzer', enabled)
        self.assertEqual(enabled, all_keys[1:])

    def test_only_nobel_enabled(self):
        all_keys = self._all_keys()
        disabled = tuple(key for key in all_keys if key != 'nobel')
        self.assertEqual(
            compute_enabled_source_keys(all_keys, disabled),
            ('nobel',),
        )

    def test_all_disabled_is_empty_tuple(self):
        all_keys = self._all_keys()
        self.assertEqual(compute_enabled_source_keys(all_keys, all_keys), ())

    def test_malformed_preference_does_not_crash(self):
        all_keys = self._all_keys()
        self.assertEqual(
            compute_enabled_source_keys(all_keys, {'pulitzer': True}),
            all_keys,
        )
        self.assertEqual(
            compute_enabled_source_keys(all_keys, 'pulitzer'),
            all_keys[1:],
        )

    def test_save_from_current_sources_drops_stale_keys(self):
        all_keys = self._all_keys()
        checked = {key: key != 'hugo' for key in all_keys}
        saved = [key for key in all_keys if not checked[key]]
        self.assertEqual(saved, ['hugo'])
        self.assertNotIn('removed_old_source', saved)


if __name__ == '__main__':
    unittest.main()
