"""Offline unittest coverage for the SFADB Locus Awards source."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from awards.engine import _lookup_awards_from_sources
from awards.qualifier import QualificationDecision, qualify_award_result
from awards.source_registry import AwardSource
from awards.sources import locus

URL_1984 = 'https://www.sfadb.com/Locus_Awards_1984'
URL_1987 = 'https://www.sfadb.com/Locus_Awards_1987'
URL_1990 = 'https://www.sfadb.com/Locus_Awards_1990'
URL_1971 = 'https://www.sfadb.com/Locus_Awards_1971'
URL_1974 = 'https://www.sfadb.com/Locus_Awards_1974'
URL_1975 = 'https://www.sfadb.com/Locus_Awards_1975'
URL_1979 = 'https://www.sfadb.com/Locus_Awards_1979'
URL_1999 = 'https://www.sfadb.com/Locus_Awards_1999'
URL_2008 = 'https://www.sfadb.com/Locus_Awards_2008'
URL_2009 = 'https://www.sfadb.com/Locus_Awards_2009'
URL_2010 = 'https://www.sfadb.com/Locus_Awards_2010'
URL_2017 = 'https://www.sfadb.com/Locus_Awards_2017'
URL_2018 = 'https://www.sfadb.com/Locus_Awards_2018'
URL_2020 = 'https://www.sfadb.com/Locus_Awards_2020'
URL_2024 = 'https://www.sfadb.com/Locus_Awards_2024'
URL_2025 = 'https://www.sfadb.com/Locus_Awards_2025'
URL_2026 = 'https://www.sfadb.com/Locus_Awards_2026'
URL_SIMMONS = 'https://www.sfadb.com/Dan_Simmons'
URL_CHERRYH = 'https://www.sfadb.com/C_J_Cherryh'
URL_HUANG = 'https://www.sfadb.com/S_L_Huang'
URL_ELMOHTAR = 'https://www.sfadb.com/Amal_El-Mohtar'
URL_ELLISON = 'https://www.sfadb.com/Harlan_Ellison'
URL_CLARKE = 'https://www.sfadb.com/Susanna_Clarke'
URL_EKLUND = 'https://www.sfadb.com/Gordon_Eklund'
URL_CHIANG = 'https://www.sfadb.com/Ted_Chiang'
URL_GIBSON = 'https://www.sfadb.com/William_Gibson'
URL_DAVIDSON = 'https://www.sfadb.com/Avram_Davidson'
URL_SILVERBERG = 'https://www.sfadb.com/Robert_Silverberg'


def _author_page(name: str, rows: str) -> str:
    return f"""
<html><head><title>sfadb : {name} Awards</title></head>
<body>
<div class="pagetitle">{name}</div>
<div class="awardlistingsectionheader">— Locus Awards and Poll — </div>
<div class="entryblock2">
<div class="titleleft"><a href="Locus_Awards">Locus Awards</a></div>
{rows}
</div>
<div class="awardlistingsectionheader">— Hugo Awards — </div>
<div class="titlemid"><b>Unrelated Hugo Work</b> — novel — winner</div>
</body></html>
"""


def _entry(year: int, title: str, category: str, place_html: str) -> str:
    return f"""
<div class="dateleftindent"><a href="Locus_Awards_{year}">{year}</a>: </div>
<div class="titlemid"><b>{title}</b> ({year} publisher)
 — {category} — {place_html}</div>
"""


_MUSE_OF_FIRE_DISCOVERY = """
<div class="dateleftindent"><a href="Locus_Awards_2008">2008</a>: </div>
<div class="titlemid">&#8220;Muse of Fire &#8221; (<b>The New Space Opera</b>)
 — novella — 5th place</div>
"""

HTML_SIMMONS = _author_page(
    'Dan Simmons',
    _entry(2010, 'Drood', 'fantasy novel', '3rd place')
    + _entry(1990, 'Hyperion', 'sf novel', '<span class="win">winner</span>')
    + _entry(1990, 'Phases of Gravity', 'sf novel', '9th place')
    + _entry(1990, 'Carrion Comfort', 'horror novel', '<span class="win">winner</span>')
    + _MUSE_OF_FIRE_DISCOVERY,
)

HTML_CHERRYH_LIVE_SHAPE = """
<html><body>
<div class="pagetitle">C. J. Cherryh</div>
<div class="awardlistingsectionheader">— Locus Awards and Poll — </div>
<div class="dateleftindent"><a href="Locus_Awards_1990">1990</a>: </div>
<div class="titlemid"><b>Rimrunners</b>   (Warner)
sf novel — 2nd place</div>
</body></html>
"""


HTML_EFFINGER = _author_page(
    'George Alec Effinger',
    _entry(1990, 'A Fire in the Sun', 'sf novel', '5th place'),
)

HTML_ANDERSON = _author_page(
    'Poul Anderson',
    _entry(1990, 'The Boat of a Million Years', 'sf novel', '6th place')
    + _entry(1984, 'Hoka!', 'collection', '6th place'),
)

HTML_WELLS = _author_page(
    'Martha Wells',
    _entry(2024, 'System Collapse', 'sf novel', '<span class="win">winner</span>'),
)

HTML_WILLIS = _author_page(
    'Connie Willis',
    _entry(2024, 'The Road to Roswell', 'sf novel', '5th place'),
)

HTML_TCHAIKOVSKY = _author_page(
    'Adrian Tchaikovsky',
    _entry(2024, 'Lords of Uncreation', 'sf novel', '6th place'),
)

HTML_OKORAFOR = _author_page(
    'Nnedi Okorafor',
    _entry(2026, 'Death of the Author', 'sf novel', '<span class="win">winner</span>'),
)

HTML_BEAR = _author_page(
    'Elizabeth Bear',
    _entry(2026, 'The Folded Sky', 'sf novel', '4th place'),
)

HTML_SCALZI = _author_page(
    'John Scalzi',
    _entry(2026, 'The Shattering Peace', 'sf novel', '5th place')
    + _entry(2018, 'The Collapsing Empire', 'sf novel', '<span class="win">winner</span>'),
)

HTML_LIU = _author_page(
    'Ken Liu',
    _entry(2026, 'All That We See or Seem', 'sf novel', '6th place'),
)

HTML_KINGFISHER = _author_page(
    'T. Kingfisher',
    _entry(2026, 'Hemlock &amp; Silver', 'fantasy novel', '3rd place (tie)'),
)

HTML_KUANG = _author_page(
    'R. F. Kuang',
    _entry(2026, 'Katabasis', 'fantasy novel', '3rd place (tie)'),
)

HTML_BENNETT = _author_page(
    'Robert Jackson Bennett',
    _entry(2026, 'A Drop of Corruption', 'fantasy novel', '5th place'),
)

HTML_NIVEN = _author_page(
    'Larry Niven',
    _entry(1971, 'Ringworld', 'novel', '<span class="win">winner</span>'),
)

HTML_MCINTYRE = _author_page(
    'Vonda N. McIntyre',
    _entry(1979, 'Dreamsnake', 'novel', '<span class="win">winner</span>'),
)

_RIVER_JUDGE_DISCOVERY = """
<div class="dateleftindent"><a href="Locus_Awards_2025">2025</a>: </div>
<div class="titlemid">&#8220;The River Judge&#8221; (Reactor 6 mar 2024)
 &#0151; novelette &#0151; 4th place</div>
"""

HTML_HUANG = _author_page('S. L. Huang', _RIVER_JUDGE_DISCOVERY)

_SEASONS_DISCOVERY = """
<div class="dateleftindent"><a href="Locus_Awards_2017">2017</a>: </div>
<div class="titlemid">&#8220;Seasons of Glass and Iron&#8221; (<b>The Starlit Wood</b>)
short story &#0151; <span class="win">winner</span></div>
"""

HTML_ELMOHTAR = _author_page('Amal El-Mohtar', _SEASONS_DISCOVERY)

_DEATHBIRD_DISCOVERY = """
<div class="dateleftindent"><a href="Locus_Awards_1974">1974</a>: </div>
<div class="titlemid">&#8220;The Deathbird &#8221; (<i>F&amp;SF</i> Mar 1973)
 &#0151; short fiction &#0151; <span class="win">winner</span></div>
"""

HTML_ELLISON = _author_page('Harlan Ellison', _DEATHBIRD_DISCOVERY)

HTML_CLARKE = _author_page(
    'Susanna Clarke',
    _entry(2025, 'The Wood at Midwinter', 'short story', '6th place'),
)

_STARS_ARE_GODS_DISCOVERY = """
<div class="dateleftindent"><a href="Locus_Awards_1975">1975</a>: </div>
<div class="titlemid">&#8220;If the Stars Are Gods&#8221; (<b>Universe 4</b>)
 &#0151; novelette &#0151; 8th place</div>
