"""Offline parser coverage for Bram Stoker Awards HTML year pages."""

from __future__ import annotations

import unittest

from awards.sources import bram_stoker as src


def _page(body: str, title: str, year: int | None = None) -> str:
    heading = title
    year_bit = f' {year}' if year is not None else ''
    return (
        '<html><head>'
        f'<title>{title} – The Bram Stoker Awards</title>'
        '</head><body>'
        '<nav>Ignore this Novel by Someone</nav>'
        f'<div class="entry-content">'
        f'<h1>{heading}</h1>'
        f'<p>The Horror Writers Association presents the Bram Stoker Awards'
        f'{year_bit}.</p>'
        f'{body}'
        '</div>'
        '<footer>Lifetime Achievement Award junk</footer>'
        '</body></html>'
    )


def _url(year: int) -> str:
    return src.HISTORICAL_CENSUS_PATHS[year] and (
        src.SITE_ORIGIN + src.HISTORICAL_CENSUS_PATHS[year]
    )


def _parse(year: int, body: str, title: str | None = None):
    html = _page(
        body,
        title or f'{year} Bram Stoker Award Winners & Nominees',
        year,
    )
    return src._parse_year_page(html, year, _url(year))


def _pairs(records):
    return {(r.category, r.status, r.work_title, r.work_author) for r in records}


def _titles(records, category, status=None):
    out = []
    for record in records:
        if record.category != category:
            continue
        if status is not None and record.status != status:
            continue
        out.append(record.work_title)
    return out


class HeadingAndAuthorHelperTests(unittest.TestCase):
    def test_superior_achievement_wrapper_is_stripped(self):
        self.assertEqual(
            src._strip_superior_wrapper('Superior Achievement in a Novel'),
            'Novel',
        )
        self.assertEqual(
            src._strip_superior_wrapper('Superior Achievement in an Anthology'),
            'Anthology',
        )
        self.assertEqual(
            src._strip_superior_wrapper(
                'Superior Achievement in Poetry (Collection and Long Form)'
            ),
            'Poetry (Collection and Long Form)',
        )
        self.assertEqual(src._heading_kind('Novella'), 'include')
        self.assertEqual(src._heading_kind('Short Story'), 'include')
        self.assertEqual(
            src._heading_kind('Superior Achievement in Non\u2013Fiction'),
            'include',
        )
        self.assertEqual(
            src._strip_superior_wrapper('Superior Achievement in Non\u2013Fiction'),
            'Non-Fiction',
        )

    def test_last_first_inversion(self):
        self.assertEqual(
            src._normalize_author_credit('Jones, Stephen Graham'),
            'Stephen Graham Jones',
        )
        self.assertEqual(
            src._normalize_author_credit('Hendrix, Grady'),
            'Grady Hendrix',
        )
        self.assertEqual(
            src._normalize_author_credit('Wehunt, Michael'),
            'Michael Wehunt',
        )

    def test_complex_editor_strings_are_not_blindly_reversed(self):
        self.assertEqual(
            src._normalize_author_credit('Kulski, Kristy Park, ed.'),
            'Kristy Park Kulski, ed.',
        )
        self.assertEqual(
            src._normalize_author_credit(
                'Golden, Christopher and Keene, Brian, eds.'
            ),
            'Christopher Golden and Brian Keene, eds.',
        )
        self.assertEqual(
            src._normalize_author_credit(
                'Day, Julie C.; Bissett, Carina; and Gidney, Craig Laurance, eds.'
            ),
            'Julie C. Day; Carina Bissett; and Craig Laurance Gidney, eds.',
        )
        self.assertEqual(
            src._normalize_author_credit(
                'Ellen Datlow and Terri Windling'
            ),
            'Ellen Datlow and Terri Windling',
        )


