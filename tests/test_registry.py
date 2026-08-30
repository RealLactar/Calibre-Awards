"""Offline coverage for the award-policy registry.

Pulitzer Fiction, Newbery Honor, Booker Shortlisted, Deutscher
Buchpreis Shortlisted, Prix Goncourt Finalist, and Miles Franklin
Finalist are the registered policies.
"""

from __future__ import annotations

import unittest

from awards.model import AwardResult
from awards.registry import (
    AWARD_POLICIES,
    BOOKER_POLICY,
    GERMAN_BOOK_PRIZE_POLICY,
    MILES_FRANKLIN_POLICY,
    NEWBERY_POLICY,
    PRIX_GONCOURT_POLICY,
    PULITZER_FICTION_POLICY,
    find_award_policy,
)


def _result(**overrides) -> AwardResult:
    values = {
        'work_title': 'Beloved',
        'work_author': 'Toni Morrison',
        'award_name': 'Pulitzer Prize',
        'award_year': 1988,
        'category': 'Fiction',
        'status': 'Winner',
        'rank': None,
        'source_name': 'Pulitzer Prizes',
        'source_url': 'https://www.pulitzer.org/prize-winners-by-category/219',
    }
    values.update(overrides)
    return AwardResult(**values)


def _newbery_result(**overrides) -> AwardResult:
    values = {
        'work_title': 'The Tombs of Atuan',
        'work_author': 'Ursula K. LeGuin',
        'award_name': 'Newbery Medal',
        'award_year': 1972,
        'category': "Children's Literature",
        'status': 'Honor',
        'rank': None,
        'source_name': 'John Newbery Medal',
        'source_url': 'https://www.ala.org/winner/tombs-atuan',
    }
    values.update(overrides)
    return AwardResult(**values)


def _german_result(**overrides) -> AwardResult:
    values = {
        'work_title': 'Es geht uns gut',
        'work_author': 'Arno Geiger',
        'award_name': 'Deutscher Buchpreis',
        'award_year': 2005,
        'category': 'Fiction',
        'status': 'Winner',
        'rank': None,
        'source_name': 'Deutscher Buchpreis',
        'source_url': 'https://www.deutscher-buchpreis.de/archiv/jahr/2005/',
    }
    values.update(overrides)
    return AwardResult(**values)


def _booker_result(**overrides) -> AwardResult:
    values = {
        'work_title': 'Midnight’s Children',
        'work_author': 'Salman Rushdie',
        'award_name': 'Booker Prize',
        'award_year': 1981,
        'category': 'Fiction',
        'status': 'Winner',
        'rank': None,
        'source_name': 'The Booker Prize',
        'source_url': 'https://thebookerprizes.com/the-booker-library/books/midnights-children',
    }
    values.update(overrides)
    return AwardResult(**values)