"""

HTML_EKLUND = _author_page('Gordon Eklund', _STARS_ARE_GODS_DISCOVERY)

HTML_NO_LOCUS = """
<html><body>
<div class="pagetitle">Dan Simmons</div>
<div class="awardlistingsectionheader">— Hugo Awards — </div>
</body></html>
"""

HTML_MALFORMED_LOCUS = """
<html><body>
<div class="pagetitle">Dan Simmons</div>
<div class="awardlistingsectionheader">— Locus Awards and Poll — </div>
<div class="dateleftindent"><a href="Locus_Awards_1990">1990</a>: </div>
</body></html>
"""

HTML_WRONG_PERSON = """
<html><body>
<div class="pagetitle">Someone Else</div>
<div class="awardlistingsectionheader">— Locus Awards and Poll — </div>
</body></html>
"""

HTML_1990 = """
<div class="categoryblock">
<div class="category">Sf Novel</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> <b>Hyperion</b>, <a href="Dan_Simmons">Dan Simmons</a> (Doubleday Foundation)</li>
<li value="2"> <b>Rimrunners</b>, <a href="C_J_Cherryh">C. J. Cherryh</a> (Warner)</li>
<li value="3"> <b>Grass</b>, <a href="Sheri_S_Tepper">Sheri S. Tepper</a> (Doubleday Foundation)</li>
<li value="4"> <b>Tides of Light</b>, <a href="Gregory_Benford">Gregory Benford</a> (Bantam Spectra)</li>
<li value="5"> <b>A Fire in the Sun</b>, <a href="George_Alec_Effinger">George Alec Effinger</a> (Doubleday Foundation)</li>
<li value="6"> <b>The Boat of a Million Years</b>, <a href="Poul_Anderson">Poul Anderson</a> (Tor)</li>
<li value="7"> <b>Rama II</b>, <a href="Arthur_C_Clarke">Arthur C. Clarke</a> &amp; <a href="Gentry_Lee">Gentry Lee</a> (Bantam Spectra)</li>
</ol>
</div>
<div class="categoryblock">
<div class="category">Horror Novel</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> <b>Carrion Comfort</b>, <a href="Dan_Simmons">Dan Simmons</a> (Dark Harvest)</li>
</ol>
</div>
<div class="categoryblock">
<div class="category">Novella</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> <b>The Father of Stones</b>, <a href="Lucius_Shepard">Lucius Shepard</a></li>
</ol>
</div>
"""

HTML_1971 = """
<div class="categoryblock">
<div class="category">Novel</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> <b>Ringworld</b>, <a href="Larry_Niven">Larry Niven</a> (Ballantine)</li>
<li value="2"> (tie): <b>Tower of Glass</b>, <a href="Robert_Silverberg">Robert Silverberg</a> (Scribner's)</li>
<li value="2"> (tie): <b>The Year of the Quiet Sun</b>, <a href="Wilson_Tucker">Wilson Tucker</a> (Ace)</li>
<li value="4"> <b>And Chaos Died</b>, <a href="Joanna_Russ">Joanna Russ</a> (Ace)</li>
<li value="5"> (tie): <b>Downward to the Earth</b>, <a href="Robert_Silverberg">Robert Silverberg</a></li>
<li value="5"> (tie): <b>Fourth Mansions</b>, <a href="R_A_Lafferty">R. A. Lafferty</a> (Ace)</li>
<li value="7"> <b>Tau Zero</b>, <a href="Poul_Anderson">Poul Anderson</a> (Doubleday)</li>
</ol>
</div>
"""

HTML_1979 = """
<div class="categoryblock">
<div class="category">Novel</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> <b>Dreamsnake</b>, <a href="Vonda_N_McIntyre">Vonda N. McIntyre</a> (Houghton Mifflin)</li>
<li value="2"> <b>Blind Voices</b>, <a href="Tom_Reamy">Tom Reamy</a> (Berkley Putnam)</li>
</ol>
</div>
"""

HTML_2008 = """
<div class="categoryblock">
<div class="category">Novella</div>
<ol>
<li value="5"> &#8220;Muse of Fire&#8221;, <a href="Dan_Simmons">Dan Simmons</a> (<b>The New Space Opera</b>)</li>
</ol>
</div>
"""

HTML_1974 = """
<div class="categoryblock">
<div class="category">Short Fiction</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> &#8220;The Deathbird&#8221;, <a href="Harlan_Ellison">Harlan Ellison</a> (<i>F&amp;SF</i> Mar 1973)</li>
</ol>
</div>
<div class="categoryblock">
<div class="category">Novella</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> &#8220;The Death of Doctor Island&#8221;, <a href="Gene_Wolfe">Gene Wolfe</a> (<b>Universe 3</b>)</li>
</ol>
</div>
"""

HTML_1975_NOVELETTE = """
<div class="categoryblock">
<div class="category">Novelette</div>
<ol>
<li value="8"> &#8220;If the Stars Are Gods&#8221;, <a href="Gordon_Eklund">Gordon Eklund</a> &amp; <a href="Gregory_Benford">Gregory Benford</a> (<b>Universe 4</b>)</li>
</ol>
</div>
"""

HTML_2017 = """
<div class="categoryblock">
<div class="category">Short Story</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> &#8220;Seasons of Glass and Iron&#8221;, <a href="Amal_El-Mohtar">Amal El-Mohtar</a> (<b>The Starlit Wood</b>)</li>
</ol>
</div>
"""

HTML_2025 = """
<div class="categoryblock">
<div class="category">Novelette</div>
<ol>
<li value="4"> &#8220;The River Judge&#8221;, <a href="S_L_Huang">S. L. Huang</a> (Reactor 6 mar 2024)</li>
</ol>
</div>
<div class="categoryblock">
<div class="category">Short Story</div>
<ol>
<li value="6"> <b>The Wood at Midwinter</b>, <a href="Susanna_Clarke">Susanna Clarke</a> (Bloomsbury)</li>
</ol>
</div>
"""

HTML_FINALIST_PREFIX = """
<div class="categoryblock">
<div class="category">Novelette</div>
<ol>
<li value="2"> Finalist: &#8220;Some Story&#8221;, <a href="Test_Author">Test Author</a> (<b>Some Anthology</b>)</li>
</ol>
</div>
"""

HTML_SHORT_OVERLAP_ANNUAL = """
<div class="categoryblock">
<div class="category">Novelette</div>
<ol>
<li value="3"> &#8220;Same Short Book&#8221;, <a href="Short_Overlap_Author">Short Overlap Author</a> (Mag)</li>
</ol>
</div>
<div class="categoryblock">
<div class="category">Short Story</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> &#8220;Same Short Book&#8221;, <a href="Short_Overlap_Author">Short Overlap Author</a> (Mag)</li>
</ol>
</div>
"""

HTML_SHORT_OVERLAP_AUTHOR = _author_page(
    'Short Overlap Author',
    """
<div class="dateleftindent"><a href="Locus_Awards_1992">1992</a>: </div>
<div class="titlemid">&#8220;Same Short Book&#8221; (Mag)
 &#0151; novelette &#0151; 3rd place</div>
<div class="dateleftindent"><a href="Locus_Awards_1992">1992</a>: </div>
<div class="titlemid">&#8220;Same Short Book&#8221; (Mag)
 &#0151; short story &#0151; <span class="win">winner</span></div>
""",
)

_EXHALATION_COLLECTION_DISCOVERY = """
<div class="dateleftindent">
    <a href="Locus_Awards_2020">2020</a>:
</div>
<div class="titlemid">
    <b>Exhalation</b> (Knopf; Picador)
    collection &#0151; <span class="win">winner</span>
</div>
"""

_EXHALATION_SHORT_STORY_DISCOVERY = """
<div class="dateleftindent"><a href="Locus_Awards_2009">2009</a>: </div>
<div class="titlemid">&#8220;Exhalation&#8221; (<i>F&amp;SF</i>)
 &#0151; short story &#0151; 2nd place</div>
"""

HTML_CHIANG = _author_page('Ted Chiang', _EXHALATION_COLLECTION_DISCOVERY)

HTML_CHIANG_CROSS = _author_page(
    'Ted Chiang',
    _EXHALATION_COLLECTION_DISCOVERY + _EXHALATION_SHORT_STORY_DISCOVERY,
)

HTML_GIBSON = _author_page(
    'William Gibson',
    """
<div class="dateleftindent"><a href="Locus_Awards_1987">1987</a>:</div>
<div class="titlemid"><b>Burning Chrome</b> (Arbor House)
collection &#0151; 2nd place</div>
""",
)

_TREASURY_COLLECTION_DISCOVERY = """
<div class="dateleftindent"><a href="Locus_Awards_1999">1999</a>:</div>
<div class="titlemid"><b>The Avram Davidson Treasury</b> (Tor)
collection &#0151; <span class="win">winner</span></div>
"""

HTML_DAVIDSON = _author_page('Avram Davidson', _TREASURY_COLLECTION_DISCOVERY)

HTML_SILVERBERG = _author_page(
    'Robert Silverberg',
    _TREASURY_COLLECTION_DISCOVERY,
)

HTML_2020_COLLECTION = """
<div class="categoryblock">
<div class="category">Collection</div>
<ol>
<li value="1">
    <span class="winner">Winner:</span>
    <b>Exhalation</b>,
    <a href="Ted_Chiang">Ted Chiang</a>
    (Knopf; Picador)
</li>
</ol>
</div>
"""

HTML_2009_EXHALATION_STORY = """
<div class="categoryblock">
<div class="category">Short Story</div>
<ol>
<li value="2"> &#8220;Exhalation&#8221;, <a href="Ted_Chiang">Ted Chiang</a> (<i>F&amp;SF</i>)</li>
</ol>
</div>
"""

HTML_1987_COLLECTION = """
<div class="categoryblock">
<div class="category">Collection</div>
<ol>
<li value="2">
    <b>Burning Chrome</b>,
    <a href="William_Gibson">William Gibson</a>
    (Arbor House)
</li>
</ol>
</div>
"""

HTML_1999_COLLECTION = """
<div class="categoryblock">
<div class="category">Collection</div>
<ol>
<li value="1">
    <span class="winner">Winner:</span>
    <b>The Avram Davidson Treasury</b>,
    <a href="Avram_Davidson">Avram Davidson</a>,
    edited by
    <a href="Robert_Silverberg">Robert Silverberg</a>
    &
    <a href="Grania_Davis">Grania Davis</a>
    (Tor)
</li>
</ol>
</div>
"""

HTML_1984_COLLECTION = """
<div class="categoryblock">
<div class="category">Collection</div>
<ol>
<li value="6">
    <b>Hoka!</b>,
    <a href="Poul_Anderson">Poul Anderson</a>
    &
    <a href="Gordon_R_Dickson">Gordon R. Dickson</a>
    (...)
</li>
</ol>
</div>
"""

HTML_WOLFE_AKA_COLLECTION = """
<div class="categoryblock">
<div class="category">Collection</div>
<ol>
<li value="2">
    <b>The Best of Gene Wolfe</b>
    (aka <b>The Very Best of Gene Wolfe</b>),
    <a href="Gene_Wolfe">Gene Wolfe</a>
    (Tor)
</li>
</ol>
</div>
"""

HTML_2018 = """
<div class="categoryblock">
<div class="category">Sf Novel</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> <b>The Collapsing Empire</b>, <a href="John_Scalzi">John Scalzi</a> (Tor US; Tor UK)</li>
<li value="2"> <b>Provenance</b>, <a href="Ann_Leckie">Ann Leckie</a> (Orbit)</li>
</ol>
</div>
"""

HTML_2024 = """
<div class="categoryblock">
<div class="category">Sf Novel</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> <b>System Collapse</b>, <a href="Martha_Wells">Martha Wells</a> (Tordotcom)</li>
<li value="2"> <b>Starter Villain</b>, <a href="John_Scalzi">John Scalzi</a> (Tor)</li>
<li value="3"> <b>Translation State</b>, <a href="Ann_Leckie">Ann Leckie</a> (Orbit)</li>
<li value="4"> <b>The Terraformers</b>, <a href="Annalee_Newitz">Annalee Newitz</a> (Tor)</li>
<li value="5"> <b>The Road to Roswell</b>, <a href="Connie_Willis">Connie Willis</a> (Del Rey)</li>
<li value="6"> <b>Lords of Uncreation</b>, <a href="Adrian_Tchaikovsky">Adrian Tchaikovsky</a> (Orbit)</li>
</ol>
</div>
<div class="categoryblock">
<div class="category">Young Adult Novel</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> <b>Promises Stronger Than Darkness</b>, <a href="Charlie_Jane_Anders">Charlie Jane Anders</a> (Tor Teen)</li>
</ol>
</div>
<div class="categoryblock">
<div class="category">First Novel</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> <b>The Saint of Bright Doors</b>, <a href="Vajra_Chandrasekera">Vajra Chandrasekera</a> (Tordotcom)</li>
</ol>
</div>
"""

HTML_2026 = """
<div class="categoryblock">
<div class="category">Sf Novel</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> <b>Death of the Author</b>, <a href="Nnedi_Okorafor">Nnedi Okorafor</a> (Morrow)</li>
<li value="2"> <b>Shroud</b>, <a href="Adrian_Tchaikovsky">Adrian Tchaikovsky</a> (Tor)</li>
<li value="3"> <b>Slow Gods</b>, <a href="Claire_North">Claire North</a> (Orbit)</li>
<li value="4"> <b>The Folded Sky</b>, <a href="Elizabeth_Bear">Elizabeth Bear</a> (Saga)</li>
<li value="5"> <b>The Shattering Peace</b>, <a href="John_Scalzi">John Scalzi</a> (Tor)</li>
<li value="6"> <b>All That We See or Seem</b>, <a href="Ken_Liu">Ken Liu</a> (Saga)</li>
</ol>
</div>
<div class="categoryblock">
<div class="category">Fantasy Novel</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> <b>The Everlasting</b>, <a href="Alix_E_Harrow">Alix E. Harrow</a> (Tor)</li>
<li value="2"> <b>The Incandescent</b>, <a href="Emily_Tesh">Emily Tesh</a> (Tor)</li>
<li value="3"> (tie): <b>Hemlock &amp; Silver</b>, <a href="T_Kingfisher">T. Kingfisher</a> (Tor)</li>
<li value="3"> (tie): <b>Katabasis</b>, <a href="R_F_Kuang">R. F. Kuang</a> (Harper Voyager)</li>
<li value="5"> <b>A Drop of Corruption</b>, <a href="Robert_Jackson_Bennett">Robert Jackson Bennett</a> (Del Rey)</li>
<li value="6"> <b>Queen Demon</b>, <a href="Martha_Wells">Martha Wells</a> (Tor)</li>
</ol>
</div>
<div class="categoryblock">
<div class="category">Horror Novel</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> <b>The Buffalo Hunter Hunter</b>, <a href="Stephen_Graham_Jones">Stephen Graham Jones</a> (Saga)</li>
</ol>
</div>
<div class="categoryblock">
<div class="category">Young Adult Book</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> <b>Historical YA Book</b>, <a href="Example_Author">Example Author</a> (Tor)</li>
</ol>
</div>
<div class="categoryblock">
<div class="category">Translated Novel</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> <b>On the Calculation of Volume III</b>, <a href="Solvej_Balle">Solvej Balle</a>, <a href="Sophia_Hersi_Smith">Sophia Hersi Smith</a> &amp; <a href="Jennifer_Russell">Jennifer Russell</a>, trans23 (New Directions; Faber &amp; Faber)</li>
<li value="2"> <b>Red Sword</b>, <a href="Bora_Chung">Bora Chung</a>, translated by <a href="Anton_Hur">Anton Hur</a> (Honford Star)</li>
<li value="3"> <b>The Wax Child</b>, <a href="Olga_Ravn">Olga Ravn</a>, translated by <a href="Martin_Aitken">Martin Aitken</a> (New Directions; Viking UK)</li>
</ol>
</div>
"""

HTML_COAUTHOR = """
<div class="categoryblock">
<div class="category">Novel</div>
<ol>
<li value="2"> <b>The Mote in God's Eye</b>, <a href="Larry_Niven">Larry Niven</a> &amp; <a href="Jerry_Pournelle">Jerry Pournelle</a> (Simon &amp; Schuster)</li>
</ol>
</div>
"""

HTML_MISSING_VALUE = """
<div class="categoryblock">
<div class="category">Sf Novel</div>
<ol>
<li> <span class="winner">Winner:</span> <b>Hyperion</b>, <a href="Dan_Simmons">Dan Simmons</a></li>
<li value="2"> <b>Rimrunners</b>, <a href="C_J_Cherryh">C. J. Cherryh</a></li>
</ol>
</div>
"""

HTML_ZERO_VALUE = """
<div class="categoryblock">
<div class="category">Sf Novel</div>
<ol>
<li value="0"> <span class="winner">Winner:</span> <b>Hyperion</b>, <a href="Dan_Simmons">Dan Simmons</a></li>
</ol>
</div>
"""

HTML_ALT_TITLE = """
<div class="categoryblock">
<div class="category">Sf Novel</div>
<ol>
<li value="15"> <b>Buying Time</b> (UK title: <b>The Long Habit of Living</b>), <a href="Joe_Haldeman">Joe Haldeman</a> (Morrow)</li>
</ol>
</div>
"""

HTML_OVERLAP_ANNUAL = """
<div class="categoryblock">
<div class="category">Sf Novel</div>
<ol>
<li value="3"> <b>Same Test Book</b>, <a href="Test_Author">Test Author</a> (Tor)</li>
</ol>
</div>
<div class="categoryblock">
<div class="category">First Novel</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> <b>Same Test Book</b>, <a href="Test_Author">Test Author</a> (Tor)</li>
</ol>
</div>
"""

HTML_OVERLAP_AUTHOR = _author_page(
    'Test Author',
    _entry(1991, 'Same Test Book', 'sf novel', '3rd place')
    + _entry(1991, 'Same Test Book', 'first novel', '<span class="win">winner</span>'),
)

HTML_OVERLAP_SF_ONLY = _author_page(
    'Test Author',
    _entry(1991, 'Same Test Book', 'sf novel', '3rd place'),
)

HTML_OVERLAP_FIRST_ONLY = _author_page(
    'Test Author',
    _entry(1991, 'Same Test Book', 'first novel', '<span class="win">winner</span>'),
)

URL_OVERLAP = 'https://www.sfadb.com/Locus_Awards_1991'
URL_TEST_AUTHOR = 'https://www.sfadb.com/Test_Author'
URL_SHORT_OVERLAP = 'https://www.sfadb.com/Locus_Awards_1992'
URL_SHORT_AUTHOR = 'https://www.sfadb.com/Short_Overlap_Author'


PAGES = {
    URL_SIMMONS: HTML_SIMMONS,
    URL_CHERRYH: HTML_CHERRYH_LIVE_SHAPE,
    'https://www.sfadb.com/George_Alec_Effinger': HTML_EFFINGER,
    'https://www.sfadb.com/Poul_Anderson': HTML_ANDERSON,
    'https://www.sfadb.com/Martha_Wells': HTML_WELLS,
    'https://www.sfadb.com/Connie_Willis': HTML_WILLIS,
    'https://www.sfadb.com/Adrian_Tchaikovsky': HTML_TCHAIKOVSKY,
    'https://www.sfadb.com/Nnedi_Okorafor': HTML_OKORAFOR,
    'https://www.sfadb.com/Elizabeth_Bear': HTML_BEAR,
    'https://www.sfadb.com/John_Scalzi': HTML_SCALZI,
    'https://www.sfadb.com/Ken_Liu': HTML_LIU,
    'https://www.sfadb.com/T_Kingfisher': HTML_KINGFISHER,
    'https://www.sfadb.com/R_F_Kuang': HTML_KUANG,
    'https://www.sfadb.com/Robert_Jackson_Bennett': HTML_BENNETT,
    'https://www.sfadb.com/Larry_Niven': HTML_NIVEN,
    'https://www.sfadb.com/Vonda_N_McIntyre': HTML_MCINTYRE,
    URL_1984: HTML_1984_COLLECTION,
    URL_1987: HTML_1987_COLLECTION,
    URL_1990: HTML_1990,
    URL_1971: HTML_1971,
    URL_1974: HTML_1974,
    URL_1975: HTML_1975_NOVELETTE,
    URL_1979: HTML_1979,
    URL_1999: HTML_1999_COLLECTION,
    URL_2008: HTML_2008,
    URL_2009: HTML_2009_EXHALATION_STORY,
    URL_2017: HTML_2017,
    URL_2018: HTML_2018,
    URL_2020: HTML_2020_COLLECTION,
    URL_2024: HTML_2024,
    URL_2025: HTML_2025,
    URL_2026: HTML_2026,
    URL_CHIANG: HTML_CHIANG,
    URL_GIBSON: HTML_GIBSON,
    URL_DAVIDSON: HTML_DAVIDSON,
    URL_SILVERBERG: HTML_SILVERBERG,
    URL_HUANG: HTML_HUANG,
    URL_ELMOHTAR: HTML_ELMOHTAR,
    URL_ELLISON: HTML_ELLISON,
    URL_CLARKE: HTML_CLARKE,
    URL_EKLUND: HTML_EKLUND,
    URL_TEST_AUTHOR: HTML_OVERLAP_AUTHOR,
    URL_OVERLAP: HTML_OVERLAP_ANNUAL,
    URL_SHORT_AUTHOR: HTML_SHORT_OVERLAP_AUTHOR,
    URL_SHORT_OVERLAP: HTML_SHORT_OVERLAP_ANNUAL,
}


def _fake_request(_opener, url: str) -> tuple[int, str]:
    body = PAGES.get(url)
    if body is None:
        return 404, ''
    return 200, body


class LocusTestCase(unittest.TestCase):
    def setUp(self) -> None:
        locus._reset_runtime_state()

    def tearDown(self) -> None:
        locus._reset_runtime_state()


class AuthorSlugTests(LocusTestCase):
    def test_ordinary_and_initial_slugs(self):
        self.assertEqual(locus._author_slug_candidates('Dan Simmons'), ('Dan_Simmons',))
        self.assertEqual(locus._author_slug_candidates('C. J. Cherryh'), ('C_J_Cherryh',))
        self.assertEqual(locus._author_slug_candidates('N. K. Jemisin'), ('N_K_Jemisin',))
        self.assertEqual(locus._author_slug_candidates('T. Kingfisher'), ('T_Kingfisher',))
        self.assertEqual(
            locus._author_slug_candidates('Ursula K. Le Guin'),
            ('Ursula_K_Le_Guin',),
        )

    def test_diacritic_slug_prefers_ascii_fold(self):
        self.assertEqual(
            locus._author_slug_candidates('China Miéville'),
            ('China_Mieville', 'China_Miéville'),
        )
        self.assertEqual(
            locus._author_slug_candidates('Isabel Cañas'),
            ('Isabel_Canas', 'Isabel_Cañas'),
        )


class AnnualParseTests(LocusTestCase):
    def test_1990_sf_novel_ranks_and_winner(self):
        records = locus._parse_annual_page(HTML_1990, 1990, URL_1990)
        by_title = {record.work_title: record for record in records if record.category == 'Sf Novel'}
        hyperion = by_title['Hyperion']
        self.assertEqual(hyperion.rank, 1)
        self.assertTrue(hyperion.winner)
        self.assertEqual(hyperion.work_author, 'Dan Simmons')
        self.assertEqual(by_title['Rimrunners'].rank, 2)
        self.assertEqual(by_title['A Fire in the Sun'].rank, 5)
        self.assertEqual(by_title['The Boat of a Million Years'].rank, 6)
        self.assertFalse(by_title['Rimrunners'].winner)

    def test_father_of_stones_is_emitted_as_novella_winner(self):
        records = locus._parse_annual_page(HTML_1990, 1990, URL_1990)
        novellas = [record for record in records if record.category == 'Novella']
        self.assertEqual(len(novellas), 1)
        record = novellas[0]
        self.assertEqual(record.work_title, 'The Father of Stones')
        self.assertEqual(record.work_author, 'Lucius Shepard')
        self.assertEqual(record.category, 'Novella')
        self.assertEqual(record.rank, 1)
        self.assertTrue(record.winner)

    def test_muse_of_fire_live_shaped_annual_row(self):
        records = locus._parse_annual_page(HTML_2008, 2008, URL_2008)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.work_title, 'Muse of Fire')
        self.assertNotEqual(record.work_title, 'The New Space Opera')
        self.assertEqual(record.work_author, 'Dan Simmons')
        self.assertEqual(record.category, 'Novella')
        self.assertEqual(record.rank, 5)
        self.assertFalse(record.winner)

    def test_river_judge_live_shaped_annual_row(self):
        records = locus._parse_annual_page(HTML_2025, 2025, URL_2025)
        record = next(item for item in records if item.work_title == 'The River Judge')
        self.assertEqual(record.work_author, 'S. L. Huang')
        self.assertEqual(record.category, 'Novelette')
        self.assertEqual(record.rank, 4)
        self.assertFalse(record.winner)

    def test_seasons_of_glass_and_iron_winner_does_not_use_anthology_title(self):
        records = locus._parse_annual_page(HTML_2017, 2017, URL_2017)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.work_title, 'Seasons of Glass and Iron')
        self.assertNotEqual(record.work_title, 'The Starlit Wood')
        self.assertEqual(record.work_author, 'Amal El-Mohtar')
        self.assertEqual(record.category, 'Short Story')
        self.assertEqual(record.rank, 1)
        self.assertTrue(record.winner)

    def test_deathbird_stays_short_fiction_not_short_story_or_novelette(self):
        records = locus._parse_annual_page(HTML_1974, 1974, URL_1974)
        record = next(item for item in records if item.work_title == 'The Deathbird')
        self.assertEqual(record.work_author, 'Harlan Ellison')
        self.assertEqual(record.category, 'Short Fiction')
        self.assertNotEqual(record.category, 'Short Story')
        self.assertNotEqual(record.category, 'Novelette')
        self.assertEqual(record.rank, 1)
        self.assertTrue(record.winner)

    def test_quoted_novella_winner_does_not_use_anthology_title(self):
        records = locus._parse_annual_page(HTML_1974, 1974, URL_1974)
        record = next(
            item for item in records if item.work_title == 'The Death of Doctor Island'
        )
        self.assertNotEqual(record.work_title, 'Universe 3')
        self.assertEqual(record.work_author, 'Gene Wolfe')
        self.assertEqual(record.category, 'Novella')
        self.assertEqual(record.rank, 1)
        self.assertTrue(record.winner)

    def test_wood_at_midwinter_uses_bold_title_fallback(self):
        records = locus._parse_annual_page(HTML_2025, 2025, URL_2025)
        record = next(
            item for item in records if item.work_title == 'The Wood at Midwinter'
        )
        self.assertEqual(record.work_author, 'Susanna Clarke')
        self.assertEqual(record.category, 'Short Story')
        self.assertEqual(record.rank, 6)
        self.assertFalse(record.winner)

    def test_stars_are_gods_keeps_both_linked_authors(self):
        records = locus._parse_annual_page(HTML_1975_NOVELETTE, 1975, URL_1975)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.work_title, 'If the Stars Are Gods')
        self.assertNotEqual(record.work_title, 'Universe 4')
        self.assertEqual(record.work_author, 'Gordon Eklund & Gregory Benford')
        self.assertEqual(record.category, 'Novelette')
        self.assertEqual(record.rank, 8)
        self.assertTrue(
            locus._record_matches(record, 'If the Stars Are Gods', 'Gordon Eklund')
        )
        self.assertTrue(
            locus._record_matches(record, 'If the Stars Are Gods', 'Gregory Benford')
        )

    def test_finalist_prefix_does_not_activate_winner_quoted_path(self):
        records = locus._parse_annual_page(
            HTML_FINALIST_PREFIX, 2025, URL_2025
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].work_title, 'Some Anthology')
        self.assertNotEqual(records[0].work_title, 'Some Story')

    def test_1971_ties_preserve_shared_ranks(self):
        records = locus._parse_annual_page(HTML_1971, 1971, URL_1971)
        novels = [record for record in records if record.category == 'Novel']
        ranks = [record.rank for record in novels]
        self.assertEqual(ranks, [1, 2, 2, 4, 5, 5, 7])
        ties = [record for record in novels if record.tied]
        self.assertEqual(
            [(record.work_title, record.rank) for record in ties],
            [
                ('Tower of Glass', 2),
                ('The Year of the Quiet Sun', 2),
                ('Downward to the Earth', 5),
                ('Fourth Mansions', 5),
            ],
        )

    def test_2026_fantasy_tie_skips_fourth(self):
        records = locus._parse_annual_page(HTML_2026, 2026, URL_2026)
        fantasy = {
            record.work_title: record
            for record in records
            if record.category == 'Fantasy Novel'
        }
        self.assertEqual(fantasy['Hemlock & Silver'].rank, 3)
        self.assertTrue(fantasy['Hemlock & Silver'].tied)
        self.assertEqual(fantasy['Katabasis'].rank, 3)
        self.assertTrue(fantasy['Katabasis'].tied)
        self.assertEqual(fantasy['A Drop of Corruption'].rank, 5)
        self.assertFalse(fantasy['A Drop of Corruption'].tied)
        self.assertEqual(fantasy['Queen Demon'].rank, 6)

    def test_distinct_category_labels_are_preserved(self):
        records_1979 = locus._parse_annual_page(HTML_1979, 1979, URL_1979)
        records_1990 = locus._parse_annual_page(HTML_1990, 1990, URL_1990)
        records_2024 = locus._parse_annual_page(HTML_2024, 2024, URL_2024)
        records_2026 = locus._parse_annual_page(HTML_2026, 2026, URL_2026)
        labels = {
            records_1979[0].category,
            records_1990[0].category,
            next(r.category for r in records_1990 if r.category == 'Horror Novel'),
            next(r.category for r in records_1990 if r.category == 'Novella'),
            next(r.category for r in records_2024 if r.category == 'Young Adult Novel'),
            next(r.category for r in records_2024 if r.category == 'First Novel'),
            next(r.category for r in records_2026 if r.category == 'Young Adult Book'),
            next(r.category for r in records_2026 if r.category == 'Translated Novel'),
            next(r.category for r in records_2026 if r.category == 'Fantasy Novel'),
        }
        self.assertEqual(
            labels,
            {
                'Novel',
                'Sf Novel',
                'Horror Novel',
                'Young Adult Novel',
                'First Novel',
                'Young Adult Book',
                'Translated Novel',
                'Fantasy Novel',
                'Novella',
            },
        )
        self.assertNotIn('Science Fiction Novel', labels)

    def test_missing_li_value_is_an_error(self):
        with self.assertRaises(locus.LocusSourceError) as ctx:
            locus._parse_annual_page(HTML_MISSING_VALUE, 1990, URL_1990)
        self.assertIn('li value', str(ctx.exception))

    def test_non_positive_li_value_is_an_error(self):
        with self.assertRaises(locus.LocusSourceError):
            locus._parse_annual_page(HTML_ZERO_VALUE, 1990, URL_1990)

    def test_coauthors_are_joined_and_individually_matchable(self):
        records = locus._parse_annual_page(
            HTML_COAUTHOR, 1975, 'https://www.sfadb.com/Locus_Awards_1975'
        )
        record = records[0]
        self.assertEqual(record.work_author, 'Larry Niven & Jerry Pournelle')
        self.assertTrue(locus._record_matches(record, "The Mote in God's Eye", 'Larry Niven'))
        self.assertTrue(
            locus._record_matches(record, "The Mote in God's Eye", 'Jerry Pournelle')
        )
        self.assertTrue(
            locus._record_matches(
                record, "The Mote in God's Eye", 'Larry Niven & Jerry Pournelle'
            )
        )
        self.assertFalse(locus._record_matches(record, "The Mote in God's Eye", 'Niven'))

    def test_uk_alternate_title_is_not_a_primary_match(self):
        records = locus._parse_annual_page(HTML_ALT_TITLE, 1990, URL_1990)
        record = records[0]
        self.assertEqual(record.work_title, 'Buying Time')
        self.assertTrue(locus._titles_equivalent('Buying Time', record.work_title))
        self.assertFalse(
            locus._titles_equivalent('The Long Habit of Living', record.work_title)
        )

    def test_translated_winner_keeps_author_not_translators(self):
        records = locus._parse_annual_page(HTML_2026, 2026, URL_2026)
        translated = next(
            record
            for record in records
            if record.work_title == 'On the Calculation of Volume III'
        )
        self.assertEqual(translated.work_author, 'Solvej Balle')
        self.assertEqual(translated.linked_authors, ('Solvej Balle',))
        self.assertTrue(
            locus._record_matches(
                translated,
                'On the Calculation of Volume III',
                'Solvej Balle',
            )
        )
        self.assertFalse(
            locus._record_matches(
                translated,
                'On the Calculation of Volume III',
                'Sophia Hersi Smith',
            )
        )
        self.assertFalse(
            locus._record_matches(
                translated,
                'On the Calculation of Volume III',
                'Jennifer Russell',
            )
        )

    def test_translated_by_marker_keeps_author_not_translator(self):
        records = locus._parse_annual_page(HTML_2026, 2026, URL_2026)
        red_sword = next(
            record for record in records if record.work_title == 'Red Sword'
        )
        self.assertEqual(red_sword.work_author, 'Bora Chung')
        self.assertEqual(red_sword.linked_authors, ('Bora Chung',))
        self.assertFalse(
            locus._record_matches(red_sword, 'Red Sword', 'Anton Hur')
        )

    def test_exhalation_collection_winner(self):
        records = locus._parse_annual_page(HTML_2020_COLLECTION, 2020, URL_2020)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.work_title, 'Exhalation')
        self.assertEqual(record.work_author, 'Ted Chiang')
        self.assertEqual(record.category, 'Collection')
        self.assertEqual(record.rank, 1)
        self.assertTrue(record.winner)
        self.assertEqual(record.linked_authors, ('Ted Chiang',))

    def test_burning_chrome_collection_second_place(self):
        records = locus._parse_annual_page(HTML_1987_COLLECTION, 1987, URL_1987)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.work_title, 'Burning Chrome')
        self.assertEqual(record.work_author, 'William Gibson')
        self.assertEqual(record.category, 'Collection')
        self.assertEqual(record.rank, 2)
        self.assertFalse(record.winner)

    def test_avram_davidson_treasury_keeps_author_not_editors(self):
        records = locus._parse_annual_page(HTML_1999_COLLECTION, 1999, URL_1999)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.work_title, 'The Avram Davidson Treasury')
        self.assertEqual(record.work_author, 'Avram Davidson')
        self.assertEqual(record.linked_authors, ('Avram Davidson',))
        self.assertEqual(record.category, 'Collection')
        self.assertEqual(record.rank, 1)
        self.assertTrue(record.winner)
        self.assertTrue(locus._author_matches_record('Avram Davidson', record))
        self.assertFalse(locus._author_matches_record('Robert Silverberg', record))
        self.assertFalse(locus._author_matches_record('Grania Davis', record))

    def test_hoka_keeps_both_collection_authors(self):
        records = locus._parse_annual_page(HTML_1984_COLLECTION, 1984, URL_1984)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.work_title, 'Hoka!')
        self.assertEqual(record.work_author, 'Poul Anderson & Gordon R. Dickson')
        self.assertEqual(
            record.linked_authors,
            ('Poul Anderson', 'Gordon R. Dickson'),
        )
        self.assertEqual(record.category, 'Collection')
        self.assertEqual(record.rank, 6)
        self.assertTrue(locus._author_matches_record('Poul Anderson', record))
        self.assertTrue(locus._author_matches_record('Gordon R. Dickson', record))

    def test_best_of_gene_wolfe_keeps_first_bold_title(self):
        records = locus._parse_annual_page(
            HTML_WOLFE_AKA_COLLECTION, 2010, URL_2010
        )
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.work_title, 'The Best of Gene Wolfe')
        self.assertNotEqual(record.work_title, 'The Very Best of Gene Wolfe')
        self.assertEqual(record.work_author, 'Gene Wolfe')
        self.assertEqual(record.category, 'Collection')


class WorkAuthorFromLinksTests(LocusTestCase):
    def test_edited_by_keeps_author_only(self):
        self.assertEqual(
            locus._work_authors_from_links(
                ('Author', 'Editor'),
                'Title, Author, edited by Editor',
            ),
            ('Author',),
        )

    def test_edited_by_two_editors_keeps_author_only(self):
        self.assertEqual(
            locus._work_authors_from_links(
                ('Author', 'Editor One', 'Editor Two'),
                'Title, Author, edited by Editor One & Editor Two',
            ),
            ('Author',),
        )

    def test_two_authors_without_edited_by_are_kept(self):
        self.assertEqual(
            locus._work_authors_from_links(
                ('Author One', 'Author Two'),
                'Title, Author One & Author Two',
            ),
            ('Author One', 'Author Two'),
        )

    def test_translated_by_keeps_author_only(self):
        self.assertEqual(
            locus._work_authors_from_links(
                ('Author', 'Translator'),
                'Title, Author, translated by Translator',
            ),
            ('Author',),
        )

    def test_earliest_of_translated_by_and_edited_by(self):
        self.assertEqual(
            locus._work_authors_from_links(
                ('Author', 'Translator', 'Editor'),
                'Title, Author, translated by Translator, edited by Editor',
            ),
            ('Author',),
        )

    def test_edited_by_without_prior_author_is_empty(self):
        self.assertEqual(
            locus._work_authors_from_links(
                ('Editor',),
                'Title, edited by Editor',
            ),
            (),
        )

    def test_unsupported_editor_phrases_are_not_cutoffs(self):
        self.assertEqual(
            locus._work_authors_from_links(
                ('Author', 'Other'),
                'Title, Author, ed. Other',
            ),
            ('Author', 'Other'),
        )
        self.assertEqual(
            locus._work_authors_from_links(
                ('Author', 'Other'),
                'Title, Author, selected by Other',
            ),
            ('Author', 'Other'),
        )


class QuotedTitleExtractionTests(LocusTestCase):
    def test_curly_double_quotes(self):
        self.assertEqual(
            locus._extract_leading_quoted_title('\u201cMuse of Fire\u201d'),
            'Muse of Fire',
        )

    def test_live_extra_space_before_closing_quote(self):
        self.assertEqual(
            locus._extract_leading_quoted_title('\u201cMuse of Fire \u201d'),
            'Muse of Fire',
        )

    def test_ascii_double_quotes(self):
        self.assertEqual(
            locus._extract_leading_quoted_title('"Muse of Fire"'),
            'Muse of Fire',
        )

    def test_single_quoted_forms_are_not_extracted(self):
        self.assertIsNone(
            locus._extract_leading_quoted_title('\u2018Muse of Fire\u2019')
        )
        self.assertIsNone(locus._extract_leading_quoted_title("'Muse of Fire'"))
        self.assertIsNone(locus._extract_leading_quoted_title("'Don't Look Now'"))
        self.assertIsNone(
            locus._extract_leading_quoted_title('\u2018Don\u2019t Look Now\u2019')
        )

    def test_internal_quotes_are_preserved(self):
        self.assertEqual(
            locus._extract_leading_quoted_title(
                '\u201cThe "Inner" Title\u201d (Anthology)'
            ),
            'The "Inner" Title',
        )
        self.assertEqual(
            locus._extract_leading_quoted_title('"Title with \'apostrophes\'"'),
            "Title with 'apostrophes'",
        )

    def test_unmatched_quote_returns_none(self):
        self.assertIsNone(
            locus._extract_leading_quoted_title('\u201cMuse of Fire')
        )
        self.assertIsNone(locus._extract_leading_quoted_title('"Muse of Fire'))

    def test_ordinary_unquoted_novel_text_returns_none(self):
        self.assertIsNone(
            locus._extract_leading_quoted_title(
                'Hyperion (Doubleday Foundation) — sf novel — winner'
            )
        )
        self.assertIsNone(locus._extract_leading_quoted_title('Muse of Fire'))


class AnnualQuotedTitleTests(LocusTestCase):
    def test_quoted_non_winner_extracts_without_winner_prefix(self):
        self.assertEqual(
            locus._extract_annual_quoted_title(
                ' \u201cThe River Judge\u201d, S. L. Huang (Reactor 6 mar 2024)'
            ),
            'The River Judge',
        )

    def test_winner_prefix_then_quoted_title(self):
        self.assertEqual(
            locus._extract_annual_quoted_title(
                ' Winner: \u201cSeasons of Glass and Iron\u201d, '
                'Amal El-Mohtar (The Starlit Wood)'
            ),
            'Seasons of Glass and Iron',
        )
        self.assertEqual(
            locus._extract_annual_quoted_title(
                'winner:\u201cThe Deathbird\u201d, Harlan Ellison'
            ),
            'The Deathbird',
        )

    def test_winner_prefix_without_quotes_returns_none(self):
        self.assertIsNone(
            locus._extract_annual_quoted_title(
                ' Winner: Hyperion, Dan Simmons (Doubleday Foundation)'
            )
        )

    def test_finalist_prefix_is_not_stripped(self):
        self.assertIsNone(
            locus._extract_annual_quoted_title(
                ' Finalist: \u201cSome Story\u201d, Test Author (Some Anthology)'
            )
        )


class AuthorPageParseTests(LocusTestCase):
    def test_muse_of_fire_discovery_maps_to_novella(self):
        page = locus._parse_author_page(HTML_SIMMONS, URL_SIMMONS)
        entry = next(
            item for item in page.entries if item.award_year == 2008
        )
        self.assertEqual(entry.work_title, 'Muse of Fire')
        self.assertNotEqual(entry.work_title, 'The New Space Opera')
        self.assertEqual(entry.category_text.casefold(), 'novella')
        self.assertEqual(entry.rank, 5)
        self.assertFalse(entry.winner)
        self.assertEqual(entry.annual_url, URL_2008)
        self.assertEqual(
            locus._annual_category_for_discovery(entry.category_text),
            'Novella',
        )

    def test_hyperion_discovery_still_uses_bold_title(self):
        page = locus._parse_author_page(HTML_SIMMONS, URL_SIMMONS)
        entry = next(
            item for item in page.entries if item.work_title == 'Hyperion'
        )
        self.assertEqual(entry.category_text.casefold(), 'sf novel')
        self.assertEqual(entry.rank, 1)
        self.assertTrue(entry.winner)
        self.assertEqual(entry.annual_url, URL_1990)

    def test_river_judge_discovery_maps_to_novelette(self):
        page = locus._parse_author_page(HTML_HUANG, URL_HUANG)
        entry = page.entries[0]
        self.assertEqual(entry.work_title, 'The River Judge')
        self.assertEqual(entry.category_text.casefold(), 'novelette')
        self.assertEqual(entry.rank, 4)
        self.assertFalse(entry.winner)
        self.assertEqual(entry.annual_url, URL_2025)
        self.assertEqual(
            locus._annual_category_for_discovery(entry.category_text),
            'Novelette',
        )

    def test_seasons_discovery_maps_to_short_story_without_first_emdash(self):
        page = locus._parse_author_page(HTML_ELMOHTAR, URL_ELMOHTAR)
        entry = page.entries[0]
        self.assertEqual(entry.work_title, 'Seasons of Glass and Iron')
        self.assertNotEqual(entry.work_title, 'The Starlit Wood')
        self.assertEqual(entry.category_text.casefold(), 'short story')
        self.assertEqual(entry.rank, 1)
        self.assertTrue(entry.winner)
        self.assertEqual(entry.annual_url, URL_2017)

    def test_deathbird_discovery_maps_to_short_fiction(self):
        page = locus._parse_author_page(HTML_ELLISON, URL_ELLISON)
        entry = page.entries[0]
        self.assertEqual(entry.work_title, 'The Deathbird')
        self.assertEqual(entry.category_text.casefold(), 'short fiction')
        self.assertEqual(entry.rank, 1)
        self.assertTrue(entry.winner)
        self.assertEqual(entry.annual_url, URL_1974)
        self.assertEqual(
            locus._annual_category_for_discovery(entry.category_text),
            'Short Fiction',
        )

    def test_one_dash_live_markup_still_finds_sf_novel(self):
        page = locus._parse_author_page(HTML_CHERRYH_LIVE_SHAPE, URL_CHERRYH)
        self.assertEqual(page.page_name, 'C. J. Cherryh')
        self.assertEqual(len(page.entries), 1)
        entry = page.entries[0]
        self.assertEqual(entry.work_title, 'Rimrunners')
        self.assertEqual(entry.category_text.casefold(), 'sf novel')
        self.assertEqual(entry.rank, 2)
        self.assertEqual(entry.annual_url, URL_1990)

    def test_prefix_collision_does_not_match(self):
        self.assertFalse(
            locus._titles_equivalent('The Collapsing', 'The Collapsing Empire')
        )
        self.assertTrue(
            locus._titles_equivalent('The Collapsing Empire', 'The Collapsing Empire')
        )

    def test_standalone_ampersand_matches_and(self):
        self.assertTrue(
            locus._titles_equivalent(
                'Jonathan Strange and Mr Norrell',
                'Jonathan Strange & Mr Norrell',
            )
        )
        self.assertTrue(
            locus._titles_equivalent(
                'Jonathan Strange & Mr Norrell',
                'Jonathan Strange and Mr Norrell',
            )
        )
        self.assertTrue(
            locus._titles_equivalent('Smith & Jones', 'Smith and Jones')
        )
        self.assertFalse(
            locus._titles_equivalent('The City', 'The City & The City')
        )


class LookupAndQualificationTests(LocusTestCase):
    def _lookup(self, title: str, author: str):
        with patch.object(locus, '_request_html', side_effect=_fake_request):
            return locus.lookup(title, author)

    def test_hyperion_winner_rank_one(self):
        with patch.object(locus, '_request_html', side_effect=_fake_request) as mocked:
            results = locus.lookup('Hyperion', 'Dan Simmons')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.award_name, 'Locus Award')
        self.assertEqual(result.award_year, 1990)
        self.assertEqual(result.category, 'Sf Novel')
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(result.rank, 1)
        self.assertEqual(result.source_name, 'Science Fiction Awards Database')
        self.assertEqual(result.source_url, URL_1990)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )
        fetched = [call.args[1] for call in mocked.call_args_list]
        self.assertEqual(fetched, [URL_SIMMONS, URL_1990])
        self.assertNotIn(URL_2008, fetched)
        self.assertNotIn(URL_2025, fetched)
        self.assertNotIn(URL_2017, fetched)
        self.assertNotIn(URL_1974, fetched)

    def test_1990_qualification_boundary(self):
        cases = (
            ('Rimrunners', 'C. J. Cherryh', 2, '2nd place', QualificationDecision.QUALIFIES),
            (
                'A Fire in the Sun',
                'George Alec Effinger',
                5,
                '5th place',
                QualificationDecision.QUALIFIES,
            ),
            (
                'The Boat of a Million Years',
                'Poul Anderson',
                6,
                '6th place',
                QualificationDecision.DOES_NOT_QUALIFY,
            ),
        )
        for title, author, rank, status, decision in cases:
            with self.subTest(title=title):
                results = self._lookup(title, author)
                self.assertEqual(len(results), 1)
                result = results[0]
                self.assertEqual(result.rank, rank)
                self.assertEqual(result.status, status)
                self.assertEqual(result.category, 'Sf Novel')
                self.assertEqual(qualify_award_result(result).decision, decision)

    def test_recent_ranks(self):
        cases = (
            ('System Collapse', 'Martha Wells', 2024, 1, 'Winner'),
            ('The Road to Roswell', 'Connie Willis', 2024, 5, '5th place'),
            ('Lords of Uncreation', 'Adrian Tchaikovsky', 2024, 6, '6th place'),
            ('Death of the Author', 'Nnedi Okorafor', 2026, 1, 'Winner'),
            ('The Folded Sky', 'Elizabeth Bear', 2026, 4, '4th place'),
            ('The Shattering Peace', 'John Scalzi', 2026, 5, '5th place'),
            ('All That We See or Seem', 'Ken Liu', 2026, 6, '6th place'),
            ('The Collapsing Empire', 'John Scalzi', 2018, 1, 'Winner'),
        )
        for title, author, year, rank, status in cases:
            with self.subTest(title=title):
                results = self._lookup(title, author)
                self.assertEqual(len(results), 1)
                result = results[0]
                self.assertEqual(result.award_year, year)
                self.assertEqual(result.rank, rank)
                self.assertEqual(result.status, status)
                self.assertEqual(result.source_name, 'Science Fiction Awards Database')

    def test_rank_greater_than_five_is_still_returned(self):
        results = self._lookup('The Boat of a Million Years', 'Poul Anderson')
        self.assertEqual(results[0].rank, 6)

    def test_1979_unified_novel_category(self):
        results = self._lookup('Dreamsnake', 'Vonda N. McIntyre')
        self.assertEqual(results[0].category, 'Novel')
        self.assertEqual(results[0].award_year, 1979)
        self.assertEqual(results[0].rank, 1)

    def test_unrelated_title_does_not_fetch_annual_pages(self):
        with patch.object(locus, '_request_html', side_effect=_fake_request) as mocked:
            results = locus.lookup('No Such Book', 'Dan Simmons')
        self.assertEqual(results, [])
        self.assertEqual(
            [call.args[1] for call in mocked.call_args_list],
            [URL_SIMMONS],
        )

    def test_muse_of_fire_lookup_fetches_only_2008_annual_page(self):
        with patch.object(locus, '_request_html', side_effect=_fake_request) as mocked:
            results = locus.lookup('Muse of Fire', 'Dan Simmons')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, 'Muse of Fire')
        self.assertNotEqual(result.work_title, 'The New Space Opera')
        self.assertEqual(result.award_name, 'Locus Award')
        self.assertEqual(result.award_year, 2008)
        self.assertEqual(result.category, 'Novella')
        self.assertEqual(result.rank, 5)
        self.assertEqual(result.status, '5th place')
        self.assertEqual(result.source_name, 'Science Fiction Awards Database')
        self.assertEqual(result.source_url, URL_2008)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            [call.args[1] for call in mocked.call_args_list],
            [URL_SIMMONS, URL_2008],
        )

    def test_river_judge_lookup_fetches_only_2025_annual_page(self):
        with patch.object(locus, '_request_html', side_effect=_fake_request) as mocked:
            results = locus.lookup('The River Judge', 'S. L. Huang')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, 'The River Judge')
        self.assertEqual(result.award_name, 'Locus Award')
        self.assertEqual(result.award_year, 2025)
        self.assertEqual(result.category, 'Novelette')
        self.assertEqual(result.rank, 4)
        self.assertEqual(result.status, '4th place')
        self.assertEqual(result.source_name, 'Science Fiction Awards Database')
        self.assertEqual(result.source_url, URL_2025)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            [call.args[1] for call in mocked.call_args_list],
            [URL_HUANG, URL_2025],
        )

    def test_seasons_of_glass_and_iron_lookup_is_short_story_winner(self):
        results = self._lookup('Seasons of Glass and Iron', 'Amal El-Mohtar')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, 'Seasons of Glass and Iron')
        self.assertNotEqual(result.work_title, 'The Starlit Wood')
        self.assertEqual(result.award_year, 2017)
        self.assertEqual(result.category, 'Short Story')
        self.assertEqual(result.rank, 1)
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )

    def test_deathbird_lookup_is_historical_short_fiction_winner(self):
        results = self._lookup('The Deathbird', 'Harlan Ellison')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, 'The Deathbird')
        self.assertEqual(result.award_year, 1974)
        self.assertEqual(result.category, 'Short Fiction')
        self.assertNotEqual(result.category, 'Short Story')
        self.assertNotEqual(result.category, 'Novelette')
        self.assertEqual(result.rank, 1)
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )

    def test_exhalation_collection_lookup_fetches_only_2020(self):
        with patch.object(locus, '_request_html', side_effect=_fake_request) as mocked:
            results = locus.lookup('Exhalation', 'Ted Chiang')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, 'Exhalation')
        self.assertEqual(result.work_author, 'Ted Chiang')
        self.assertEqual(result.award_name, 'Locus Award')
        self.assertEqual(result.award_year, 2020)
        self.assertEqual(result.category, 'Collection')
        self.assertEqual(result.rank, 1)
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(result.source_name, 'Science Fiction Awards Database')
        self.assertEqual(result.source_url, URL_2020)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            [call.args[1] for call in mocked.call_args_list],
            [URL_CHIANG, URL_2020],
        )

    def test_burning_chrome_collection_lookup_qualifies(self):
        results = self._lookup('Burning Chrome', 'William Gibson')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, 'Burning Chrome')
        self.assertEqual(result.work_author, 'William Gibson')
        self.assertEqual(result.award_year, 1987)
        self.assertEqual(result.category, 'Collection')
        self.assertEqual(result.rank, 2)
        self.assertEqual(result.status, '2nd place')
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )

    def test_hoka_collection_rank_six_does_not_qualify(self):
        results = self._lookup('Hoka!', 'Poul Anderson')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, 'Hoka!')
        self.assertEqual(result.work_author, 'Poul Anderson & Gordon R. Dickson')
        self.assertEqual(result.award_year, 1984)
        self.assertEqual(result.category, 'Collection')
        self.assertEqual(result.rank, 6)
        self.assertEqual(result.status, '6th place')
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.DOES_NOT_QUALIFY,
        )

    def test_treasury_author_lookup_qualifies(self):
        results = self._lookup('The Avram Davidson Treasury', 'Avram Davidson')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, 'The Avram Davidson Treasury')
        self.assertEqual(result.work_author, 'Avram Davidson')
        self.assertEqual(result.award_year, 1999)
        self.assertEqual(result.category, 'Collection')
        self.assertEqual(result.rank, 1)
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )

    def test_treasury_editor_author_page_does_not_qualify(self):
        results = self._lookup(
            'The Avram Davidson Treasury',
            'Robert Silverberg',
        )
        self.assertEqual(results, [])

    def test_exhalation_collection_and_short_story_stay_separate(self):
        pages = dict(PAGES)
        pages[URL_CHIANG] = HTML_CHIANG_CROSS

        def fake(_opener, url: str):
            body = pages.get(url)
            if body is None:
                return 404, ''
            return 200, body

        with patch.object(locus, '_request_html', side_effect=fake):
            results = locus.lookup('Exhalation', 'Ted Chiang')
        by_category = {result.category: result for result in results}
        self.assertEqual(set(by_category), {'Collection', 'Short Story'})
        self.assertEqual(by_category['Collection'].award_year, 2020)
        self.assertEqual(by_category['Collection'].rank, 1)
        self.assertEqual(by_category['Short Story'].award_year, 2009)
        self.assertEqual(by_category['Short Story'].rank, 2)
        self.assertNotEqual(
            by_category['Collection'].category,
            by_category['Short Story'].category,
        )

    def test_wood_at_midwinter_rank_six_does_not_qualify(self):
        results = self._lookup('The Wood at Midwinter', 'Susanna Clarke')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.category, 'Short Story')
        self.assertEqual(result.rank, 6)
        self.assertEqual(result.status, '6th place')
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.DOES_NOT_QUALIFY,
        )

    def test_stars_are_gods_multi_author_novelette_does_not_qualify(self):
        results = self._lookup('If the Stars Are Gods', 'Gordon Eklund')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, 'If the Stars Are Gods')
        self.assertEqual(result.work_author, 'Gordon Eklund & Gregory Benford')
        self.assertEqual(result.category, 'Novelette')
        self.assertEqual(result.rank, 8)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.DOES_NOT_QUALIFY,
        )

    def test_no_locus_section_is_empty_not_an_error(self):
        def fake(_opener, url: str):
            if url == URL_SIMMONS:
                return 200, HTML_NO_LOCUS
            return 404, ''

        with patch.object(locus, '_request_html', side_effect=fake):
            self.assertEqual(locus.lookup('Hyperion', 'Dan Simmons'), [])

    def test_malformed_locus_section_raises(self):
        def fake(_opener, url: str):
            if url == URL_SIMMONS:
                return 200, HTML_MALFORMED_LOCUS
            return 404, ''

        with patch.object(locus, '_request_html', side_effect=fake):
            with self.assertRaises(locus.LocusSourceError):
                locus.lookup('Hyperion', 'Dan Simmons')

    def test_unknown_author_404_is_empty(self):
        def fake(_opener, url: str):
            return 404, ''

        with patch.object(locus, '_request_html', side_effect=fake):
            self.assertEqual(locus.lookup('Hyperion', 'Nobody Known'), [])

    def test_wrong_identity_page_is_rejected(self):
        def fake(_opener, url: str):
            return 200, HTML_WRONG_PERSON

        with patch.object(locus, '_request_html', side_effect=fake):
            self.assertEqual(locus.lookup('Hyperion', 'Dan Simmons'), [])

    def test_404_then_next_candidate_is_accepted(self):
        annual = 'https://www.sfadb.com/Locus_Awards_2005'
        author_html = _author_page(
            'China Miéville',
            _entry(2005, 'Iron Council', 'fantasy novel', '<span class="win">winner</span>'),
        )
        annual_html = """
<div class="categoryblock">
<div class="category">Fantasy Novel</div>
<ol>
<li value="1"> <span class="winner">Winner:</span> <b>Iron Council</b>, <a href="China_Mieville">China Miéville</a> (Del Rey)</li>
</ol>
</div>
"""

        requested: list[str] = []

        def fake(_opener, url: str):
            requested.append(url)
            if url.endswith('China_Mieville'):
                return 404, ''
            if 'China_Mi' in url and url != annual:
                return 200, author_html
            if url == annual:
                return 200, annual_html
            return 404, ''

        with patch.object(locus, '_request_html', side_effect=fake):
            results = locus.lookup('Iron Council', 'China Miéville')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].rank, 1)
        self.assertEqual(results[0].status, 'Winner')
        self.assertTrue(requested[0].endswith('China_Mieville'))
        self.assertGreaterEqual(len(requested), 3)

    def test_discovery_rank_disagreement_raises(self):
        bad_author = _author_page(
            'Dan Simmons',
            _entry(1990, 'Hyperion', 'sf novel', '4th place'),
        )

        def fake(_opener, url: str):
            if url == URL_SIMMONS:
                return 200, bad_author
            if url == URL_1990:
                return 200, HTML_1990
            return 404, ''

        with patch.object(locus, '_request_html', side_effect=fake):
            with self.assertRaises(locus.LocusSourceError) as ctx:
                locus.lookup('Hyperion', 'Dan Simmons')
        self.assertIn('disagreed', str(ctx.exception))

    def test_other_source_failure_does_not_suppress_locus(self):
        def boom(title: str, author: str, series=None):
            raise RuntimeError('pulitzer down')

        with patch.object(locus, '_request_html', side_effect=_fake_request):
            report = _lookup_awards_from_sources(
                'Hyperion',
                'Dan Simmons',
                (
                    AwardSource('pulitzer', 'Pulitzer Prizes', boom),
                    AwardSource('locus', 'Locus Awards', locus.lookup),
                ),
            )
        self.assertEqual(len(report.failures), 1)
        self.assertEqual(report.failures[0].source_name, 'Pulitzer Prizes')
        self.assertEqual(len(report.assessments), 1)
        self.assertEqual(report.assessments[0].result.work_title, 'Hyperion')
        self.assertEqual(
            report.assessments[0].qualification.decision,
            QualificationDecision.QUALIFIES,
        )

    def test_same_year_two_categories_do_not_cross_match(self):
        def fake(_opener, url: str):
            if url == URL_TEST_AUTHOR:
                return 200, HTML_OVERLAP_AUTHOR
            if url == URL_OVERLAP:
                return 200, HTML_OVERLAP_ANNUAL
            return 404, ''

        with patch.object(locus, '_request_html', side_effect=fake):
            results = locus.lookup('Same Test Book', 'Test Author')
        by_category = {result.category: result for result in results}
        self.assertEqual(set(by_category), {'Sf Novel', 'First Novel'})
        self.assertEqual(by_category['Sf Novel'].rank, 3)
        self.assertEqual(by_category['Sf Novel'].status, '3rd place')
        self.assertEqual(by_category['First Novel'].rank, 1)
        self.assertEqual(by_category['First Novel'].status, 'Winner')

    def test_sf_novel_discovery_ignores_first_novel_rank_on_same_page(self):
        def fake(_opener, url: str):
            if url == URL_TEST_AUTHOR:
                return 200, HTML_OVERLAP_SF_ONLY
            if url == URL_OVERLAP:
                return 200, HTML_OVERLAP_ANNUAL
            return 404, ''

        with patch.object(locus, '_request_html', side_effect=fake):
            results = locus.lookup('Same Test Book', 'Test Author')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].category, 'Sf Novel')
        self.assertEqual(results[0].rank, 3)

    def test_first_novel_discovery_ignores_sf_novel_rank_on_same_page(self):
        def fake(_opener, url: str):
            if url == URL_TEST_AUTHOR:
                return 200, HTML_OVERLAP_FIRST_ONLY
            if url == URL_OVERLAP:
                return 200, HTML_OVERLAP_ANNUAL
            return 404, ''

        with patch.object(locus, '_request_html', side_effect=fake):
            results = locus.lookup('Same Test Book', 'Test Author')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].category, 'First Novel')
        self.assertEqual(results[0].rank, 1)

    def test_same_short_title_keeps_novelette_and_short_story_distinct(self):
        def fake(_opener, url: str):
            if url == URL_SHORT_AUTHOR:
                return 200, HTML_SHORT_OVERLAP_AUTHOR
            if url == URL_SHORT_OVERLAP:
                return 200, HTML_SHORT_OVERLAP_ANNUAL
            return 404, ''

        with patch.object(locus, '_request_html', side_effect=fake):
            results = locus.lookup('Same Short Book', 'Short Overlap Author')
        by_category = {result.category: result for result in results}
        self.assertEqual(set(by_category), {'Novelette', 'Short Story'})
        self.assertEqual(by_category['Novelette'].rank, 3)
        self.assertEqual(by_category['Novelette'].status, '3rd place')
        self.assertEqual(by_category['Short Story'].rank, 1)
        self.assertEqual(by_category['Short Story'].status, 'Winner')


class RedirectHostTests(LocusTestCase):
    def test_external_redirect_is_an_error(self):
        class FakeResponse:
            def __init__(self) -> None:
                self.status = 200
                self.headers = {}

            def geturl(self) -> str:
                return 'https://example.com/not-sfadb'

            def getcode(self) -> int:
                return 200

            def read(self) -> bytes:
                return b'<html>offsite</html>'

            def __enter__(self):
                return self

            def __exit__(self, *args) -> bool:
                return False

        class FakeOpener:
            def open(self, request, timeout=None):
                return FakeResponse()

        with self.assertRaises(locus.LocusSourceError) as ctx:
            locus._request_html(
                FakeOpener(),
                'https://www.sfadb.com/Dan_Simmons',
            )
        self.assertIn('redirected off SFADB', str(ctx.exception))


class CacheTests(LocusTestCase):
    def test_second_lookup_reuses_author_and_annual_pages(self):
        with patch.object(locus, '_request_html', side_effect=_fake_request) as mocked:
            first = locus.lookup('Hyperion', 'Dan Simmons')
            second = locus.lookup('Hyperion', 'Dan Simmons')
        self.assertEqual(first[0].rank, 1)
        self.assertEqual(second[0].rank, 1)
        self.assertEqual(
            [call.args[1] for call in mocked.call_args_list],
            [URL_SIMMONS, URL_1990],
        )

    def test_failed_fetch_is_not_cached(self):
        calls = {'n': 0}

        def fake(_opener, url: str):
            calls['n'] += 1
            raise locus.LocusSourceError('network down')

        with patch.object(locus, '_request_html', side_effect=fake):
            with self.assertRaises(locus.LocusSourceError):
                locus.lookup('Hyperion', 'Dan Simmons')
            with self.assertRaises(locus.LocusSourceError):
                locus.lookup('Hyperion', 'Dan Simmons')
        self.assertEqual(calls['n'], 2)

    def test_malformed_annual_page_is_not_cached(self):
        calls = {'n': 0}

        def fake(_opener, url: str):
            calls['n'] += 1
            if url == URL_SIMMONS:
                return 200, HTML_SIMMONS
            if url == URL_1990:
                return 200, HTML_MISSING_VALUE
            return 404, ''

        with patch.object(locus, '_request_html', side_effect=fake):
            with self.assertRaises(locus.LocusSourceError):
                locus.lookup('Hyperion', 'Dan Simmons')
            with self.assertRaises(locus.LocusSourceError):
                locus.lookup('Hyperion', 'Dan Simmons')
        self.assertEqual(calls['n'], 3)
        self.assertNotIn(URL_1990, locus._annual_page_cache)


if __name__ == '__main__':
    unittest.main()