class Inaugural1987Tests(unittest.TestCase):
    def _html(self):
        return '''
        <h3>Novel</h3>
        Live Girls by Ray Garton<br>
        Misery by Stephen King, Winner (Tie)<br>
        Swan Song by Robert R. McCammon, Winner (Tie)<br>
        Unassigned Territory by Kem Nunn<br>
        Ash Wednesday by Chet Williamson
        <h3>First Novel</h3>
        The Damnation Game by Clive Barker<br>
        The Manse by Lisa Cantrell, Winner<br>
        Slob by Rex Miller
        <h3>Short Fiction</h3>
        "Friend's Best Man" by Jonathan Carroll<br>
        "The Deep End" by Robert R. McCammon, Winner
        <h3>Screenplay</h3>
        Some Film by A Writer, Winner
        '''

    def test_1987_novel_two_winners_and_finalist(self):
        records = _parse(1987, self._html())
        novel = [r for r in records if r.category == 'Novel']
        winners = [r for r in novel if r.status == 'Winner']
        self.assertEqual(
            {(r.work_title, r.work_author) for r in winners},
            {
                ('Misery', 'Stephen King'),
                ('Swan Song', 'Robert R. McCammon'),
            },
        )
        self.assertIn(
            ('Live Girls', 'Ray Garton', 'Finalist'),
            {(r.work_title, r.work_author, r.status) for r in novel},
        )
        for record in novel:
            self.assertIsNone(
                src._to_award_result(record).rank
            )

    def test_1987_first_novel_and_short_fiction_winners(self):
        records = _parse(1987, self._html())
        self.assertIn(
            ('First Novel', 'Winner', 'The Manse', 'Lisa Cantrell'),
            _pairs(records),
        )
        self.assertIn(
            ('Short Fiction', 'Winner', 'The Deep End', 'Robert R. McCammon'),
            _pairs(records),
        )

    def test_screenplay_is_excluded(self):
        records = _parse(1987, self._html())
        self.assertFalse(any(r.category == 'Screenplay' for r in records))
        self.assertFalse(any(r.work_title == 'Some Film' for r in records))


