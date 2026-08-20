"""Offline unittest coverage for the Hugo Best Novel parser and archive helpers."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from awards.sources import hugo

URL_1966 = 'https://www.thehugoawards.org/hugo-history/1966-hugo-awards/'
URL_1968 = 'https://www.thehugoawards.org/hugo-history/1968-hugo-awards/'
URL_1985 = 'https://www.thehugoawards.org/hugo-history/1995-hugo-awards-2/'
URL_2015 = 'https://www.thehugoawards.org/hugo-history/2015-hugo-awards/'
URL_2020 = 'https://www.thehugoawards.org/hugo-history/2020-hugo-awards/'
URL_2025 = 'https://www.thehugoawards.org/hugo-history/2025-hugo-awards/'
URL_2026 = 'https://www.thehugoawards.org/hugo-history/2026-hugo-awards/'
URL_2016 = 'https://www.thehugoawards.org/hugo-history/2016-hugo-awards/'

HTML_1966 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Dune</em> by Frank Herbert [Chilton, 1965] (tie)</li>
<li class="winner"><em>&#8230;And Call Me Conrad (alt: This Immortal)</em> by Roger Zelazny [<em>F&amp;SF</em> Oct,Nov 1965; Ace, 1965] (tie)</li>
<li><em>The Squares of the City</em> by John Brunner [Ballantine, 1965]</li>
<li><em>The Moon is a Harsh Mistress</em> by Robert A. Heinlein [<em>If</em> Dec 1965,Jan,Feb,Mar,Apr 1966; Putnam, 1966]</li>
<li><em>Skylark DuQuesne</em> by Edward E. Smith [<em>If</em> Jun,Jul,Aug,Oct 1965]</li>
</ul>
<p><strong>Short Fiction</strong></p>
<ul>
<li class="winner">&#8220;&#8216;Repent, Harlequin!&#8217; Said the Ticktockman&#8221; by Harlan Ellison [<em>Galaxy</em> Dec 1965]</li>
</ul>
"""

HTML_2025 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>The Tainted Cup</em> by Robert Jackson Bennett (Del Rey, Hodderscape UK)</li>
<li><em>A Sorceress Comes to Call</em> by T. Kingfisher (Tor)</li>
<li><em>Alien Clay</em> by Adrian Tchaikovsky (Orbit US, Tor UK)</li>
<li><em>Someone You Can Build a Nest In</em> by John Wiswell (DAW)</li>
<li><em>The Ministry of Time</em> by Kaliane Bradley (Avid Reader Press, Sceptre)</li>
<li><em>Service Model</em> by Adrian Tchaikovsky (Tordotcom)</li>
</ul>
<p>1078 ballots cast for 554 nominees, finalists range 90 to 157.</p>
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner"><em>The Tusks of Extinction</em> by Ray Nayler (Tordotcom)</li>
</ul>
<p><strong>Best Novelette</strong></p>
<ul>
<li class="winner">“The Four Sisters Overlooking the Sea” by Naomi Kritzer</li>
</ul>
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner">“Stitched to Skin like Family Is” by Nghi Vo</li>
</ul>
"""

HTML_2026 = """
<p><strong>Best Novel</strong></p>
<ul>
<li><em>A Drop of Corruption</em> by Robert Jackson Bennett (Del Rey; Hodderscape)</li>
<li><em>Death of the Author</em> by Nnedi Okorafor (William Morrow; Gollancz)</li>
<li><em>Shroud</em> by Adrian Tchaikovsky (Tor UK; Orbit US)</li>
<li><em>The Everlasting</em> by Alix E. Harrow (Tor US; Tor UK)</li>
<li><em>The Incandescent</em> by Emily Tesh (Tor US; Orbit UK)</li>
<li><em>The Raven Scholar</em> by Antonia Hodgson (Orbit US; Hodderscape)</li>
</ul>
<p>1,153 ballots cast for 555 nominees. Finalists range 126-210.</p>
<p><strong>Best Novella</strong></p>
<ul>
<li><em>Automatic Noodle</em> by Annalee Newitz (Tordotcom)</li>
<li><em>A Mouthful of Dust</em> by Nghi Vo (Tordotcom)</li>
</ul>
<p><strong>Best Novelette</strong></p>
<ul>
<li>“Kaiju Agonistes” by Scott Lynch (Uncanny Magazine, Issue 62)</li>
</ul>
<p><strong>Best Short Story</strong></p>
<ul>
<li>“10 Visions of the Future; or, Self-Care for the End of Days” by Samantha Mills (<em>Uncanny Magazine</em>, Issue 63)</li>
</ul>
"""

HTML_1958 = """
<p><strong>Best Novel or Novelette</strong></p>
<ul>
<li class="winner"><em>The Big Time</em> by Fritz Leiber [<em>Galaxy</em> Mar,Apr 1958]</li>
</ul>
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner">&#8220;Or All the Seas with Oysters&#8221; by Avram Davidson [<em>Galaxy Science Fiction</em> May 1958]</li>
</ul>
"""

URL_1958 = 'https://www.thehugoawards.org/hugo-history/1958-hugo-awards/'

HTML_1958_SHORT_STORY_ONLY = """
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner">&#8220;Or All the Seas with Oysters&#8221; by Avram Davidson [<em>Galaxy Science Fiction</em> May 1958]</li>
</ul>
"""

HTML_1957 = """
<p><strong>Best American Professional Magazine</strong></p>
<ul>
<li class="winner"><em>Astounding Science Fiction</em> ed. by John W. Campbell, Jr.</li>
</ul>
<p><strong>Best Fanzine</strong></p>
<ul>
<li class="winner"><em>Science Fiction Times</em> ed. by James V. Taurasi, Sr., Ray Van Houten and Frank R. Prieto, Jr.</li>
</ul>
"""

HTML_1959 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>A Case of Conscience</em> by James Blish</li>
</ul>
<p><strong>Best Novelette</strong></p>
<ul>
<li class="winner">&#8220;The Big Front Yard&#8221; by Clifford D. Simak</li>
</ul>
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner">&#8220;That Hell-Bound Train&#8221; by Robert Bloch</li>
</ul>
"""

HTML_NO_SUPPORTED_WRITTEN_WORKS = """
<p><strong>Best Dramatic Presentation</strong></p>
<ul>
<li class="winner"><em>Should Not Appear</em> by Dramatic Author (Press)</li>
</ul>
"""

HTML_DIALECTS = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Double Star</em> by Robert A. Heinlein [<em>Astounding</em> Feb,Mar,Apr 1956]</li>
<li><em>Call Him Dead</em>, by Eric Frank Russell</li>
<li class="winner"><strong>Ancillary Justice</strong>, Ann Leckie (Orbit US/Orbit UK)</li>
<li><strong>No Award</strong></li>
<li>No winner chosen</li>
<li>Insufficient Nominations &#8211; Not on ballot</li>
</ul>
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner"><em>Should Not Leak</em> by A. Leak</li>
</ul>
"""

HTML_DUNE_WORLD = """
<p><strong>Best Novel</strong></p>
<ul>
<li><em>Dune World</em> by Frank Herbert [Analog, 1963]</li>
<li><em>Way Station</em> by Clifford D. Simak [Galaxy, 1963]</li>
</ul>
"""

HTML_1985 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Neuromancer</em> by William Gibson [Ace, 1984]</li>
</ul>
"""

HTML_RETRO = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Should Not Appear</em> by Retro Author (Press)</li>
</ul>
"""

HTML_INTERVENING_LIST = """
<p><strong>Best Novel</strong></p>
<p>Presented at: intervening commentary that is not the novel list.</p>
<ul>
<li class="winner"><em>Should Not Associate</em> by Intervening Author (Press)</li>
</ul>
<p><strong>Best Novella</strong></p>
<ul>
<li><em>Also Should Not Leak</em> by Other Author (Tor)</li>
</ul>
"""

HTML_MALFORMED_STRONG_TITLE = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><strong>Ancillary Justice</strong>, Ann Leckie (Orbit US/Orbit UK)</li>
<li><strong>Warbound, Book III of the Grimnoir Chronicle</strong>s, Larry Correia (Baen Books)</li>
<li><strong>Parasite</strong>, Mira Grant (Orbit US/Orbit UK)</li>
</ul>
"""

HTML_2015 = """
<p><strong>Best Novel</strong> (5653 final ballots, 1827 nominating ballots, 587 entries, range 212-387)</p>
<ul>
<li class="winner"><strong>The Three Body Problem</strong>, Cixin Liu, Ken Liu translator (Tor Books)</li>
<li><strong>The Goblin Emperor</strong>, Katherine Addison (Sarah Monette) (Tor Books)</li>
<li><strong>Ancillary Sword</strong>, Ann Leckie (Orbit US/Orbit UK)</li>
<li><strong>No Award</strong></li>
<li><strong>Skin Game</strong>, Jim Butcher (Orbit UK/Roc Books)</li>
<li><strong>The Dark Between the Stars</strong>, Kevin J. Anderson (Tor Books)</li>
</ul>
<p><strong>Best Novella</strong> (5337 final ballots, 1083 nominating ballots, 201 entries, range 145-338)</p>
<ul>
<li class="winner"><strong>No Award</strong></li>
<li><strong>&#8220;Flow&#8221;</strong>, Arlan Andrews, Sr. (Analog, 11-2014)</li>
<li><strong>&#8220;The Plural of Helen of Troy&#8221;</strong>, John C. Wright (The Book of Feasts &amp; Seasons, Castalia House)</li>
</ul>
<p><strong>Best Short Story</strong> (5267 final ballots, 1174 nominating ballots, 728 entries, range 132-226)</p>
<ul>
<li class="winner"><strong>No Award</strong></li>
<li><strong>“Totaled”</strong>, Kary English (<em>Galaxy&#8217;s Edge Magazine</em>, 07-2014)</li>
<li><strong>&#8220;A Single Samurai”</strong>, Steven Diamond (<strong>The Baen Big Book of Monsters</strong>, Baen Books)</li>
</ul>
"""

