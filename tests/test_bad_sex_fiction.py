import unittest
from unittest.mock import patch
from awards.sources import bad_sex_fiction as source
from awards.cache_control import refresh_award_source_cache, source_cache_refresh_confirm_body


class BadSexFictionTests(unittest.TestCase):
    def tearDown(self):
        source._reset_runtime_state()

    def test_historical_coverage_and_joint_winners(self):
        records = source._get_records()
        self.assertEqual(len(records), 28)
        self.assertEqual({r.award_year for r in records}, set(range(1993, 2020)))
        self.assertEqual({r.work_title for r in records if r.award_year == 2019},
                         {'Pax', 'The Office of Gardens and Ponds'})
        self.assertTrue(all(r.status == 'Winner' and r.rank is None
                            and r.identity_kind == 'work' and r.source_url for r in records))

    def test_offline_lookup_and_refresh(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('network')):
            first = source.lookup('Katerina', 'James Frey')
            self.assertEqual(first[0].award_year, 2018)
            self.assertTrue(refresh_award_source_cache(source.SOURCE_KEY))
            self.assertIsNone(source._records)
            self.assertEqual(first, source.lookup('Katerina', 'James Frey'))
        self.assertIn('does not download', source_cache_refresh_confirm_body(source.SOURCE_KEY, source.AWARD_NAME))

    def test_corrected_early_years_have_secondary_attribution(self):
        for title, author, year in [('The Stonebreakers', 'Philip Hook', 1994),
                                    ('Gridiron', 'Philip Kerr', 1995)]:
            record = source.lookup(title, author)[0]
            self.assertEqual(record.award_year, year)
            self.assertIn('Wikipedia', record.source_name)

    def test_conservative_identity_and_initial_spacing(self):
        self.assertEqual(len(source.lookup(' STARCROSSED ', 'A.A. Gill')), 1)
        self.assertEqual(source.lookup('Katerina', 'John Harvey'), [])
        self.assertEqual(source.lookup('Katerina: Another Book', 'James Frey'), [])

    def test_shortlists_and_author_lifetime_award_excluded(self):
        self.assertEqual(source.lookup('City of Girls', 'Elizabeth Gilbert'), [])
        self.assertEqual(source.lookup('Rabbit, Run', 'John Updike'), [])

    def test_blank_identity_rejected(self):
        for title, author in [('', 'James Frey'), ('Katerina', ' ')]:
            with self.assertRaises(ValueError):
                source.lookup(title, author)