class HistoricalEraTests(unittest.TestCase):
    def test_1991_first_novel_tie(self):
        body = '''
        <h3>First Novel</h3>
        Winter Scream by Chris Curry & L. Dean James<br>
        The Cipher by Kathe Koja, Winner (Tie)<br>
        Prodigal by Melanie Tem, Winner (Tie)
        '''
        records = _parse(1991, body)
        winners = [
            r for r in records
            if r.category == 'First Novel' and r.status == 'Winner'
        ]
        self.assertEqual(
            {(r.work_title, r.work_author) for r in winners},
            {('The Cipher', 'Kathe Koja'), ('Prodigal', 'Melanie Tem')},
        )

    def test_1992_novel_winner(self):
        body = '''
        <h3>Novel</h3>
        Homecoming by Matthew Costello<br>
        Blood of the Lamb by Thomas F. Monteleone, Winner<br>
        Children of the Night by Dan Simmons
        '''
        records = _parse(1992, body)
        self.assertIn(
            ('Novel', 'Winner', 'Blood of the Lamb', 'Thomas F. Monteleone'),
            _pairs(records),
        )

    def test_1998_anthology_winner_and_no_award(self):
        body = '''
        <h3>Anthology</h3>
        Robert Bloch's Psychos by Robert Bloch, ed.<br>
        Horrors!: 365 Scary Stories by Stefan Dziemianowicz, ed.,
        Martin H. Greenberg, ed. & Robert Weinberg, ed., Winner
        <h3>Illustrated Narrative</h3>
        Sergio Aragones' Dia de las Muertos by Sergio Aragones & Mark Evanier<br>
        No Award, Winner
        <h3>Other Media</h3>
        Universal Horror by Kevin Brownlow<br>
        No Award, Winner
        '''
        records = _parse(1998, body)
        anthologies = [r for r in records if r.category == 'Anthology']
        winner = [r for r in anthologies if r.status == 'Winner']
        self.assertEqual(len(winner), 1)
        self.assertEqual(winner[0].work_title, 'Horrors!: 365 Scary Stories')
        self.assertIn('Stefan Dziemianowicz', winner[0].work_author)
        self.assertIn('Martin H. Greenberg', winner[0].work_author)
        self.assertIn('Robert Weinberg', winner[0].work_author)
        self.assertEqual(len(anthologies), 1 + 1)
        self.assertFalse(any(r.work_title == 'No Award' for r in records))
        self.assertFalse(
            any(r.category == 'Illustrated Narrative' and r.status == 'Winner'
                for r in records)
        )
        self.assertFalse(any(r.category == 'Other Media' for r in records))

    def test_1988_no_nominees_nonfiction_is_empty_not_fatal(self):
        records = _parse(
            1988,
            '''
            <h3>Novel</h3>
            The Silence of the Lambs by Thomas Harris, Winner<br>
            <h3>Nonfiction</h3>
            No nominees
            ''',
        )
        self.assertIn(
            ('Novel', 'Winner', 'The Silence of the Lambs', 'Thomas Harris'),
            _pairs(records),
        )
        self.assertFalse(any(r.category == 'Nonfiction' for r in records))
        self.assertFalse(any(r.work_title.casefold() == 'no nominees' for r in records))
        self.assertFalse(
            any(r.category == 'Illustrated Narrative' and r.status == 'Winner'
                for r in records)
        )
        self.assertFalse(any(r.category == 'Other Media' for r in records))

    def test_2000_cross_category_same_work(self):
        body = '''
        <h3>Novel</h3>
        The Indifference of Heaven by Gary A. Braunbeck<br>
        The Licking Valley Coon Hunters Club by Brian A. Hopkins<br>
        The Traveling Vampire Show by Richard Laymon, Winner
        <h3>First Novel</h3>
        Nailed by the Heart by Simon Clark<br>
        The Licking Valley Coon Hunters Club by Brian A. Hopkins, Winner<br>
        Run by Douglas E. Winter
        '''
        records = _parse(2000, body)
        club = [
            r for r in records
            if r.work_title == 'The Licking Valley Coon Hunters Club'
        ]
        self.assertEqual(
            {(r.category, r.status) for r in club},
            {('Novel', 'Finalist'), ('First Novel', 'Winner')},
        )
        self.assertIn(
            (
                'Novel',
                'Winner',
                'The Traveling Vampire Show',
                'Richard Laymon',
            ),
            _pairs(records),
        )

    def test_2010_novel_winner_glued_marker(self):
        body = '''
        <h3>Novel</h3>
        Horns by Joe Hill<br>
        A Dark Matter by Peter Straub(winner)
        '''
        records = _parse(2010, body)
        self.assertIn(
            ('Novel', 'Winner', 'A Dark Matter', 'Peter Straub'),
            _pairs(records),
        )

    def test_2015_first_novel_winner(self):
        body = '''
        <h3>First Novel</h3>
        Shutter (Feiwel & Friends) by Courtney Alameda<br>
        Mr. Suicide (Word Horde) by Nicole Cushing, winner
        '''
        records = _parse(2015, body)
        self.assertIn(
            ('First Novel', 'Winner', 'Mr. Suicide', 'Nicole Cushing'),
            _pairs(records),
        )

    def test_2017_novel_winner(self):
        body = '''
        <h3>Novel</h3>
        Ararat (St. Martin's Press) by Christopher Golden, winner<br>
        Sleeping Beauties (Scribner) by Stephen King and Owen King
        '''
        records = _parse(2017, body)
        self.assertIn(
            ('Novel', 'Winner', 'Ararat', 'Christopher Golden'),
            _pairs(records),
        )

    def test_1993_novella_and_2006_short_story_headings(self):
        records_1993 = _parse(
            1993,
            '''
            <h3>Novella</h3>
            The Night We Buried Road Dog by Jack Cady, Winner<br>
            Death in Bangkok by Dan Simmons
            <h3>Novelet</h3>
            Death of a Ghost by Brian Hodge, Winner
            ''',
        )
        self.assertIn(
            ('Novella', 'Winner', 'The Night We Buried Road Dog', 'Jack Cady'),
            _pairs(records_1993),
        )
        self.assertIn(
            ('Novelet', 'Winner', 'Death of a Ghost', 'Brian Hodge'),
            _pairs(records_1993),
        )
        records_2006 = _parse(
            2006,
            '''
            <h3>Short Story</h3>
            Tested by Lisa Morton, Winner<br>
            Feather by David J. Schow
            ''',
        )
        self.assertIn(
            ('Short Story', 'Winner', 'Tested', 'Lisa Morton'),
            _pairs(records_2006),
        )