HTML_2016 = """
<p><strong>Best Novel</strong> (2903 final ballots, 3695 nominating ballots)</p>
<ul>
<li class="winner"><em>The Fifth Season</em> by N.K. Jemisin (Orbit)</li>
<li><em>Uprooted</em> by Naomi Novik (Del Rey)</li>
<li><em>Ancillary Mercy</em> by Ann Leckie (Orbit)</li>
<li><em>Seveneves: A Novel</em> by Neal Stephenson (William Morrow)</li>
<li><em>The Cinder Spires: The Aeronaut’s Windlass</em> by Jim Butcher (Roc)</li>
</ul>
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner"><em>Binti</em> by Nnedi Okorafor (Tor.com)</li>
</ul>
"""

HTML_ARBITRARY_PARENTHETICAL = """
<p><strong>Best Novel</strong> (see Worldcon program notes)</p>
<ul>
<li class="winner"><em>Should Not Associate</em> by Intervening Author (Press)</li>
</ul>
"""

HTML_1968 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Lord of Light</em> by Roger Zelazny [Doubleday, 1967]</li>
</ul>
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner">&#8220;Riders of the Purple Wage&#8221; by Philip José Farmer [<em>Dangerous Visions</em>, 1967]</li>
<li class="winner">&#8220;Weyr Search&#8221; by Anne McCaffrey [<em>Analog</em> Oct 1967]</li>
<li>&#8220;Damnation Alley&#8221; by Roger Zelazny [<em>Galaxy</em> Oct 1967]</li>
</ul>
<p><strong>Best Novelette</strong></p>
<ul>
<li class="winner">&#8220;Gonna Roll the Bones&#8221; by Fritz Leiber [<em>Dangerous Visions</em>, 1967]</li>
</ul>
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner">&#8220;I Have No Mouth, and I Must Scream&#8221; by Harlan Ellison [<em>If</em> Mar 1967]</li>
<li>&#8220;The Jigsaw Man&#8221; by Larry Niven [Dangerous Visions, 1967]</li>
</ul>
"""

HTML_2020 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>A Memory Called Empire</em>, by Arkady Martine (Tor; Tor UK)</li>
</ul>
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner"><em>This Is How You Lose the Time War</em>, by Amal El-Mohtar and Max Gladstone (Saga Press; Jo Fletcher Books)</li>
<li><em>Anxiety Is the Dizziness of Freedom</em>, by Ted Chiang (Exhalation)</li>
</ul>
<p><strong>Best Novelette</strong></p>
<ul>
<li class="winner"><em>Emergency Skin</em>, by N.K. Jemisin (<em>Forward Collection</em> (Amazon))</li>
</ul>
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner">“As the Last I May Know”, by S.L. Huang (Tor.com, 23 October 2019)</li>
</ul>
<p><strong>Best Series</strong></p>
<ul>
<li class="winner"><em>The Expanse</em>, by James S. A. Corey (Orbit US; Orbit UK)</li>
</ul>
"""

HTML_NOVEL_ONLY_2020 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>A Memory Called Empire</em>, by Arkady Martine (Tor; Tor UK)</li>
</ul>
"""

HTML_NOVEL_AND_NOVELLA_ONLY_2020 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>A Memory Called Empire</em>, by Arkady Martine (Tor; Tor UK)</li>
</ul>
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner"><em>This Is How You Lose the Time War</em>, by Amal El-Mohtar and Max Gladstone (Saga Press; Jo Fletcher Books)</li>
</ul>
"""

HTML_NOVEL_NOVELLA_NOVELETTE_ONLY_2020 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>A Memory Called Empire</em>, by Arkady Martine (Tor; Tor UK)</li>
</ul>
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner"><em>This Is How You Lose the Time War</em>, by Amal El-Mohtar and Max Gladstone (Saga Press; Jo Fletcher Books)</li>
</ul>
<p><strong>Best Novelette</strong></p>
<ul>
<li class="winner"><em>Emergency Skin</em>, by N.K. Jemisin (<em>Forward Collection</em> (Amazon))</li>
</ul>
"""

HTML_1971_NOVELETTE_GAP = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Ringworld</em> by Larry Niven [Ballantine, 1970]</li>
</ul>
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner">&#8220;Ill Met in Lankhmar&#8221; by Fritz Leiber [<em>F&amp;SF</em> Apr 1970]</li>
</ul>
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner">&#8220;Slow Sculpture&#8221; by Theodore Sturgeon [<em>Galaxy</em> Feb 1970]</li>
</ul>
"""

URL_2010 = 'https://www.thehugoawards.org/hugo-history/2010-hugo-awards/'

HTML_2010_NOVELETTE = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>The Windup Girl</em> by Paolo Bacigalupi (Night Shade)</li>
</ul>
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner"><em>Palimpsest</em>, Charles Stross (Wireless; Ace; Orbit)</li>
</ul>
<p><strong>Best Novelette</strong></p>
<ul>
<li class="winner">The Island&#8221;, Peter Watts (<em>The New Space Opera 2</em>; Eos)</li>
<li>&#8220;Overtime&#8221;, Charles Stross (Tor.com 12/09)</li>
</ul>
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner">&#8220;Bridesicle&#8221;, Will McIntosh (<em>Asimov’s</em> 1/09)</li>
</ul>
"""

HTML_UNOPENED_QUOTE_WITHOUT_AUTHOR = """
<p><strong>Best Novelette</strong></p>
<ul>
<li class="winner">Not A Recoverable Title”</li>
</ul>
"""

HTML_UNOPENED_QUOTE_AS_BEST_NOVEL = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner">The Island&#8221;, Peter Watts (<em>The New Space Opera 2</em>; Eos)</li>
</ul>
"""

HTML_UNOPENED_QUOTE_NOVELETTE_ONLY = """
<p><strong>Best Novelette</strong></p>
<ul>
<li class="winner">The Island&#8221;, Peter Watts (<em>The New Space Opera 2</em>; Eos)</li>
</ul>
"""

HTML_UNOPENED_QUOTE_AS_SHORT_STORY = """
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner">The Island&#8221;, Peter Watts (<em>The New Space Opera 2</em>; Eos)</li>
</ul>
"""

HTML_UNOPENED_QUOTE_AS_SHORT_FICTION = """
<p><strong>Short Fiction</strong></p>
<ul>
<li class="winner">The Island&#8221;, Peter Watts (<em>The New Space Opera 2</em>; Eos)</li>
</ul>
"""

URL_1960 = 'https://www.thehugoawards.org/hugo-history/1960-hugo-awards/'
URL_1962 = 'https://www.thehugoawards.org/hugo-history/1962-hugo-awards/'
URL_1967 = 'https://www.thehugoawards.org/hugo-history/1967-hugo-awards/'
URL_1973 = 'https://www.thehugoawards.org/hugo-history/1973-hugo-awards/'

HTML_1960_SHORT_FICTION = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Starship Troopers</em> by Robert A. Heinlein [Putnam, 1959]</li>
</ul>
<p><strong>Short Fiction</strong></p>
<ul>
<li class="winner">&#8220;Flowers for Algernon&#8221; by Daniel Keyes [<em>F&amp;SF</em> Apr 1959]</li>
<li>&#8220;The Alley Man&#8221; by Philip José Farmer [<em>F&amp;SF</em> Jun 1959]</li>
</ul>
"""

HTML_1962_SHORT_FICTION = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Stranger in a Strange Land</em> by Robert A. Heinlein [Putnam, 1961]</li>
</ul>
<p><strong>Short Fiction</strong></p>
<ul>
<li class="winner">the &#8220;Hothouse&#8221; series by Brian W. Aldiss [<em>F&amp;SF</em> Feb,Apr,Jul,Sep,Dec 1961]</li>
<li>&#8220;Monument&#8221; by Lloyd Biggle, Jr. [<em>Analog</em> Jun 1961]</li>
<li>&#8220;Scylla&#8217;s Daughter&#8221; by Fritz Leiber [<em>Fantastic</em> May 1961]</li>
</ul>
"""

HTML_1966_NOVEL_ONLY = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Dune</em> by Frank Herbert [Chilton, 1965] (tie)</li>
</ul>
"""

HTML_1967 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>The Moon is a Harsh Mistress</em> by Robert A. Heinlein</li>
</ul>
<p><strong>Best Novelette</strong></p>
<ul>
<li class="winner">&#8220;The Last Castle&#8221; by Jack Vance [<em>Galaxy</em> Apr 1966]</li>
</ul>
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner">&#8220;Neutron Star&#8221; by Larry Niven [<em>If</em> Oct 1966]</li>
</ul>
"""

