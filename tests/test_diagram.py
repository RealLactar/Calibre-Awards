import unittest
from unittest.mock import patch
from awards.sources import diagram
from awards.cache_control import refresh_award_source_cache, source_cache_refresh_confirm_body
from awards.qualifier import qualify_award_result, QualificationDecision


class DiagramPrizeTests(unittest.TestCase):
    def tearDown(self):
        diagram._reset_runtime_state()

    def test_reviewed_coverage_and_exclusions(self):
        records = diagram._get_records()
        self.assertEqual(len(records), 42)
        expected = set(range(1979, 2026)) - {1981, 1982, 1987, 1991, 2017}
        self.assertEqual({r.award_year for r in records}, expected)
        self.assertTrue(all(r.status == 'Winner' and r.rank is None and r.category is None
                            and r.identity_kind == 'work' and r.source_url for r in records))
        self.assertEqual(len({(r.work_title, r.work_author) for r in records}), 42)

    def test_offline_lookup_qualifies_and_refresh_reloads(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('network')):
            record = diagram.lookup('How to Avoid Huge Ships', 'John W. Trimmer')[0]
            self.assertEqual(record.award_year, 1992)
            self.assertEqual(qualify_award_result(record).decision, QualificationDecision.QUALIFIES)
            self.assertTrue(refresh_award_source_cache('diagram'))
            self.assertIsNone(diagram._records)
            self.assertEqual(record, diagram.lookup('How to Avoid Huge Ships', 'John W. Trimmer')[0])
        self.assertIn('does not download', source_cache_refresh_confirm_body('diagram', diagram.AWARD_NAME))

    def test_complete_coauthor_identity_order_and_separator(self):
        self.assertEqual(len(diagram.lookup('The Big Book of Lesbian Horse Stories',
                                          'Monica Nolan & Alisa Surkis')), 1)
        self.assertEqual(len(diagram.lookup('The Big Book of Lesbian Horse Stories',
                                          'Alisa Surkis and Monica Nolan')), 1)
        self.assertEqual(diagram.lookup('The Big Book of Lesbian Horse Stories', 'Monica Nolan'), [])
        self.assertEqual(diagram.lookup('The Big Book of Lesbian Horse Stories',
                                        'Alisa Surkis & Another Writer'), [])

    def test_whole_title_and_author_required(self):
        self.assertEqual(diagram.lookup('Cooking with Poo', 'Unknown'), [])
        self.assertEqual(diagram.lookup('Cooking with Poo: Another Book', 'Saiyuud Diwong'), [])
        self.assertEqual(diagram.lookup('Is Superman Circumcised?', 'McFarland'), [])

    def test_explicit_subtitle_alias_and_initial_spacing(self):
        self.assertEqual(len(diagram.lookup(diagram._TITLE_ALIASES[2004][0],
                                          'Rick Pelicano & Lauren Tjaden')), 1)
        self.assertEqual(len(diagram.lookup('How to Avoid Huge Ships', 'John W.  Trimmer')), 1)
        self.assertEqual(len(diagram.lookup('Highlights in the History of Concrete', 'C.C. Stanley')), 1)

    def test_award_year_is_not_announcement_year(self):
        self.assertEqual(diagram.lookup('Cooking with Poo', 'Saiyuud Diwong')[0].award_year, 2011)
        self.assertEqual(diagram.lookup('Greek Rural Postmen and Their Cancellation Numbers',
                                       'Derek Willan')[0].award_year, 1996)

    def test_latest_winner_and_unicode(self):
        title = "The Pornographic Delicatessen: Midcentury Montréal’s Erotic Art, Media, and Spaces"
        record = diagram.lookup(title, 'Matthew Purvis')[0]
        self.assertEqual(record.award_year, 2025)
        self.assertIn('Wikipedia', record.source_name)
        self.assertEqual(len(diagram.lookup('The Joy of Waterboiling', 'Thomas Götz von Aust')), 1)

    def test_blank_identity_rejected(self):
        for title, author in [('', 'John W. Trimmer'), ('How to Avoid Huge Ships', ' ')]:
            with self.assertRaises(ValueError):
                diagram.lookup(title, author)