class Modern2025Tests(unittest.TestCase):
    def _html(self):
        return '''
        <h3>Superior Achievement in a Novel</h3>
        <p>Hendrix, Grady— Witchcraft for Wayward Girls (Berkley)</p>
        <p>Hill, Joe— King Sorrow (William Morrow)</p>
        <p>WINNER: Jones, Stephen Graham— The Buffalo Hunter Hunter (Saga Press / Titan Books)</p>
        <p>Moreno-Garcia, Silvia— The Bewitching (Del Rey)</p>
        <p>Wagner, Wendy N.— Girl in the Creek (Tor Nightfire)</p>
        <h3>Superior Achievement in a First Novel</h3>
        <p>Daly, Grace— The Scald-Crow (Creature Publishing)</p>
        <p>Karella, Bitter— Moonflow (Run For It)</p>
        <p>Pell, Tanya— Her Wicked Roots (Gallery Books)</p>
        <p>Steel, Hester— The Faceless Thing We Adore (Page Street Horror)</p>
        <p>Tennison, Kathryn— Molting (Uncomfortably Dark Horror)</p>
        <p>Viel, Neena— Listen to Your Sister (St. Martin's Griffin / Titan Books)</p>
        <p>WINNER: Wehunt, Michael— The October Film Haunt (St. Martin's Press)</p>
        <h3>Superior Achievement in a Fiction Collection</h3>
        <p>Chapman, Clay McLeod— Acquired Taste (Titan Books)</p>
        <p>WINNER: Langan, John— Lost in The Dark and Other Excursions (Word Horde)</p>
        <h3>Superior Achievement in an Anthology</h3>
        <p>Day, Julie C.; Bissett, Carina; and Gidney, Craig Laurance, eds. — Storyteller: A Tanith Lee Tribute Anthology (Essential Dreams Press)</p>
        <p>WINNER: Kulski, Kristy Park, ed. — Silk &amp; Sinew: A Collection of Folk Horror from the Asian Diaspora (Bad Hand Books)</p>
        <h3>Superior Achievement in Long Fiction (tie)</h3>
        <p>WINNER: Ballingrud, Nathan— Cathedral of the Drowned (Tor Nightfire / Titan Books)</p>
        <p>Ha, Thomas— "Uncertain Sons" (Uncertain Sons and Other Stories, Undertow Publications)</p>
        <p>Langan, Sarah— "Squid Teeth"(Reactor)</p>
        <p>Langan, Sarah— Pam Kowolski is a Monster! (Raw Dog Screaming Press)</p>
        <p>WINNER: Wise, A.C.— "Wolf Moon, Antler Moon" (Reactor)</p>
        <h3>Superior Achievement in Short Fiction</h3>
        <p>WINNER: Joseph, RJ– "Inheritance" (Full Throttle: A Dark Dozen Anthology)</p>
        <p>Daniels, L.E.— "Stomata" (Darkness Most Fowl)</p>
        <h3>Superior Achievement in a Graphic Novel</h3>
        <p>WINNER: Mignola, Mike– Bowling With Corpses and Other Tales from Lands Unknown (Dark Horse Comics)</p>
        <p>King, Sandy(editor) – John Carpenter's Tales for a HalloweeNight, Volume 11</p>
        <h3>Superior Achievement in a Young Adult Novel</h3>
        <p>WINNER: Chapman, Clay McLeod– Shiny Happy People (Delacorte Press)</p>
        <p>Roux, Madeleine — A Girl Walks Into The Forest (Quill Tree Books)</p>
        <h3>Superior Achievement in a Middle Grade Novel</h3>
        <p>WINNER: Dawson, Delilah S.— Ride or Die (Delacorte Press)</p>
        <p>Oh, Ellen— The House Next Door (HarperCollins Children's Books)</p>
        <h3>Superior Achievement in a Screenplay</h3>
        <p>WINNER: Coogler, Ryan— Sinners (Warner Bros.)</p>
        <h3>SPECIALTY AWARDS</h3>
        <p>Lifetime Achievement Award Winners: Lisa Morton, Jonathan Maberry</p>
        <p>Specialty Press Award: Bad Hand Books</p>
        <p>Karen Lansdale Silver Hammer Award: Sarah Read</p>
        <p>Richard Laymon President's Award: Marc L. Abbott</p>
        <p>Mentor of the Year Award: Eric Guignard</p>
        '''

    def test_2025_core_winners_and_finalists(self):
        records = _parse(
            2025,
            self._html(),
            title='The 2025 Bram Stoker Award® Winners',
        )
        self.assertIn(
            (
                'Novel',
                'Winner',
                'The Buffalo Hunter Hunter',
                'Stephen Graham Jones',
            ),
            _pairs(records),
        )
        self.assertIn(
            (
                'Novel',
                'Finalist',
                'Witchcraft for Wayward Girls',
                'Grady Hendrix',
            ),
            _pairs(records),
        )
        self.assertIn(
            (
                'First Novel',
                'Winner',
                'The October Film Haunt',
                'Michael Wehunt',
            ),
            _pairs(records),
        )
        self.assertIn(
            (
                'Fiction Collection',
                'Winner',
                'Lost in The Dark and Other Excursions',
                'John Langan',
            ),
            _pairs(records),
        )
        anth = [
            r for r in records
            if r.category == 'Anthology' and r.status == 'Winner'
        ]
        self.assertEqual(len(anth), 1)
        self.assertEqual(
            anth[0].work_title,
            'Silk & Sinew: A Collection of Folk Horror from the Asian Diaspora',
        )
        self.assertEqual(anth[0].work_author, 'Kristy Park Kulski, ed.')
        long_winners = {
            (r.work_title, r.work_author)
            for r in records
            if r.category == 'Long Fiction' and r.status == 'Winner'
        }
        self.assertEqual(
            long_winners,
            {
                ('Cathedral of the Drowned', 'Nathan Ballingrud'),
                ('Wolf Moon, Antler Moon', 'A.C. Wise'),
            },
        )
        self.assertEqual(
            len([
                r for r in records
                if r.category == 'Long Fiction' and 'Langan' in r.work_author
            ]),
            2,
        )
        self.assertIn(
            ('Short Fiction', 'Winner', 'Inheritance', 'RJ Joseph'),
            _pairs(records),
        )
        self.assertIn(
            (
                'Graphic Novel',
                'Winner',
                'Bowling With Corpses and Other Tales from Lands Unknown',
                'Mike Mignola',
            ),
            _pairs(records),
        )
        self.assertIn(
            (
                'Young Adult Novel',
                'Winner',
                'Shiny Happy People',
                'Clay McLeod Chapman',
            ),
            _pairs(records),
        )
        self.assertIn(
            (
                'Middle Grade Novel',
                'Winner',
                'Ride or Die',
                'Delilah S. Dawson',
            ),
            _pairs(records),
        )
        self.assertFalse(any(r.work_title == 'Sinners' for r in records))
        self.assertFalse(any('Maberry' in r.work_author for r in records))
        self.assertFalse(any(r.work_title == 'Bad Hand Books' for r in records))
        first = [r for r in records if r.category == 'First Novel']
        self.assertEqual(len(first), 7)
        self.assertEqual(
            [r.status for r in first if r.work_title == 'The October Film Haunt'],
            ['Winner'],
        )
        collection_chapman = [
            r for r in records
            if r.work_title == 'Acquired Taste'
        ]
        ya_chapman = [
            r for r in records
            if r.work_title == 'Shiny Happy People'
        ]
        self.assertEqual(collection_chapman[0].category, 'Fiction Collection')
        self.assertEqual(collection_chapman[0].status, 'Finalist')
        self.assertEqual(ya_chapman[0].category, 'Young Adult Novel')
        self.assertEqual(ya_chapman[0].status, 'Winner')

    def test_paragraph_superior_achievement_headings_without_h3(self):
        body = '''
        <p>The Horror Writers Association is proud to announce the winners.</p>
        <p>Superior Achievement in a Novel</p>
        <p>Hendrix, Grady— Witchcraft for Wayward Girls (Berkley)</p>
        <p>WINNER: Jones, Stephen Graham— The Buffalo Hunter Hunter (Saga Press)</p>
        <p>Superior Achievement in a First Novel</p>
        <p>WINNER: Wehunt, Michael— The October Film Haunt (St. Martin's Press)</p>
        '''
        records = _parse(
            2025,
            body,
            title='The 2025 Bram Stoker Award® Winners',
        )
        self.assertIn(
            (
                'Novel',
                'Winner',
                'The Buffalo Hunter Hunter',
                'Stephen Graham Jones',
            ),
            _pairs(records),
        )
        self.assertIn(
            (
                'First Novel',
                'Winner',
                'The October Film Haunt',
                'Michael Wehunt',
            ),
            _pairs(records),
        )

    def test_2024_title_first_winner_line(self):
        body = '''
        <p>Superior Achievement in a Novel</p>
        <p>WINNER: The Haunting of Velkwood, Gwendolyn Kiste (Saga)</p>
        <p>House of Bone and Rain, Gabino Iglesias (Mulholland)</p>
        '''
        records = _parse(
            2024,
            body,
            title='The 2024 Bram Stoker Award® Winners',
        )
        self.assertIn(
            (
                'Novel',
                'Winner',
                'The Haunting of Velkwood',
                'Gwendolyn Kiste',
            ),
            _pairs(records),
        )
        self.assertIn(
            (
                'Novel',
                'Finalist',
                'House of Bone and Rain',
                'Gabino Iglesias',
            ),
            _pairs(records),
        )