HTML_1973_SHORT_STORY = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>The Gods Themselves</em> by Isaac Asimov</li>
</ul>
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner">&#8220;Eurema&#8217;s Dam&#8221; by R. A. Lafferty [<em>New Dimensions #2</em>, 1972]</li>
<li class="winner">&#8220;The Meeting&#8221; by Frederik Pohl and C. M. Kornbluth [<em>F&amp;SF</em> Nov 1972]</li>
<li>&#8220;When It Changed&#8221; by Joanna Russ [<em>Again, Dangerous Visions</em>, 1972]</li>
</ul>
"""

HTML_STRAIGHT_QUOTED_NOVELLA = """
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner">"Riders of the Purple Wage" by Philip José Farmer [<em>Dangerous Visions</em>, 1967]</li>
</ul>
"""

HTML_2014_NOMINATING_NOTE = """
<p><strong>Best Novel</strong> (1595 nominating ballots)</p>
<ul>
<li class="winner"><strong>Ancillary Justice</strong>, Ann Leckie (Orbit US/Orbit UK)</li>
</ul>
<p><strong>Best Novella</strong> (847 nominating ballots)</p>
<ul>
<li class="winner"><strong>&#8220;Equoid&#8221;</strong>, Charles Stross (<em>Tor.com</em>, 09-2013)</li>
<li><strong>Six-Gun Snow White</strong>, Catherynne M. Valente (Subterranean Press)</li>
</ul>
"""

HTML_2021_UNPAREN_BALLOT_NOTES = """
<p><strong>Best Novella</strong><br />
1691 final ballots cast (71.6%)<br />
778 nominating ballots for 157 nominees, finalist range 219-124</p>
<ul>
<li class="winner"><em>The Empress of Salt and Fortune</em>, Nghi Vo (Tor.com)</li>
<li><em>Ring Shout</em>, P. Djèlí Clark (Tor.com)</li>
</ul>
"""

HTML_2022_UNPAREN_BALLOT_NOTE = """
<p><strong>Best Novella</strong><br />
807 nominating ballots for 138 nominees; finalist range 90-235</p>
<ul>
<li class="winner"><em>A Psalm for the Wild-Built</em>, by Becky Chambers (Tordotcom)</li>
</ul>
"""


def _find_records(records, *, title: str, author: str | None = None):
    matches = [record for record in records if record.work_title == title]
    if author is not None:
        matches = [record for record in matches if record.work_author == author]
    return matches


def _archive_item(title: str, link: str, content: str, slug: str = 'unused'):
    return {
        'title': {'rendered': title},
        'link': link,
        'slug': slug,
        'content': {'rendered': content},
    }


class HugoParserTests(unittest.TestCase):
    def test_1966_tied_winners_and_finalists(self):
        records = hugo._parse_best_novel_html(HTML_1966, 1966, URL_1966)
        dune = _find_records(records, title='Dune', author='Frank Herbert')
        self.assertEqual(len(dune), 1)
        self.assertEqual(dune[0].status, 'Winner')
        self.assertEqual(dune[0].award_year, 1966)
        self.assertEqual(dune[0].source_url, URL_1966)

        conrad = [
            record
            for record in records
            if 'Call Me Conrad' in record.work_title
        ]
        self.assertEqual(len(conrad), 1)
        self.assertEqual(conrad[0].status, 'Winner')
        self.assertEqual(conrad[0].work_author, 'Roger Zelazny')
        self.assertNotIn('alt:', conrad[0].work_title.casefold())

        squares = _find_records(
            records,
            title='The Squares of the City',
            author='John Brunner',
        )
        self.assertEqual(len(squares), 1)
        self.assertEqual(squares[0].status, 'Finalist')

        self.assertEqual(sum(1 for record in records if record.status == 'Winner'), 2)
        self.assertEqual(sum(1 for record in records if record.status == 'Finalist'), 3)
        self.assertTrue(
            all(record.status != 'Winner' or 'winner' in HTML_1966 for record in records)
        )
        self.assertNotIn('Repent, Harlequin', ' '.join(r.work_title for r in records))

    def test_this_immortal_alternate_title_matches_tied_winner(self):
        records = hugo._parse_best_novel_html(HTML_1966, 1966, URL_1966)
        conrad = [
            record
            for record in records
            if record.work_author == 'Roger Zelazny'
        ][0]
        self.assertTrue(
            hugo._record_matches(conrad, 'This Immortal', 'Roger Zelazny')
        )
        self.assertTrue(
            hugo._record_matches(conrad, '...And Call Me Conrad', 'Roger Zelazny')
        )
        self.assertFalse(hugo._record_matches(conrad, 'Dune', 'Frank Herbert'))

    def test_2025_winner_and_finalist(self):
        records = hugo._parse_best_novel_html(HTML_2025, 2025, URL_2025)
        tainted = _find_records(
            records,
            title='The Tainted Cup',
            author='Robert Jackson Bennett',
        )
        self.assertEqual(len(tainted), 1)
        self.assertEqual(tainted[0].status, 'Winner')

        sorceress = _find_records(
            records,
            title='A Sorceress Comes to Call',
            author='T. Kingfisher',
        )
        self.assertEqual(len(sorceress), 1)
        self.assertEqual(sorceress[0].status, 'Finalist')
        self.assertEqual(len(records), 6)
        self.assertNotIn('The Tusks of Extinction', [r.work_title for r in records])
        self.assertNotIn(
            'The Four Sisters Overlooking the Sea',
            [r.work_title for r in records],
        )

    def test_2026_finalists_do_not_invent_a_winner(self):
        records = hugo._parse_best_novel_html(HTML_2026, 2026, URL_2026)
        self.assertEqual(len(records), 6)
        self.assertTrue(all(record.status == 'Finalist' for record in records))
        self.assertNotIn('Winner', [record.status for record in records])
        drop = _find_records(
            records,
            title='A Drop of Corruption',
            author='Robert Jackson Bennett',
        )
        self.assertEqual(len(drop), 1)
        self.assertEqual(drop[0].status, 'Finalist')
        self.assertNotIn('Automatic Noodle', [r.work_title for r in records])

    def test_best_novel_or_novelette_is_not_best_novel(self):
        records = hugo._parse_best_novel_html(HTML_1958, 1958, URL_1958)
        self.assertEqual(records, [])

    def test_citation_dialects_and_non_work_rows(self):
        records = hugo._parse_best_novel_html(
            HTML_DIALECTS, 2014, 'https://example.test/dialects'
        )
        titles = [record.work_title for record in records]
        self.assertEqual(
            _find_records(records, title='Double Star', author='Robert A. Heinlein')[0].status,
            'Winner',
        )
        self.assertEqual(
            _find_records(records, title='Call Him Dead', author='Eric Frank Russell')[0].status,
            'Finalist',
        )
        ancillary = _find_records(
            records, title='Ancillary Justice', author='Ann Leckie'
        )
        self.assertEqual(len(ancillary), 1)
        self.assertEqual(ancillary[0].status, 'Winner')
        self.assertNotIn('No Award', titles)
        self.assertNotIn('Should Not Leak', titles)
        self.assertEqual(len(records), 3)

    def test_dune_does_not_match_dune_world(self):
        dune = hugo._parse_best_novel_html(HTML_1966, 1966, URL_1966)[0]
        world = hugo._parse_best_novel_html(HTML_DUNE_WORLD, 1964, 'https://example.test/1964')[0]
        self.assertEqual(dune.work_title, 'Dune')
        self.assertEqual(world.work_title, 'Dune World')
        self.assertTrue(hugo._record_matches(dune, 'Dune', 'Frank Herbert'))
        self.assertFalse(hugo._record_matches(world, 'Dune', 'Frank Herbert'))
        self.assertFalse(hugo._record_matches(dune, 'Dune World', 'Frank Herbert'))
        self.assertFalse(hugo._record_matches(dune, 'The Three', 'Frank Herbert'))

    def test_standalone_ampersand_matches_and(self):
        self.assertTrue(
            hugo._titles_equivalent(
                'Jonathan Strange and Mr Norrell',
                'Jonathan Strange & Mr Norrell',
            )
        )
        self.assertTrue(
            hugo._titles_equivalent(
                'Jonathan Strange & Mr Norrell',
                'Jonathan Strange and Mr Norrell',
            )
        )
        self.assertTrue(
            hugo._titles_equivalent('Smith & Jones', 'Smith and Jones')
        )
        self.assertFalse(
            hugo._titles_equivalent('The City', 'The City & The City')
        )

    def test_quotation_punctuation_matches_but_internal_apostrophes_do_not(self):
        records = hugo._parse_category_html(
            HTML_1966, 1966, URL_1966, hugo.CATEGORY_SHORT_FICTION
        )
        ticktockman = [
            record
            for record in records
            if record.work_author == 'Harlan Ellison'
        ][0]
        self.assertEqual(
            ticktockman.work_title,
            '‘Repent, Harlequin!’ Said the Ticktockman',
        )
        self.assertTrue(
            hugo._record_matches(
                ticktockman,
                '"Repent, Harlequin!" Said the Ticktockman',
                'Harlan Ellison',
            )
        )
        self.assertTrue(
            hugo._record_matches(
                ticktockman,
                "'Repent, Harlequin!' Said the Ticktockman",
                'Harlan Ellison',
            )
        )
        self.assertTrue(
            hugo._titles_equivalent(
                "'Repent, Harlequin!' Said the Ticktockman",
                '"Repent, Harlequin!" Said the Ticktockman',
            )
        )
        self.assertTrue(
            hugo._titles_equivalent(
                '‘Repent, Harlequin!’ Said the Ticktockman',
                '"Repent, Harlequin!" Said the Ticktockman',
            )
        )
        self.assertFalse(
            hugo._titles_equivalent("Don't Look Now", 'Dont Look Now')
        )
        self.assertFalse(
            hugo._titles_equivalent("King's Justice", 'Kings Justice')
        )
        self.assertTrue(
            hugo._titles_equivalent("Don't Look Now", 'Don’t Look Now')
        )
        self.assertTrue(
            hugo._titles_equivalent(
                'Jonathan Strange and Mr Norrell',
                'Jonathan Strange & Mr Norrell',
            )
        )
        self.assertTrue(
            hugo._titles_equivalent('Seveneves: A Novel', 'Seveneves')
        )
        self.assertFalse(
            hugo._titles_equivalent('Seveneves', 'Seveneves Extra Words')
        )

    def test_ticktockman_lookup_uses_calibre_double_quote_form(self):
        hugo._archive_records_cache = tuple(
            hugo._parse_supported_categories_html(HTML_1966, 1966, URL_1966)
        )
        try:
            results = hugo.lookup(
                '"Repent, Harlequin!" Said the Ticktockman',
                'Harlan Ellison',
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].award_name, 'Hugo Award')
            self.assertEqual(results[0].award_year, 1966)
            self.assertEqual(results[0].category, 'Short Fiction')
            self.assertEqual(results[0].status, 'Winner')
            self.assertIsNone(results[0].rank)
            self.assertEqual(results[0].work_author, 'Harlan Ellison')
        finally:
            hugo._archive_records_cache = None

    def test_word_separator_hyphen_matches_but_prefix_does_not(self):
        three_body = hugo._parse_best_novel_html(HTML_2015, 2015, URL_2015)[0]
        self.assertEqual(three_body.work_title, 'The Three Body Problem')
        self.assertTrue(
            hugo._record_matches(three_body, 'The Three Body Problem', 'Cixin Liu')
        )
        self.assertTrue(
            hugo._record_matches(three_body, 'The Three-Body Problem', 'Cixin Liu')
        )
        self.assertFalse(
            hugo._record_matches(three_body, 'The Three', 'Cixin Liu')
        )
        self.assertFalse(
            hugo._record_matches(three_body, 'The Three Body Problem', 'Ann Leckie')
        )

    def test_to_award_result_fields(self):
        dune = _find_records(
            hugo._parse_best_novel_html(HTML_1966, 1966, URL_1966),
            title='Dune',
            author='Frank Herbert',
        )[0]
        result = hugo._to_award_result(dune)
        self.assertEqual(result.award_name, 'Hugo Award')
        self.assertEqual(result.category, 'Best Novel')
        self.assertEqual(dune.category, 'Best Novel')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'Hugo Awards')
        self.assertEqual(result.source_url, URL_1966)
        self.assertIsNone(result.notes)

    def test_2015_ballot_count_note_with_entries_does_not_drop_best_novel(self):
        records = hugo._parse_best_novel_html(HTML_2015, 2015, URL_2015)
        titles = [record.work_title for record in records]
        three_body = _find_records(
            records,
            title='The Three Body Problem',
            author='Cixin Liu, Ken Liu translator',
        )
        self.assertEqual(len(three_body), 1)
        self.assertEqual(three_body[0].status, 'Winner')
        skin = _find_records(records, title='Skin Game', author='Jim Butcher')
        self.assertEqual(len(skin), 1)
        self.assertEqual(skin[0].status, 'Finalist')
        self.assertEqual(len(records), 5)
        self.assertNotIn('No Award', titles)
        self.assertNotIn('Flow', titles)

    def test_2016_ballot_count_note_does_not_drop_best_novel(self):
        records = hugo._parse_best_novel_html(HTML_2016, 2016, URL_2016)
        fifth = _find_records(
            records,
            title='The Fifth Season',
            author='N.K. Jemisin',
        )
        self.assertEqual(len(fifth), 1)
        self.assertEqual(fifth[0].status, 'Winner')
        self.assertEqual(fifth[0].award_year, 2016)
        uprooted = _find_records(
            records,
            title='Uprooted',
            author='Naomi Novik',
        )
        self.assertEqual(len(uprooted), 1)
        self.assertEqual(uprooted[0].status, 'Finalist')
        self.assertEqual(len(records), 5)
        self.assertNotIn('Binti', [record.work_title for record in records])

    def test_2016_ballot_count_note_accepts_comma_grouped_numbers(self):
        html = HTML_2016.replace(
            '(2903 final ballots, 3695 nominating ballots)',
            '(2,903 final ballots, 2,416 nominating ballots)',
        )
        records = hugo._parse_best_novel_html(html, 2016, URL_2016)
        self.assertEqual(
            _find_records(
                records, title='The Fifth Season', author='N.K. Jemisin'
            )[0].status,
            'Winner',
        )

    def test_arbitrary_parenthetical_commentary_does_not_keep_pending_list(self):
        records = hugo._parse_best_novel_html(
            HTML_ARBITRARY_PARENTHETICAL,
            2016,
            'https://example.test/parenthetical',
        )
        titles = [record.work_title for record in records]
        self.assertEqual(records, [])
        self.assertNotIn('Should Not Associate', titles)

    def test_intervening_markup_does_not_claim_a_later_list(self):
        records = hugo._parse_best_novel_html(
            HTML_INTERVENING_LIST,
            2014,
            'https://example.test/intervening',
        )
        titles = [record.work_title for record in records]
        self.assertEqual(records, [])
        self.assertNotIn('Should Not Associate', titles)
        self.assertNotIn('Also Should Not Leak', titles)

    def test_malformed_strong_title_row_is_skipped_not_repaired(self):
        records = hugo._parse_best_novel_html(
            HTML_MALFORMED_STRONG_TITLE,
            2014,
            'https://example.test/warbound',
        )
        titles = [record.work_title for record in records]
        authors = [record.work_author for record in records]
        self.assertEqual(len(records), 2)
        self.assertEqual(
            _find_records(
                records, title='Ancillary Justice', author='Ann Leckie'
            )[0].status,
            'Winner',
        )
        self.assertEqual(
            _find_records(records, title='Parasite', author='Mira Grant')[0].status,
            'Finalist',
        )
        self.assertNotIn('Warbound, Book III of the Grimnoir Chronicle', titles)
        self.assertNotIn('Warbound, Book III of the Grimnoir Chronicles', titles)
        self.assertNotIn('Larry Correia', authors)
        self.assertFalse(any('Warbound' in title for title in titles))
        self.assertFalse(any(author.casefold().startswith('s,') for author in authors))

    def test_1968_quoted_novella_winners_and_magazine_em_is_not_the_title(self):
        records = hugo._parse_category_html(
            HTML_1968, 1968, URL_1968, hugo.CATEGORY_BEST_NOVELLA
        )
        riders = _find_records(
            records,
            title='Riders of the Purple Wage',
            author='Philip José Farmer',
        )
        self.assertEqual(len(riders), 1)
        self.assertEqual(riders[0].status, 'Winner')
        self.assertEqual(riders[0].category, 'Best Novella')
        self.assertEqual(riders[0].award_year, 1968)
        self.assertEqual(riders[0].source_url, URL_1968)
        weyr = _find_records(
            records,
            title='Weyr Search',
            author='Anne McCaffrey',
        )
        self.assertEqual(len(weyr), 1)
        self.assertEqual(weyr[0].status, 'Winner')
        alley = _find_records(
            records,
            title='Damnation Alley',
            author='Roger Zelazny',
        )
        self.assertEqual(len(alley), 1)
        self.assertEqual(alley[0].status, 'Finalist')
        titles = [record.work_title for record in records]
        self.assertNotIn('Dangerous Visions', titles)
        self.assertNotIn('Analog', titles)
        self.assertNotIn('Galaxy', titles)
        self.assertNotIn('Lord of Light', titles)
        self.assertNotIn('Gonna Roll the Bones', titles)
        self.assertEqual(sum(1 for record in records if record.status == 'Winner'), 2)

    def test_straight_quoted_novella_title_does_not_use_anthology_em(self):
        records = hugo._parse_category_html(
            HTML_STRAIGHT_QUOTED_NOVELLA,
            1968,
            URL_1968,
            hugo.CATEGORY_BEST_NOVELLA,
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].work_title, 'Riders of the Purple Wage')
        self.assertEqual(records[0].work_author, 'Philip José Farmer')
        self.assertNotEqual(records[0].work_title, 'Dangerous Visions')

    def test_2020_tagged_novella_title_path(self):
        records = hugo._parse_category_html(
            HTML_2020, 2020, URL_2020, hugo.CATEGORY_BEST_NOVELLA
        )
        time_war = _find_records(
            records,
            title='This Is How You Lose the Time War',
            author='Amal El-Mohtar and Max Gladstone',
        )
        self.assertEqual(len(time_war), 1)
        self.assertEqual(time_war[0].status, 'Winner')
        self.assertEqual(time_war[0].category, 'Best Novella')
        result = hugo._to_award_result(time_war[0])
        self.assertEqual(result.award_name, 'Hugo Award')
        self.assertEqual(result.category, 'Best Novella')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'Hugo Awards')
        self.assertEqual(result.source_url, URL_2020)
        self.assertIsNone(result.notes)
        self.assertNotIn(
            'A Memory Called Empire',
            [record.work_title for record in records],
        )

    def test_2015_novella_skips_no_award_and_does_not_invent_a_winner(self):
        records = hugo._parse_category_html(
            HTML_2015, 2015, URL_2015, hugo.CATEGORY_BEST_NOVELLA
        )
        titles = [record.work_title for record in records]
        self.assertNotIn('No Award', titles)
        self.assertNotIn('The Three Body Problem', titles)
        self.assertTrue(all(record.status == 'Finalist' for record in records))
        self.assertNotIn('Winner', [record.status for record in records])
        flow = _find_records(
            records,
            title='Flow',
            author='Arlan Andrews, Sr.',
        )
        self.assertEqual(len(flow), 1)
        self.assertEqual(flow[0].status, 'Finalist')
        self.assertEqual(flow[0].category, 'Best Novella')
        helen = _find_records(
            records,
            title='The Plural of Helen of Troy',
            author='John C. Wright',
        )
        self.assertEqual(len(helen), 1)
        self.assertEqual(helen[0].status, 'Finalist')
        result = hugo._to_award_result(flow[0])
        self.assertEqual(result.category, 'Best Novella')
        self.assertEqual(result.status, 'Finalist')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_url, URL_2015)

    def test_2026_novella_finalists_do_not_invent_a_winner(self):
        records = hugo._parse_category_html(
            HTML_2026, 2026, URL_2026, hugo.CATEGORY_BEST_NOVELLA
        )
        self.assertTrue(records)
        self.assertTrue(all(record.status == 'Finalist' for record in records))
        self.assertNotIn('Winner', [record.status for record in records])
        noodle = _find_records(
            records,
            title='Automatic Noodle',
            author='Annalee Newitz',
        )
        self.assertEqual(len(noodle), 1)
        self.assertEqual(noodle[0].category, 'Best Novella')
        result = hugo._to_award_result(noodle[0])
        self.assertEqual(result.status, 'Finalist')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_url, URL_2026)
        self.assertNotIn(
            'A Drop of Corruption',
            [record.work_title for record in records],
        )

    def test_supported_categories_on_one_page_stay_isolated(self):
        records = hugo._parse_supported_categories_html(HTML_1968, 1968, URL_1968)
        novels = [record for record in records if record.category == 'Best Novel']
        novellas = [record for record in records if record.category == 'Best Novella']
        novelettes = [
            record for record in records if record.category == 'Best Novelette'
        ]
        self.assertEqual([record.work_title for record in novels], ['Lord of Light'])
        self.assertEqual(novels[0].status, 'Winner')
        self.assertEqual(
            {record.work_title for record in novellas},
            {'Riders of the Purple Wage', 'Weyr Search', 'Damnation Alley'},
        )
        self.assertEqual(
            [record.work_title for record in novelettes],
            ['Gonna Roll the Bones'],
        )
        self.assertEqual(novelettes[0].work_author, 'Fritz Leiber')
        self.assertEqual(novelettes[0].status, 'Winner')
        shorts = [
            record for record in records if record.category == 'Best Short Story'
        ]
        self.assertEqual(
            [record.work_title for record in shorts],
            ['I Have No Mouth, and I Must Scream', 'The Jigsaw Man'],
        )
        self.assertEqual(shorts[0].work_author, 'Harlan Ellison')
        self.assertEqual(shorts[0].status, 'Winner')
        self.assertEqual(shorts[1].status, 'Finalist')
        self.assertNotIn(
            'If',
            [record.work_title for record in records],
        )
        self.assertNotIn(
            'Short Fiction',
            [record.category for record in records],
        )
        mixed = hugo._parse_supported_categories_html(HTML_2025, 2025, URL_2025)
        mixed_titles = {(record.category, record.work_title) for record in mixed}
        self.assertIn(('Best Novel', 'The Tainted Cup'), mixed_titles)
        self.assertIn(('Best Novella', 'The Tusks of Extinction'), mixed_titles)
        self.assertIn(
            ('Best Novelette', 'The Four Sisters Overlooking the Sea'),
            mixed_titles,
        )
        self.assertIn(
            ('Best Short Story', 'Stitched to Skin like Family Is'),
            mixed_titles,
        )
        self.assertNotIn(
            ('Best Novel', 'The Tusks of Extinction'),
            mixed_titles,
        )
        self.assertNotIn(
            ('Best Novel', 'The Four Sisters Overlooking the Sea'),
            mixed_titles,
        )
        self.assertNotIn(
            ('Best Novella', 'The Four Sisters Overlooking the Sea'),
            mixed_titles,
        )

    def test_novella_lookup_from_cached_records(self):
        hugo._archive_records_cache = tuple(
            hugo._parse_supported_categories_html(HTML_1968, 1968, URL_1968)
        )
        try:
            results = hugo.lookup('Riders of the Purple Wage', 'Philip José Farmer')
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].category, 'Best Novella')
            self.assertEqual(results[0].status, 'Winner')
            self.assertIsNone(results[0].rank)
            novel = hugo.lookup('Lord of Light', 'Roger Zelazny')
            self.assertEqual(len(novel), 1)
            self.assertEqual(novel[0].category, 'Best Novel')
        finally:
            hugo._archive_records_cache = None

    def test_novella_ampersand_title_matching_remains_conservative(self):
        record = hugo._parse_category_html(
            HTML_2020, 2020, URL_2020, hugo.CATEGORY_BEST_NOVELLA
        )[0]
        self.assertTrue(
            hugo._record_matches(
                record,
                'This Is How You Lose the Time War',
                'Amal El-Mohtar and Max Gladstone',
            )
        )
        self.assertFalse(
            hugo._record_matches(
                record,
                'This Is How You Lose',
                'Amal El-Mohtar and Max Gladstone',
            )
        )

    def test_2014_nominating_only_ballot_note_keeps_novella_list(self):
        records = hugo._parse_supported_categories_html(
            HTML_2014_NOMINATING_NOTE,
            2014,
            'https://example.test/2014',
        )
        novels = [record for record in records if record.category == 'Best Novel']
        novellas = [record for record in records if record.category == 'Best Novella']
        self.assertEqual(novels[0].work_title, 'Ancillary Justice')
        equoid = _find_records(
            novellas, title='Equoid', author='Charles Stross'
        )
        self.assertEqual(len(equoid), 1)
        self.assertEqual(equoid[0].status, 'Winner')
        self.assertNotIn('Tor.com', [record.work_title for record in novellas])

    def test_2021_unparenthesized_ballot_notes_keep_novella_list(self):
        records = hugo._parse_category_html(
            HTML_2021_UNPAREN_BALLOT_NOTES,
            2021,
            'https://example.test/2021',
            hugo.CATEGORY_BEST_NOVELLA,
        )
        empress = _find_records(
            records,
            title='The Empress of Salt and Fortune',
            author='Nghi Vo',
        )
        self.assertEqual(len(empress), 1)
        self.assertEqual(empress[0].status, 'Winner')

    def test_2022_unparenthesized_ballot_note_keeps_novella_list(self):
        records = hugo._parse_category_html(
            HTML_2022_UNPAREN_BALLOT_NOTE,
            2022,
            'https://example.test/2022',
            hugo.CATEGORY_BEST_NOVELLA,
        )
        psalm = _find_records(
            records,
            title='A Psalm for the Wild-Built',
            author='Becky Chambers',
        )
        self.assertEqual(len(psalm), 1)
        self.assertEqual(psalm[0].status, 'Winner')

    def test_quoted_historical_novelette_does_not_use_anthology_em(self):
        records = hugo._parse_category_html(
            HTML_1968, 1968, URL_1968, hugo.CATEGORY_BEST_NOVELETTE
        )
        bones = _find_records(
            records,
            title='Gonna Roll the Bones',
            author='Fritz Leiber',
        )
        self.assertEqual(len(bones), 1)
        self.assertEqual(bones[0].status, 'Winner')
        self.assertEqual(bones[0].category, 'Best Novelette')
        self.assertEqual(bones[0].award_year, 1968)
        self.assertEqual(bones[0].source_url, URL_1968)
        result = hugo._to_award_result(bones[0])
        self.assertEqual(result.award_name, 'Hugo Award')
        self.assertEqual(result.category, 'Best Novelette')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'Hugo Awards')
        self.assertEqual(result.source_url, URL_1968)
        self.assertIsNone(result.notes)
        titles = [record.work_title for record in records]
        self.assertNotIn('Dangerous Visions', titles)
        self.assertNotIn('Lord of Light', titles)
        self.assertNotIn('Riders of the Purple Wage', titles)
        self.assertNotIn('I Have No Mouth, and I Must Scream', titles)

    def test_2010_malformed_novelette_recovers_island_without_anthology_em(self):
        records = hugo._parse_category_html(
            HTML_2010_NOVELETTE,
            2010,
            URL_2010,
            hugo.CATEGORY_BEST_NOVELETTE,
        )
        island = _find_records(
            records,
            title='The Island',
            author='Peter Watts',
        )
        self.assertEqual(len(island), 1)
        self.assertEqual(island[0].status, 'Winner')
        self.assertEqual(island[0].category, 'Best Novelette')
        self.assertEqual(island[0].award_year, 2010)
        result = hugo._to_award_result(island[0])
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_url, URL_2010)
        titles = [record.work_title for record in records]
        self.assertNotIn('The New Space Opera 2', titles)
        self.assertNotIn('Eos', titles)
        overtime = _find_records(
            records,
            title='Overtime',
            author='Charles Stross',
        )
        self.assertEqual(len(overtime), 1)
        self.assertEqual(overtime[0].status, 'Finalist')
        self.assertNotIn('Bridesicle', titles)
        self.assertNotIn('The Windup Girl', titles)
        novels = hugo._parse_best_novel_html(HTML_2010_NOVELETTE, 2010, URL_2010)
        self.assertEqual(novels[0].work_title, 'The Windup Girl')
        self.assertNotIn('The Island', [record.work_title for record in novels])

    def test_unopened_quote_without_recognized_author_is_not_recovered(self):
        records = hugo._parse_category_html(
            HTML_UNOPENED_QUOTE_WITHOUT_AUTHOR,
            2010,
            URL_2010,
            hugo.CATEGORY_BEST_NOVELETTE,
        )
        self.assertEqual(records, [])

    def test_unopened_quote_shape_is_not_recovered_as_2010_best_novel(self):
        records = hugo._parse_category_html(
            HTML_UNOPENED_QUOTE_AS_BEST_NOVEL,
            2010,
            URL_2010,
            hugo.CATEGORY_BEST_NOVEL,
        )
        titles = [record.work_title for record in records]
        self.assertNotIn('The Island', titles)
        self.assertNotIn('The New Space Opera 2', titles)
        self.assertEqual(records, [])

    def test_unopened_quote_shape_is_not_recovered_as_novelette_in_other_year(self):
        for year in (2009, 2011):
            with self.subTest(year=year):
                records = hugo._parse_category_html(
                    HTML_UNOPENED_QUOTE_NOVELETTE_ONLY,
                    year,
                    URL_2010,
                    hugo.CATEGORY_BEST_NOVELETTE,
                )
                titles = [record.work_title for record in records]
                self.assertNotIn('The Island', titles)
                self.assertNotIn('The New Space Opera 2', titles)
                self.assertEqual(records, [])

    def test_2020_tagged_novelette_title_path(self):
        records = hugo._parse_category_html(
            HTML_2020, 2020, URL_2020, hugo.CATEGORY_BEST_NOVELETTE
        )
        skin = _find_records(
            records,
            title='Emergency Skin',
            author='N.K. Jemisin',
        )
        self.assertEqual(len(skin), 1)
        self.assertEqual(skin[0].work_author, 'N.K. Jemisin')
        self.assertEqual(skin[0].status, 'Winner')
        self.assertEqual(skin[0].category, 'Best Novelette')
        result = hugo._to_award_result(skin[0])
        self.assertEqual(result.award_name, 'Hugo Award')
        self.assertEqual(result.category, 'Best Novelette')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'Hugo Awards')
        self.assertEqual(result.source_url, URL_2020)
        self.assertIsNone(result.notes)
        titles = [record.work_title for record in records]
        self.assertNotIn('Forward Collection', titles)
        self.assertNotIn('A Memory Called Empire', titles)
        self.assertNotIn('This Is How You Lose the Time War', titles)

    def test_2026_novelette_finalists_do_not_invent_a_winner(self):
        records = hugo._parse_category_html(
            HTML_2026, 2026, URL_2026, hugo.CATEGORY_BEST_NOVELETTE
        )
        self.assertTrue(records)
        self.assertTrue(all(record.status == 'Finalist' for record in records))
        self.assertNotIn('Winner', [record.status for record in records])
        kaiju = _find_records(
            records,
            title='Kaiju Agonistes',
            author='Scott Lynch',
        )
        self.assertEqual(len(kaiju), 1)
        self.assertEqual(kaiju[0].category, 'Best Novelette')
        result = hugo._to_award_result(kaiju[0])
        self.assertEqual(result.status, 'Finalist')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_url, URL_2026)
        self.assertIsNone(result.notes)
        titles = [record.work_title for record in records]
        self.assertNotIn('A Drop of Corruption', titles)
        self.assertNotIn('Automatic Noodle', titles)

    def test_novelette_lookup_from_cached_records(self):
        hugo._archive_records_cache = tuple(
            hugo._parse_supported_categories_html(HTML_1968, 1968, URL_1968)
        )
        try:
            results = hugo.lookup('Gonna Roll the Bones', 'Fritz Leiber')
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].category, 'Best Novelette')
            self.assertEqual(results[0].status, 'Winner')
            self.assertIsNone(results[0].rank)
            novella = hugo.lookup('Riders of the Purple Wage', 'Philip José Farmer')
            self.assertEqual(len(novella), 1)
            self.assertEqual(novella[0].category, 'Best Novella')
            novel = hugo.lookup('Lord of Light', 'Roger Zelazny')
            self.assertEqual(len(novel), 1)
            self.assertEqual(novel[0].category, 'Best Novel')
            short = hugo.lookup(
                'I Have No Mouth, and I Must Scream',
                'Harlan Ellison',
            )
            self.assertEqual(len(short), 1)
            self.assertEqual(short[0].category, 'Best Short Story')
            self.assertEqual(short[0].status, 'Winner')
            self.assertIsNone(short[0].rank)
        finally:
            hugo._archive_records_cache = None

    def test_novelette_ampersand_title_matching_remains_conservative(self):
        record = hugo._parse_category_html(
            HTML_2020, 2020, URL_2020, hugo.CATEGORY_BEST_NOVELETTE
        )[0]
        self.assertTrue(
            hugo._record_matches(record, 'Emergency Skin', 'N.K. Jemisin')
        )
        self.assertFalse(
            hugo._record_matches(record, 'Emergency', 'N.K. Jemisin')
        )
        time_war = hugo._parse_category_html(
            HTML_2020, 2020, URL_2020, hugo.CATEGORY_BEST_NOVELLA
        )[0]
        self.assertTrue(
            hugo._record_matches(
                time_war,
                'This Is How You Lose the Time War',
                'Amal El-Mohtar and Max Gladstone',
            )
        )
        self.assertFalse(
            hugo._record_matches(
                time_war,
                'This Is How You Lose',
                'Amal El-Mohtar and Max Gladstone',
            )
        )

    def test_year_requires_novelette_matches_official_coverage(self):
        required = {1955, 1956, 1959, 1967, 1968, 1969, 1973, 2010, 2026}
        skipped = {1957, 1958, 1960, 1966, 1970, 1971, 1972}
        for year in required:
            with self.subTest(year=year):
                self.assertTrue(hugo._year_requires_novelette(year))
        for year in skipped:
            with self.subTest(year=year):
                self.assertFalse(hugo._year_requires_novelette(year))

    def test_quoted_historical_short_story_does_not_use_magazine_em(self):
        records = hugo._parse_category_html(
            HTML_1968, 1968, URL_1968, hugo.CATEGORY_BEST_SHORT_STORY
        )
        scream = _find_records(
            records,
            title='I Have No Mouth, and I Must Scream',
            author='Harlan Ellison',
        )
        self.assertEqual(len(scream), 1)
        self.assertEqual(scream[0].status, 'Winner')
        self.assertEqual(scream[0].category, 'Best Short Story')
        self.assertEqual(scream[0].award_year, 1968)
        self.assertEqual(scream[0].source_url, URL_1968)
        result = hugo._to_award_result(scream[0])
        self.assertEqual(result.award_name, 'Hugo Award')
        self.assertEqual(result.category, 'Best Short Story')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'Hugo Awards')
        self.assertEqual(result.source_url, URL_1968)
        self.assertIsNone(result.notes)
        titles = [record.work_title for record in records]
        self.assertNotIn('If', titles)
        self.assertNotIn('Lord of Light', titles)
        self.assertNotIn('Gonna Roll the Bones', titles)
        jigsaw = _find_records(
            records,
            title='The Jigsaw Man',
            author='Larry Niven',
        )
        self.assertEqual(len(jigsaw), 1)
        self.assertEqual(jigsaw[0].status, 'Finalist')
        self.assertEqual(jigsaw[0].category, 'Best Short Story')

    def test_1973_dual_short_story_winners(self):
        records = hugo._parse_category_html(
            HTML_1973_SHORT_STORY,
            1973,
            URL_1973,
            hugo.CATEGORY_BEST_SHORT_STORY,
        )
        eurema = _find_records(
            records, title='Eurema’s Dam', author='R. A. Lafferty'
        )
        meeting = _find_records(
            records,
            title='The Meeting',
            author='Frederik Pohl and C. M. Kornbluth',
        )
        self.assertEqual(len(eurema), 1)
        self.assertEqual(eurema[0].status, 'Winner')
        self.assertEqual(eurema[0].category, 'Best Short Story')
        self.assertEqual(len(meeting), 1)
        self.assertEqual(meeting[0].status, 'Winner')
        self.assertEqual(sum(1 for record in records if record.status == 'Winner'), 2)
        self.assertNotIn('F&SF', [record.work_title for record in records])
        changed = _find_records(
            records, title='When It Changed', author='Joanna Russ'
        )
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0].status, 'Finalist')

    def test_2015_short_story_skips_no_award_and_does_not_invent_a_winner(self):
        records = hugo._parse_category_html(
            HTML_2015, 2015, URL_2015, hugo.CATEGORY_BEST_SHORT_STORY
        )
        titles = [record.work_title for record in records]
        self.assertNotIn('No Award', titles)
        self.assertTrue(all(record.status == 'Finalist' for record in records))
        self.assertNotIn('Winner', [record.status for record in records])
        totaled = _find_records(
            records, title='Totaled', author='Kary English'
        )
        self.assertEqual(len(totaled), 1)
        self.assertEqual(totaled[0].status, 'Finalist')
        self.assertEqual(totaled[0].category, 'Best Short Story')
        self.assertNotIn('Galaxy’s Edge Magazine', titles)
        self.assertNotIn("Galaxy's Edge Magazine", titles)
        result = hugo._to_award_result(totaled[0])
        self.assertEqual(result.category, 'Best Short Story')
        self.assertEqual(result.status, 'Finalist')
        self.assertIsNone(result.rank)
        self.assertNotIn('The Three Body Problem', titles)
        self.assertNotIn('Flow', titles)

    def test_2026_short_story_finalists_do_not_invent_a_winner(self):
        records = hugo._parse_category_html(
            HTML_2026, 2026, URL_2026, hugo.CATEGORY_BEST_SHORT_STORY
        )
        self.assertTrue(records)
        self.assertTrue(all(record.status == 'Finalist' for record in records))
        self.assertNotIn('Winner', [record.status for record in records])
        visions = _find_records(
            records,
            title='10 Visions of the Future; or, Self-Care for the End of Days',
            author='Samantha Mills',
        )
        self.assertEqual(len(visions), 1)
        self.assertEqual(visions[0].category, 'Best Short Story')
        result = hugo._to_award_result(visions[0])
        self.assertEqual(result.status, 'Finalist')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_url, URL_2026)
        titles = [record.work_title for record in records]
        self.assertNotIn('Uncanny Magazine', titles)
        self.assertNotIn('A Drop of Corruption', titles)
        self.assertNotIn('Kaiju Agonistes', titles)

    def test_2015_tagged_short_story_title_path(self):
        records = hugo._parse_category_html(
            HTML_2015, 2015, URL_2015, hugo.CATEGORY_BEST_SHORT_STORY
        )
        totaled = _find_records(
            records, title='Totaled', author='Kary English'
        )
        self.assertEqual(len(totaled), 1)
        self.assertEqual(totaled[0].work_title, 'Totaled')
        samurai = _find_records(
            records, title='A Single Samurai', author='Steven Diamond'
        )
        self.assertEqual(len(samurai), 1)
        self.assertNotEqual(samurai[0].work_title, 'The Baen Big Book of Monsters')

    def test_1960_short_fiction_quoted_winner_does_not_use_magazine_em(self):
        records = hugo._parse_category_html(
            HTML_1960_SHORT_FICTION,
            1960,
            URL_1960,
            hugo.CATEGORY_SHORT_FICTION,
        )
        flowers = _find_records(
            records, title='Flowers for Algernon', author='Daniel Keyes'
        )
        self.assertEqual(len(flowers), 1)
        self.assertEqual(flowers[0].status, 'Winner')
        self.assertEqual(flowers[0].category, 'Short Fiction')
        self.assertEqual(flowers[0].award_year, 1960)
        result = hugo._to_award_result(flowers[0])
        self.assertEqual(result.award_name, 'Hugo Award')
        self.assertEqual(result.category, 'Short Fiction')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'Hugo Awards')
        self.assertEqual(result.source_url, URL_1960)
        self.assertIsNone(result.notes)
        titles = [record.work_title for record in records]
        self.assertNotIn('F&SF', titles)
        self.assertNotIn('Starship Troopers', titles)
        self.assertNotIn('Best Short Story', [record.category for record in records])
        alley = _find_records(
            records, title='The Alley Man', author='Philip José Farmer'
        )
        self.assertEqual(len(alley), 1)
        self.assertEqual(alley[0].status, 'Finalist')

    def test_1962_hothouse_series_citation_is_left_unparsed(self):
        records = hugo._parse_category_html(
            HTML_1962_SHORT_FICTION,
            1962,
            URL_1962,
            hugo.CATEGORY_SHORT_FICTION,
        )
        titles = [record.work_title for record in records]
        self.assertNotIn('Hothouse', titles)
        self.assertNotIn('the “Hothouse” series', titles)
        self.assertNotIn('F&SF', titles)
        monument = _find_records(
            records, title='Monument', author='Lloyd Biggle, Jr.'
        )
        self.assertEqual(len(monument), 1)
        self.assertEqual(monument[0].status, 'Finalist')
        self.assertEqual(monument[0].category, 'Short Fiction')
        self.assertTrue(all(record.status == 'Finalist' for record in records))
        self.assertNotIn('Winner', [record.status for record in records])

    def test_1958_best_novel_or_novelette_parses_the_big_time(self):
        records = hugo._parse_category_html(
            HTML_1958,
            1958,
            URL_1958,
            hugo.CATEGORY_BEST_NOVEL_OR_NOVELETTE,
        )
        big_time = _find_records(
            records, title='The Big Time', author='Fritz Leiber'
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(len(big_time), 1)
        self.assertEqual(big_time[0].award_year, 1958)
        self.assertEqual(big_time[0].category, 'Best Novel or Novelette')
        self.assertEqual(big_time[0].status, 'Winner')
        self.assertEqual(big_time[0].source_url, URL_1958)
        result = hugo._to_award_result(big_time[0])
        self.assertEqual(result.work_title, 'The Big Time')
        self.assertEqual(result.work_author, 'Fritz Leiber')
        self.assertEqual(result.award_name, 'Hugo Award')
        self.assertEqual(result.award_year, 1958)
        self.assertEqual(result.category, 'Best Novel or Novelette')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'Hugo Awards')
        self.assertEqual(result.source_url, URL_1958)
        self.assertIsNone(result.notes)
        self.assertNotIn('Galaxy', [record.work_title for record in records])

    def test_1958_page_keeps_combined_category_and_short_story_isolated(self):
        records = hugo._parse_supported_categories_html(HTML_1958, 1958, URL_1958)
        big_time = _find_records(
            records, title='The Big Time', author='Fritz Leiber'
        )
        oysters = _find_records(
            records,
            title='Or All the Seas with Oysters',
            author='Avram Davidson',
        )
        self.assertEqual(len(big_time), 1)
        self.assertEqual(big_time[0].category, 'Best Novel or Novelette')
        self.assertEqual(big_time[0].status, 'Winner')
        self.assertEqual(len(oysters), 1)
        self.assertEqual(oysters[0].category, 'Best Short Story')
        self.assertEqual(oysters[0].status, 'Winner')
        self.assertNotIn(
            'Best Novel',
            [record.category for record in big_time],
        )
        self.assertNotIn(
            'Best Novelette',
            [record.category for record in big_time],
        )
        self.assertNotIn(
            'Best Novel or Novelette',
            [record.category for record in oysters],
        )
        self.assertEqual(
            hugo._parse_category_html(
                HTML_1958, 1958, URL_1958, hugo.CATEGORY_BEST_NOVEL
            ),
            [],
        )
        self.assertEqual(
            hugo._parse_category_html(
                HTML_1958, 1958, URL_1958, hugo.CATEGORY_BEST_NOVELETTE
            ),
            [],
        )
        self.assertEqual(hugo._parse_best_novel_html(HTML_1958, 1958, URL_1958), [])
        titles = [record.work_title for record in records]
        self.assertNotIn('Galaxy', titles)
        self.assertNotIn('Galaxy Science Fiction', titles)

    def test_1958_lookup_returns_exactly_one_combined_category_result(self):
        hugo._archive_records_cache = tuple(
            hugo._parse_supported_categories_html(HTML_1958, 1958, URL_1958)
        )
        try:
            results = hugo.lookup('The Big Time', 'Fritz Leiber')
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].category, 'Best Novel or Novelette')
            self.assertEqual(results[0].status, 'Winner')
            self.assertEqual(results[0].award_year, 1958)
            self.assertIsNone(results[0].rank)
            short = hugo.lookup('Or All the Seas with Oysters', 'Avram Davidson')
            self.assertEqual(len(short), 1)
            self.assertEqual(short[0].category, 'Best Short Story')
        finally:
            hugo._archive_records_cache = None

    def test_year_requires_novel_or_novelette_is_1958_only(self):
        self.assertTrue(hugo._year_requires_novel_or_novelette(1958))
        for year in (1957, 1959, 1960, 1966, 1968, 2020, 2026):
            with self.subTest(year=year):
                self.assertFalse(hugo._year_requires_novel_or_novelette(year))
        self.assertTrue(hugo._year_requires_best_novel(1953))
        self.assertTrue(hugo._year_requires_best_novel(1955))
        self.assertTrue(hugo._year_requires_best_novel(1956))
        self.assertFalse(hugo._year_requires_best_novel(1957))
        self.assertFalse(hugo._year_requires_best_novel(1958))
        self.assertTrue(hugo._year_requires_best_novel(1959))
        self.assertTrue(hugo._year_requires_best_novel(1960))
        self.assertTrue(hugo._year_requires_best_novel(1966))
        self.assertTrue(hugo._year_requires_best_novel(2026))

    def test_unopened_quote_shape_is_not_recovered_as_short_story_or_fiction(self):
        short = hugo._parse_category_html(
            HTML_UNOPENED_QUOTE_AS_SHORT_STORY,
            2010,
            URL_2010,
            hugo.CATEGORY_BEST_SHORT_STORY,
        )
        fiction = hugo._parse_category_html(
            HTML_UNOPENED_QUOTE_AS_SHORT_FICTION,
            1962,
            URL_1962,
            hugo.CATEGORY_SHORT_FICTION,
        )
        for records in (short, fiction):
            titles = [record.work_title for record in records]
            self.assertNotIn('The Island', titles)
            self.assertNotIn('The New Space Opera 2', titles)
            self.assertEqual(records, [])

    def test_year_requires_short_story_matches_official_coverage(self):
        required = {1955, 1956, 1958, 1959, 1967, 1968, 1973, 2015, 2026}
        skipped = {1957, 1960, 1966}
        for year in required:
            with self.subTest(year=year):
                self.assertTrue(hugo._year_requires_short_story(year))
        for year in skipped:
            with self.subTest(year=year):
                self.assertFalse(hugo._year_requires_short_story(year))

    def test_year_requires_short_fiction_matches_official_coverage(self):
        required = {1960, 1962, 1966}
        skipped = {1959, 1967, 1968, 2020}
        for year in required:
            with self.subTest(year=year):
                self.assertTrue(hugo._year_requires_short_fiction(year))
        for year in skipped:
            with self.subTest(year=year):
                self.assertFalse(hugo._year_requires_short_fiction(year))


class HugoArchiveHelperTests(unittest.TestCase):
    def setUp(self):
        hugo._archive_records_cache = None

    def tearDown(self):
        hugo._archive_records_cache = None

    def test_regular_year_pages_are_kept_and_others_filtered(self):
        items = [
            _archive_item('1966 Hugo Awards', URL_1966, HTML_1966, '1966-hugo-awards'),
            _archive_item(
                '1954 Retro-Hugo Awards',
                'https://www.thehugoawards.org/hugo-history/1954-retro-hugo-awards/',
                HTML_RETRO,
                '1954-retro-hugo-awards',
            ),
            _archive_item(
                'A Short History of the Hugo Awards Process',
                'https://www.thehugoawards.org/hugo-history/a-short-history-of-the-hugo-awards-process/',
                HTML_RETRO,
                'a-short-history-of-the-hugo-awards-process',
            ),
            _archive_item(
                '1985 Hugo Awards',
                URL_1985,
                HTML_1985,
                '1995-hugo-awards-2',
            ),
        ]
        records = hugo._records_from_archive_items(items)
        years = {record.award_year for record in records}
        self.assertEqual(years, {1966, 1985})
        neuromancer = _find_records(
            records, title='Neuromancer', author='William Gibson'
        )
        self.assertEqual(len(neuromancer), 1)
        self.assertEqual(neuromancer[0].award_year, 1985)
        self.assertEqual(neuromancer[0].source_url, URL_1985)
        self.assertNotIn(
            'Should Not Appear',
            [record.work_title for record in records],
        )

    def test_invalid_payload_raises_and_does_not_cache(self):
        cases = [
            (500, {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}, '[]'),
            (200, {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}, '{'),
            (200, {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}, '{}'),
            (200, {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}, '[]'),
            (
                200,
                {'X-WP-Total': '2', 'X-WP-TotalPages': '1'},
                json.dumps([_archive_item('1966 Hugo Awards', URL_1966, HTML_1966)]),
            ),
            (
                200,
                {'X-WP-Total': '1', 'X-WP-TotalPages': '2'},
                json.dumps([_archive_item('1966 Hugo Awards', URL_1966, HTML_1966)]),
            ),
            (
                200,
                {'X-WP-Total': '1', 'X-WP-TotalPages': '1'},
                json.dumps([{'title': {'rendered': '1966 Hugo Awards'}, 'link': URL_1966}]),
            ),
        ]
        for status, headers, body in cases:
            with self.subTest(status=status, body=body[:40]):
                hugo._archive_records_cache = None
                with patch.object(
                    hugo, '_fetch_archive_response', return_value=(status, headers, body)
                ):
                    with self.assertRaises(hugo.HugoSourceError):
                        hugo._get_archive_records()
                self.assertIsNone(hugo._archive_records_cache)

    def test_empty_parsed_archive_raises_and_does_not_cache(self):
        body = json.dumps(
            [
                _archive_item(
                    '1959 Hugo Awards',
                    'https://www.thehugoawards.org/hugo-history/1959-hugo-awards/',
                    HTML_NO_SUPPORTED_WRITTEN_WORKS,
                    '1959-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            with self.assertRaises(hugo.HugoSourceError) as ctx:
                hugo._get_archive_records()
        self.assertIsNone(hugo._archive_records_cache)
        self.assertIn(
            'no Best Novel records could be parsed',
            str(ctx.exception),
        )

    def test_1958_archive_with_combined_category_succeeds(self):
        body = json.dumps(
            [
                _archive_item(
                    '1958 Hugo Awards',
                    URL_1958,
                    HTML_1958,
                    '1958-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            records = hugo._get_archive_records()
        categories = {record.category for record in records}
        self.assertEqual(
            categories,
            {'Best Novel or Novelette', 'Best Short Story'},
        )
        big_time = _find_records(
            records, title='The Big Time', author='Fritz Leiber'
        )
        self.assertEqual(len(big_time), 1)
        self.assertEqual(big_time[0].category, 'Best Novel or Novelette')
        self.assertNotIn('Best Novel', categories)
        self.assertNotIn('Best Novelette', categories)

    def test_1958_archive_missing_combined_category_fails_closed(self):
        body = json.dumps(
            [
                _archive_item(
                    '1958 Hugo Awards',
                    URL_1958,
                    HTML_1958_SHORT_STORY_ONLY,
                    '1958-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            with self.assertRaises(hugo.HugoSourceError) as ctx:
                hugo._get_archive_records()
        self.assertIsNone(hugo._archive_records_cache)
        self.assertIn(
            'no Best Novel or Novelette records could be parsed',
            str(ctx.exception),
        )

    def test_1957_archive_does_not_require_best_novel_or_combined_category(self):
        body = json.dumps(
            [
                _archive_item(
                    '1957 Hugo Awards',
                    'https://www.thehugoawards.org/hugo-history/1957-hugo-awards/',
                    HTML_1957,
                    '1957-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            records = hugo._get_archive_records()
        categories = {record.category for record in records}
        self.assertEqual(categories, set())
        self.assertNotIn('Best Novel', [record.category for record in records])
        self.assertNotIn('Best Novel or Novelette', categories)

    def test_1959_archive_does_not_require_novel_or_novelette(self):
        body = json.dumps(
            [
                _archive_item(
                    '1959 Hugo Awards',
                    'https://www.thehugoawards.org/hugo-history/1959-hugo-awards/',
                    HTML_1959,
                    '1959-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            records = hugo._get_archive_records()
        categories = {record.category for record in records}
        self.assertEqual(
            categories,
            {'Best Novel', 'Best Novelette', 'Best Short Story'},
        )
        self.assertNotIn('Best Novel or Novelette', categories)

    def test_novel_only_post_1968_archive_fails_closed_without_novella(self):
        body = json.dumps(
            [
                _archive_item(
                    '2020 Hugo Awards',
                    URL_2020,
                    HTML_NOVEL_ONLY_2020,
                    '2020-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            with self.assertRaises(hugo.HugoSourceError) as ctx:
                hugo._get_archive_records()
        self.assertIsNone(hugo._archive_records_cache)
        self.assertIn('no Best Novella records could be parsed', str(ctx.exception))

    def test_novel_and_novella_only_expected_year_fails_closed_without_novelette(self):
        body = json.dumps(
            [
                _archive_item(
                    '2020 Hugo Awards',
                    URL_2020,
                    HTML_NOVEL_AND_NOVELLA_ONLY_2020,
                    '2020-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            with self.assertRaises(hugo.HugoSourceError) as ctx:
                hugo._get_archive_records()
        self.assertIsNone(hugo._archive_records_cache)
        self.assertIn(
            'no Best Novelette records could be parsed',
            str(ctx.exception),
        )

    def test_intentional_1971_novelette_gap_does_not_fail_closed(self):
        body = json.dumps(
            [
                _archive_item(
                    '1971 Hugo Awards',
                    'https://www.thehugoawards.org/hugo-history/1971-hugo-awards/',
                    HTML_1971_NOVELETTE_GAP,
                    '1971-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            records = hugo._get_archive_records()
        categories = {record.category for record in records}
        self.assertEqual(categories, {'Best Novel', 'Best Novella', 'Best Short Story'})
        slow = _find_records(
            records, title='Slow Sculpture', author='Theodore Sturgeon'
        )
        self.assertEqual(len(slow), 1)
        self.assertEqual(slow[0].category, 'Best Short Story')
        self.assertNotIn('Best Novelette', [record.category for record in records])

    def test_1966_short_fiction_year_does_not_require_novelette(self):
        body = json.dumps(
            [
                _archive_item(
                    '1966 Hugo Awards',
                    URL_1966,
                    HTML_1966,
                    '1966-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            records = hugo._get_archive_records()
        categories = {record.category for record in records}
        self.assertEqual(categories, {'Best Novel', 'Short Fiction'})
        repent = _find_records(
            records,
            title='‘Repent, Harlequin!’ Said the Ticktockman',
            author='Harlan Ellison',
        )
        self.assertEqual(len(repent), 1)
        self.assertEqual(repent[0].category, 'Short Fiction')
        self.assertEqual(repent[0].status, 'Winner')
        self.assertNotIn(
            'Best Short Story',
            [record.category for record in records],
        )
        self.assertNotIn(
            'Best Novelette',
            [record.category for record in records],
        )
        self.assertNotIn('Galaxy', [record.work_title for record in records])

    def test_expected_short_story_year_fails_closed_without_short_story(self):
        body = json.dumps(
            [
                _archive_item(
                    '2020 Hugo Awards',
                    URL_2020,
                    HTML_NOVEL_NOVELLA_NOVELETTE_ONLY_2020,
                    '2020-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            with self.assertRaises(hugo.HugoSourceError) as ctx:
                hugo._get_archive_records()
        self.assertIsNone(hugo._archive_records_cache)
        self.assertIn(
            'no Best Short Story records could be parsed',
            str(ctx.exception),
        )

    def test_expected_short_fiction_year_fails_closed_without_short_fiction(self):
        body = json.dumps(
            [
                _archive_item(
                    '1966 Hugo Awards',
                    URL_1966,
                    HTML_1966_NOVEL_ONLY,
                    '1966-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            with self.assertRaises(hugo.HugoSourceError) as ctx:
                hugo._get_archive_records()
        self.assertIsNone(hugo._archive_records_cache)
        self.assertIn(
            'no Short Fiction records could be parsed',
            str(ctx.exception),
        )

    def test_1967_requires_short_story_but_not_short_fiction(self):
        body = json.dumps(
            [
                _archive_item(
                    '1967 Hugo Awards',
                    URL_1967,
                    HTML_1967,
                    '1967-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            records = hugo._get_archive_records()
        categories = {record.category for record in records}
        self.assertEqual(
            categories,
            {'Best Novel', 'Best Novelette', 'Best Short Story'},
        )
        neutron = _find_records(
            records, title='Neutron Star', author='Larry Niven'
        )
        self.assertEqual(len(neutron), 1)
        self.assertEqual(neutron[0].category, 'Best Short Story')
        self.assertNotIn('Short Fiction', categories)

    def test_1962_short_fiction_archive_succeeds_without_hothouse_row(self):
        body = json.dumps(
            [
                _archive_item(
                    '1962 Hugo Awards',
                    URL_1962,
                    HTML_1962_SHORT_FICTION,
                    '1962-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            records = hugo._get_archive_records()
        categories = {record.category for record in records}
        self.assertIn('Short Fiction', categories)
        self.assertNotIn('Best Short Story', categories)
        self.assertNotIn('Hothouse', [record.work_title for record in records])
        monument = _find_records(
            records, title='Monument', author='Lloyd Biggle, Jr.'
        )
        self.assertEqual(len(monument), 1)

    def test_archive_with_novel_novella_and_novelette_is_cached(self):
        body = json.dumps(
            [
                _archive_item(
                    '2020 Hugo Awards',
                    URL_2020,
                    HTML_2020,
                    '2020-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            records = hugo._get_archive_records()
        categories = {record.category for record in records}
        self.assertEqual(
            categories,
            {
                'Best Novel',
                'Best Novella',
                'Best Novelette',
                'Best Short Story',
                'Best Series',
            },
        )
        time_war = _find_records(
            records,
            title='This Is How You Lose the Time War',
            author='Amal El-Mohtar and Max Gladstone',
        )
        self.assertEqual(len(time_war), 1)
        self.assertEqual(time_war[0].category, 'Best Novella')
        skin = _find_records(
            records,
            title='Emergency Skin',
            author='N.K. Jemisin',
        )
        self.assertEqual(len(skin), 1)
        self.assertEqual(skin[0].category, 'Best Novelette')
        last_i_may_know = _find_records(
            records,
            title='As the Last I May Know',
            author='S.L. Huang',
        )
        self.assertEqual(len(last_i_may_know), 1)
        self.assertEqual(last_i_may_know[0].category, 'Best Short Story')
        self.assertIs(hugo._get_archive_records(), records)

    def test_lookup_uses_cached_parsed_records(self):
        records = hugo._parse_best_novel_html(HTML_1966, 1966, URL_1966)
        hugo._archive_records_cache = tuple(records)
        results = hugo.lookup('This Immortal', 'Roger Zelazny')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].award_year, 1966)
        self.assertTrue('Call Me Conrad' in results[0].work_title)


if __name__ == '__main__':
    unittest.main()