class AwardPolicyRegistryTests(unittest.TestCase):
    def test_registered_policies_are_pulitzer_newbery_booker_german_goncourt_miles(self):
        self.assertEqual(
            AWARD_POLICIES,
            (
                PULITZER_FICTION_POLICY,
                NEWBERY_POLICY,
                BOOKER_POLICY,
                GERMAN_BOOK_PRIZE_POLICY,
                PRIX_GONCOURT_POLICY,
                MILES_FRANKLIN_POLICY,
            ),
        )

    def test_pulitzer_fiction_result_finds_the_active_policy(self):
        winner = _result()
        finalist = _result(status='Finalist')
        self.assertIs(find_award_policy(winner), PULITZER_FICTION_POLICY)
        self.assertIs(find_award_policy(finalist), PULITZER_FICTION_POLICY)

    def test_newbery_result_finds_the_honor_policy(self):
        honor = _newbery_result()
        winner = _newbery_result(status='Winner', award_year=1963)
        self.assertIs(find_award_policy(honor), NEWBERY_POLICY)
        self.assertIs(find_award_policy(winner), NEWBERY_POLICY)

    def test_newbery_policy_does_not_match_other_award_or_category(self):
        self.assertIsNone(
            find_award_policy(
                _newbery_result(award_name='Caldecott Medal')
            )
        )
        self.assertIsNone(
            find_award_policy(_newbery_result(category='Fiction'))
        )
        self.assertIsNone(
            find_award_policy(
                _result(
                    award_name='Hugo Award',
                    category='Best Novel',
                    status='Honor',
                )
            )
        )

    def test_booker_result_finds_the_shortlisted_policy(self):
        winner = _booker_result()
        shortlisted = _booker_result(
            work_title='Empire of the Sun',
            work_author='J. G. Ballard',
            award_year=1984,
            status='Shortlisted',
            source_url=(
                'https://thebookerprizes.com/the-booker-library/books/'
                'empire-of-the-sun'
            ),
        )
        self.assertIs(find_award_policy(winner), BOOKER_POLICY)
        self.assertIs(find_award_policy(shortlisted), BOOKER_POLICY)

    def test_booker_policy_does_not_match_other_award_or_category(self):
        self.assertIsNone(
            find_award_policy(_booker_result(award_name='International Booker Prize'))
        )
        self.assertIsNone(find_award_policy(_booker_result(category='Poetry')))
        self.assertIsNone(find_award_policy(_booker_result(category=None)))

    def test_german_book_prize_result_finds_the_shortlisted_policy(self):
        winner = _german_result()
        shortlisted = _german_result(
            work_title='Die Vermessung der Welt',
            work_author='Daniel Kehlmann',
            status='Shortlisted',
        )
        self.assertIs(find_award_policy(winner), GERMAN_BOOK_PRIZE_POLICY)
        self.assertIs(find_award_policy(shortlisted), GERMAN_BOOK_PRIZE_POLICY)

    def test_german_and_booker_policies_do_not_cross_match(self):
        self.assertIs(find_award_policy(_booker_result()), BOOKER_POLICY)
        self.assertIs(find_award_policy(_german_result()), GERMAN_BOOK_PRIZE_POLICY)
        self.assertIsNot(
            find_award_policy(_german_result()),
            BOOKER_POLICY,
        )
        self.assertIsNot(
            find_award_policy(_booker_result()),
            GERMAN_BOOK_PRIZE_POLICY,
        )
        self.assertIsNone(find_award_policy(_german_result(category='Poetry')))
        self.assertIsNone(find_award_policy(_german_result(category=None)))

    def test_prix_goncourt_result_finds_the_finalist_policy(self):
        winner = _result(
            work_title='La Maison vide',
            work_author='Laurent Mauvignier',
            award_name='Prix Goncourt',
            award_year=2025,
            category='Fiction',
            status='Winner',
            source_name='Prix Goncourt',
            source_url='https://www.academiegoncourt.com/tous-les-laureats-prix-goncourt',
        )
        finalist = _result(
            work_title='Triste tigre',
            work_author='Neige SINNO',
            award_name='Prix Goncourt',
            award_year=2023,
            category='Fiction',
            status='Finalist',
            source_name='Prix Goncourt',
            source_url='https://www.academiegoncourt.com/prix-goncourt-et-selection-annee',
        )
        self.assertIs(find_award_policy(winner), PRIX_GONCOURT_POLICY)
        self.assertIs(find_award_policy(finalist), PRIX_GONCOURT_POLICY)

    def test_prix_goncourt_policy_does_not_match_other_award_or_category(self):
        self.assertIsNone(
            find_award_policy(
                _result(
                    award_name='Prix Goncourt',
                    category='Poetry',
                    status='Finalist',
                )
            )
        )
        self.assertIsNone(
            find_award_policy(
                _result(
                    award_name='Prix Femina',
                    category='Fiction',
                    status='Finalist',
                )
            )
        )
        self.assertNotIn('1ère', PRIX_GONCOURT_POLICY.qualifying_statuses)
        self.assertNotIn('2ème', PRIX_GONCOURT_POLICY.qualifying_statuses)
        self.assertEqual(
            PRIX_GONCOURT_POLICY.qualifying_statuses,
            frozenset({'finalist'}),
        )
        notes = (PRIX_GONCOURT_POLICY.notes or '').casefold()
        self.assertIn('3ème', notes)
        self.assertIn('does not imply', notes)
        self.assertNotIn('top 4', notes)
        self.assertNotIn('rank 4', notes)

    def test_miles_franklin_result_finds_the_finalist_policy(self):
        winner = _result(
            work_title='Fierceland',
            work_author='Omar Musa',
            award_name='Miles Franklin Literary Award',
            award_year=2026,
            category='Fiction',
            status='Winner',
            source_name='Miles Franklin Literary Award',
            source_url=(
                'https://www.perpetual.com.au/wealth-management/'
                'milesfranklin/judges-and-history-of-recipients/'
            ),
        )
        finalist = _result(
            work_title='Discipline',
            work_author='Randa Abdel-Fattah',
            award_name='Miles Franklin Literary Award',
            award_year=2026,
            category='Fiction',
            status='Finalist',
            source_name='Miles Franklin Literary Award',
            source_url=(
                'https://www.perpetual.com.au/wealth-management/'
                'milesfranklin/judges-and-history-of-recipients/'
            ),
        )
        self.assertIs(find_award_policy(winner), MILES_FRANKLIN_POLICY)
        self.assertIs(find_award_policy(finalist), MILES_FRANKLIN_POLICY)

    def test_miles_franklin_policy_does_not_match_other_award_or_category(self):
        self.assertIsNone(
            find_award_policy(
                _result(
                    award_name='Miles Franklin Literary Award',
                    category='Poetry',
                    status='Finalist',
                )
            )
        )
        self.assertIsNone(
            find_award_policy(
                _result(
                    award_name='Stella Prize',
                    category='Fiction',
                    status='Finalist',
                )
            )
        )
        self.assertEqual(
            MILES_FRANKLIN_POLICY.qualifying_statuses,
            frozenset({'finalist'}),
        )
        notes = (MILES_FRANKLIN_POLICY.notes or '').casefold()
        self.assertIn('shortlist', notes)
        self.assertIn('does not imply', notes)
        self.assertNotIn('top 6', notes)

    def test_german_book_prize_policy_does_not_include_longlisted(self):
        self.assertNotIn('longlisted', GERMAN_BOOK_PRIZE_POLICY.qualifying_statuses)
        self.assertEqual(
            GERMAN_BOOK_PRIZE_POLICY.qualifying_statuses,
            frozenset({'shortlisted'}),
        )

    def test_longlisted_booker_name_without_fiction_category_has_no_policy(self):
        result = _result(
            work_title='Other',
            work_author='Author',
            award_name='Booker Prize',
            award_year=2026,
            category=None,
            status='Longlisted',
            source_name='The Booker Prize',
            source_url=None,
        )
        self.assertIsNone(find_award_policy(result))
        self.assertNotIn('longlisted', BOOKER_POLICY.qualifying_statuses)


if __name__ == '__main__':
    unittest.main()