class Structure2021Tests(unittest.TestCase):
    def test_winner_and_also_nominated_lists(self):
        body = '''
        <h3>Superior Achievement in a Novel</h3>
        <p>Winner: Stephen Graham Jones– My Heart is a Chainsaw (Gallery/Saga Press)</p>
        <p>Also nominated:</p>
        <p>Castro, V.– The Queen of the Cicadas (Flame Tree Press)</p>
        <p>Hendrix, Grady– The Final Girl Support Group (Berkley)</p>
        <h3>Superior Achievement in a First Novel</h3>
        <p>Winner: Hailey Piper– Queen of Teeth (Strangehouse Books)</p>
        <p>Also nominated:</p>
        <p>Martinez, S. Alessandro– Helminth (Omnium Gatherum)</p>
        <p>McQueen, LaTanya– When the Reckoning Comes (Harper Perennial)</p>
        <p>Miles, Terry– Rabbits (Del Rey)</p>
        <p>Quigley, Lisa– The Forest (Perpetual Motion Machine Publishing)</p>
        <p>Willson, Nicole– Tidepool (The Parliament House)</p>
        <p>*Due to a tie in fifth place, there are six nominees in this category.</p>
        '''
        records = _parse(
            2021,
            body,
            title='The 2021 Bram Stoker Awards® Winners',
        )
        self.assertIn(
            (
                'Novel',
                'Winner',
                'My Heart is a Chainsaw',
                'Stephen Graham Jones',
            ),
            _pairs(records),
        )
        self.assertIn(
            (
                'Novel',
                'Finalist',
                'The Queen of the Cicadas',
                'V. Castro',
            ),
            _pairs(records),
        )
        first = [r for r in records if r.category == 'First Novel']
        self.assertEqual(
            [r.status for r in first if r.work_title == 'Queen of Teeth'],
            ['Winner'],
        )
        self.assertEqual(
            len([r for r in first if r.status == 'Finalist']),
            5,
        )
        self.assertFalse(any('fifth place' in r.work_title.casefold() for r in records))


