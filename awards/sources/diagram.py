"""Reviewed annual Diagram Prize winners; offline historical archive.

The prize recognizes a book title. It does not evaluate literary quality.
Facts and scope are documented in data/diagram_provenance.md.
"""
from __future__ import annotations
import re
import threading
import unicodedata
from ..matching import normalize_title_conjunctions
from ..model import AwardResult

SOURCE_KEY = 'diagram'
SOURCE_NAME = 'Wikipedia (reviewed Diagram Prize historical archive)'
AWARD_NAME = 'Diagram Prize for Oddest Title of the Year'
SOURCE_HOME_URL = 'https://www.thebookseller.com/features/diagram-prize-previous-winners'
SOURCE_ARCHIVE_URL = 'https://en.wikipedia.org/wiki/Bookseller/Diagram_Prize_for_Oddest_Title_of_the_Year'
CATEGORIES = ('Oddest book title',)
_WINNERS = (
    (1979, 'The Madam as Entrepreneur: Career Management in House Prostitution', 'Barbara Sherman Heyl'),
    (1980, 'The Joy of Chickens', 'Dennis Nolan'),
    (1983, 'Unsolved Problems of Modern Theory of Lengthwise Rolling', 'A. I. Tselikov & G. S. Nikitin & S. E. Rokotyan'),
    (1984, 'The Book of Marmalade: Its Antecedents, Its History, and Its Role in the World Today', 'Anne Wilson'),
    (1985, 'Natural Bust Enlargement with Total Mind Power: How to Use the Other 90% of Your Mind to Increase the Size of Your Breasts', 'Donald L. Wilson'),
    (1986, 'Oral Sadism and the Vegetarian Personality', 'Glenn C. Ellenbogen'),
    (1988, 'Versailles: The View from Sweden', 'Elaine Dee & Guy Walton'),
    (1989, 'How to Shit in the Woods: An Environmentally Sound Approach to a Lost Art', 'Kathleen Meyer'),
    (1990, 'Lesbian Sadomasochism Safety Manual', 'Pat Califia'),
    (1992, 'How to Avoid Huge Ships', 'John W. Trimmer'),
    (1993, 'American Bottom Archaeology', 'Charles J. Bareis & James W. Porter'),
    (1994, 'Highlights in the History of Concrete', 'C. C. Stanley'),
    (1995, 'Reusing Old Graves: A Report on Popular British Attitudes', 'Douglas Davies & Alastair Shaw'),
    (1996, 'Greek Rural Postmen and Their Cancellation Numbers', 'Derek Willan'),
    (1997, 'The Joy of Sex: Pocket Edition', 'Alex Comfort'),
    (1998, 'Developments in Dairy Cow Breeding: New Opportunities to Widen the Use of Straw', 'Gareth Williams'),
    (1999, 'Weeds in a Changing World: British Crop Protection Council Symposium Proceedings No. 64', 'Charles H. Stirton'),
    (2000, 'Designing High Performance Stiffened Structures', 'Institution of Mechanical Engineers'),
    (2001, 'Butterworths Corporate Manslaughter Service', 'Gerard Forlin'),
    (2002, 'Living with Crazy Buttocks', 'Kaz Cooke'),
    (2003, 'The Big Book of Lesbian Horse Stories', 'Alisa Surkis & Monica Nolan'),
    (2004, 'Bombproof Your Horse', 'Rick Pelicano & Lauren Tjaden'),
    (2005, "People Who Don't Know They're Dead: How They Attach Themselves to Unsuspecting Bystanders and What to Do About It", 'Gary Leon Hill'),
    (2006, 'The Stray Shopping Carts of Eastern North America: A Guide to Field Identification', 'Julian Montague'),
    (2007, 'If You Want Closure in Your Relationship, Start with Your Legs', 'Big Boom'),
    (2008, 'The 2009–2014 World Outlook for 60-milligram Containers of Fromage Frais', 'Philip M. Parker'),
    (2009, 'Crocheting Adventures with Hyperbolic Planes', 'Daina Taimina'),
    (2010, 'Managing a Dental Practice: The Genghis Khan Way', 'Michael R. Young'),
    (2011, 'Cooking with Poo', 'Saiyuud Diwong'),
    (2012, "Goblinproofing One's Chicken Coop", 'Reginald Bakeley'),
    (2013, 'How to Poo on a Date', 'Mats & Enzo'),
    (2014, 'Strangers Have the Best Candy', 'Margaret Meps Schulte'),
    (2015, 'Too Naked for the Nazis', 'Alan Stafford'),
    (2016, 'The Commuter Pig Keeper: A Comprehensive Guide to Keeping Pigs when Time is your Most Precious Commodity', 'Michaela Giles'),
    (2018, 'The Joy of Waterboiling', 'Thomas Götz von Aust'),
    (2019, 'The Dirt Hole and its Variations', 'Charles L. Dobbins'),
    (2020, 'A Dog Pissing at the Edge of a Path: Animal Metaphors in an Eastern Indonesian Society', 'Gregory Forth'),
    (2021, 'Is Superman Circumcised?', 'Roy Schwartz'),
    (2022, "RuPedagogies of Realness: Essays on Teaching and Learning With RuPaul's Drag Race", 'Lindsay Bryde & Tommy Mayberry'),
    (2023, 'Danger Sound Klaxon! The Horn That Changed History', 'Matthew F. Jordan'),
    (2024, 'The Philosopher Fish: Sturgeon, Caviar, and the Geography of Desire', 'Richard Adams Carey'),
    (2025, "The Pornographic Delicatessen: Midcentury Montréal's Erotic Art, Media, and Spaces", 'Matthew Purvis'),
)
_TITLE_ALIASES = {1993: ('American Bottom Archaeology: A Summary of the FAI-270 Project Contribution to the Culture '
        'History of the Mississippi River Valley',),
 2004: ('Bombproof Your Horse: Teach Your Horse to Be Confident, Obedient, and Safe, No Matter '
        'What You Encounter',),
 2013: ("How to Poo on a Date: The Lovers' Guide to Toilet Etiquette",)}
_records = None
_lock = threading.Lock()

def _key(value):
    value = unicodedata.normalize('NFKC', value).casefold()
    value = value.replace('’', "'").replace('–', '-').replace('—', '-')
    value = re.sub(r'\b([a-z])\.\s+', r'\1.', value)
    return normalize_title_conjunctions(re.sub(r'\s+', ' ', value).strip())

def _author_key(value):
    # Calibre joins coauthors with &, whereas source lists use 'and'.
    # Require the complete credited set; a single coauthor is not enough.
    return tuple(sorted(_key(part) for part in re.split(r'\s+(?:&|and)\s+', value, flags=re.I)))

def _get_records():
    global _records
    with _lock:
        if _records is None:
            _records = tuple(AwardResult(
                work_title=title, work_author=author, award_name=AWARD_NAME,
                award_year=year, category=None, status='Winner', rank=None,
                source_name=SOURCE_NAME, source_url=SOURCE_ARCHIVE_URL,
            ) for year, title, author in _WINNERS)
        return _records

def _reset_runtime_state():
    global _records
    with _lock:
        _records = None

def lookup(title, author, series=None):
    if not title.strip() or not author.strip():
        raise ValueError('title and author must be non-empty')
    title_key, author_key = _key(title), _author_key(author)
    return [r for r in _get_records()
            if title_key in {_key(t) for t in (r.work_title, *_TITLE_ALIASES.get(r.award_year, ()))}
            and author_key == _author_key(r.work_author)]