class Structure2022Tests(unittest.TestCase):
    def _ballot_body(self):
        return '''
        <h3>Superior Achievement in a Novel</h3>
        <p>Iglesias, Gabino– The Devil Takes You Home (Mullholland Press) – WINNER</p>
        <p>Katsu, Alma– The Fervor (G.P. Putnam's Sons)</p>
        <p>Kiste, Gwendolyn– Reluctant Immortals (Saga Press)</p>
        <p>Malerman, Josh– Daphne (Del Rey)</p>
        <p>Ward, Catriona– Sundial (Tor Nightfire)</p>
        <h3>Superior Achievement in a First Novel</h3>
        <p>Adams, Erin– Jackal (Bantam Books)</p>
        <p>Cañas, Isabel– The Hacienda (Berkley)</p>
        <p>Jones, KC– Black Tide (Tor Nightfire)</p>
        <p>Nogle, Christi– Beulah (Cemetery Gates Media) – WINNER</p>
        <p>Wilkes, Ally– All the White Spaces (Emily Bestler Books)</p>
        <h3>Superior Achievement in Long Fiction</h3>
        <p>Katsu, Alma – The Wehrwolf (Amazon Original Stories) – WINNER</p>
        <p>Someone, Else – Other Novella (Press)</p>
        <p>Third, Author – Third Novella (Press)</p>
        <p>Fourth, Author – Fourth Novella (Press)</p>
        <p>Fifth, Author – Fifth Novella (Press)</p>
        '''

    def test_2022_final_ballot_keeps_nonwinning_finalists(self):
        records = _parse(
            2022,
            self._ballot_body(),
            title='The 2022 Bram Stoker Awards® Final Ballot',
        )
        novel = [r for r in records if r.category == 'Novel']
        self.assertEqual(len(novel), 5)
        self.assertEqual(
            [r.work_title for r in novel if r.status == 'Winner'],
            ['The Devil Takes You Home'],
        )
        self.assertIn(
            'The Fervor',
            [r.work_title for r in novel if r.status == 'Finalist'],
        )

    def test_2022_winners_only_page_is_not_a_complete_census(self):
        body = '''
        <h3>Superior Achievement in a Novel</h3>
        <p>Iglesias, Gabino – The Devil Takes You Home (Mullholland Press)</p>
        <h3>Superior Achievement in a First Novel</h3>
        <p>Nogle, Christi – Beulah(Cemetery Gates Media)</p>
        <h3>Superior Achievement in Long Fiction</h3>
        <p>Katsu, Alma – The Wehrwolf (Amazon Original Stories)</p>
        '''
        html = _page(
            body,
            'The 2022 Bram Stoker Award winners',
            2022,
        )
        records = src._parse_year_page(html, 2022, _url(2022))
        self.assertTrue(src._looks_winners_only(records))
        with self.assertRaises(src.BramStokerSourceError) as raised:
            src._validate_year_records(records, 2022, 'winner')
        self.assertIn('winners-only', str(raised.exception).casefold())

    def test_merge_winners_into_existing_ballot_keeps_finalists(self):
        ballot = _parse(
            2022,
            self._ballot_body(),
            title='The 2022 Bram Stoker Awards® Final Ballot',
        )
        winner_only = (
            src._ParsedRecord(
                2022,
                'Novel',
                'Winner',
                'The Devil Takes You Home',
                'Gabino Iglesias',
                _url(2022),
            ),
        )
        merged = src._merge_winners_into_ballot(ballot, winner_only)
        novel = [r for r in merged if r.category == 'Novel']
        self.assertEqual(len(novel), 5)
        self.assertEqual(
            [r.status for r in novel if r.work_title == 'The Devil Takes You Home'],
            ['Winner'],
        )
        self.assertTrue(any(r.work_title == 'The Fervor' for r in novel))


class NegativeAndExclusionTests(unittest.TestCase):
    def test_preliminary_ballot_page_emits_nothing(self):
        body = '''
        <h3>Superior Achievement in a Novel</h3>
        <p>Baker, Kylie Lee — Bat Eater and Other Names for Cora Zeng</p>
        <p>Tingle, Chuck — Lucky Day</p>
        '''
        html = _page(
            body,
            'The 2025 Bram Stoker Awards® Preliminary Ballot Announced',
            2025,
        )
        records = src._parse_year_page(html, 2025, _url(2025))
        self.assertEqual(records, ())

    def test_person_honors_are_not_works(self):
        body = '''
        <h3>Lifetime Achievement Award</h3>
        <p>Lisa Morton</p>
        <h3>Specialty Press Award</h3>
        <p>Bad Hand Books</p>
        <h3>Novel</h3>
        <p>Misery by Stephen King, Winner</p>
        '''
        records = _parse(1987, body)
        self.assertEqual(
            {(r.work_title, r.status) for r in records},
            {('Misery', 'Winner')},
        )


class SameAuthorTests(unittest.TestCase):
    def test_2020_stephen_graham_jones_two_winners(self):
        body = '''
        <h3>Superior Achievement in a Novel</h3>
        <p>Jones, Stephen Graham – The Only Good Indians (Gallery/Saga Press) – Winner</p>
        <p>Katsu, Alma – The Deep (G.P. Putnam's Sons)</p>
        <h3>Superior Achievement in Long Fiction</h3>
        <p>Jones, Stephen Graham – Night of the Mannequins (Tor.com) – Winner</p>
        <p>Iglesias, Gabino – Beyond the Reef (Wicked Run Press)</p>
        '''
        records = _parse(
            2020,
            body,
            title='The 2020 Bram Stoker Award® Winners Announced',
        )
        jones = [
            r for r in records if 'Stephen Graham Jones' in r.work_author
        ]
        self.assertEqual(
            {(r.category, r.work_title, r.status) for r in jones},
            {
                ('Novel', 'The Only Good Indians', 'Winner'),
                ('Long Fiction', 'Night of the Mannequins', 'Winner'),
            },
        )


class IdentityKeyTests(unittest.TestCase):
    def test_cross_category_keys_are_distinct(self):
        novel = src._ParsedRecord(
            2000, 'Novel', 'Finalist',
            'The Licking Valley Coon Hunters Club',
            'Brian A. Hopkins',
            _url(2000),
        )
        first = src._ParsedRecord(
            2000, 'First Novel', 'Winner',
            'The Licking Valley Coon Hunters Club',
            'Brian A. Hopkins',
            _url(2000),
        )
        merged = src._dedupe_records([novel, first])
        self.assertEqual(len(merged), 2)


class FutureCycleParseTests(unittest.TestCase):
    def test_final_ballot_without_winners_is_finalist_state(self):
        body = '''
        <h3>Superior Achievement in a Novel</h3>
        <p>Author, One— First Book (Press)</p>
        <p>Author, Two— Second Book (Press)</p>
        <p>Author, Three— Third Book (Press)</p>
        <p>Author, Four— Fourth Book (Press)</p>
        <p>Author, Five— Fifth Book (Press)</p>
        '''
        records = src._parse_year_page(
            _page(body, 'The 2026 Bram Stoker Awards® Final Ballot', 2026),
            2026,
            src.SITE_ORIGIN + '/news/2026-final-ballot/',
        )
        self.assertEqual(src._classify_year_state(records), 'finalist')
        self.assertTrue(all(r.status == 'Finalist' for r in records))
        src._validate_year_records(records, 2026, 'finalist')


if __name__ == '__main__':
    unittest.main()
