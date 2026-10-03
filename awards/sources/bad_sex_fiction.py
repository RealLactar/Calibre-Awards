"""Reviewed historical Bad Sex in Fiction winners; no network required.

Literary Review's public archive is incomplete and labels The Stonebreakers
1995. The historical winners list identifies it as 1994 (1995: Gridiron).
See data/bad_sex_provenance.md for provenance and scope.
"""
import re
import threading
import unicodedata
from ..matching import normalize_title_conjunctions
from ..model import AwardResult

SOURCE_KEY = 'bad_sex_fiction'
SOURCE_NAME = 'Literary Review (reviewed historical archive)'
AWARD_NAME = 'Bad Sex in Fiction Award'
SOURCE_HOME_URL = 'https://literaryreview.co.uk/bad-sex-in-fiction-award'
CATEGORIES = ('Fiction',)
_HISTORICAL_URL = 'https://en.wikipedia.org/wiki/Literary_Review'
_WINNERS = (
    (1993, 'A Time to Dance', 'Melvyn Bragg'),
    (1994, 'The Stonebreakers', 'Philip Hook'),
    (1995, 'Gridiron', 'Philip Kerr'),
    (1996, 'The Big Kiss: An Arcade Mystery', 'David Huggins'),
    (1997, 'The Matter of the Heart', 'Nicholas Royle'),
    (1998, 'Charlotte Gray', 'Sebastian Faulks'),
    (1999, 'Starcrossed', 'A. A. Gill'),
    (2000, 'Kissing England', 'Sean Thomas'),
    (2001, 'Rescue Me', 'Christopher Hart'),
    (2002, 'Tread Softly', 'Wendy Perriam'),
    (2003, 'Bunker 13', 'Aniruddha Bahal'),
    (2004, 'I Am Charlotte Simmons', 'Tom Wolfe'),
    (2005, 'Winkler', 'Giles Coren'),
    (2006, 'Twenty Something', 'Iain Hollingshead'),
    (2007, 'The Castle in the Forest', 'Norman Mailer'),
    (2008, 'Shire Hell', 'Rachel Johnson'),
    (2009, 'The Kindly Ones', 'Jonathan Littell'),
    (2010, 'The Shape of Her', 'Rowan Somerville'),
    (2011, 'Ed King', 'David Guterson'),
    (2012, 'Infrared', 'Nancy Huston'),
    (2013, 'The City of Devi', 'Manil Suri'),
    (2014, 'The Age of Magic', 'Ben Okri'),
    (2015, 'List of the Lost', 'Morrissey'),
    (2016, 'The Day Before Happiness', 'Erri De Luca'),
    (2017, 'The Destroyers', 'Christopher Bollen'),
    (2018, 'Katerina', 'James Frey'),
    (2019, 'The Office of Gardens and Ponds', 'Didier Decoin'),
    (2019, 'Pax', 'John Harvey'),
)
_OFFICIAL_YEARS = frozenset((1997, 2003, 2004, 2005, *range(2008, 2020)))
_records = None
_lock = threading.Lock()

def _key(value):
    value = unicodedata.normalize('NFKC', value).casefold()
    value = value.replace('’', "'").replace('–', '-').replace('—', '-')
    value = re.sub(r'\b([a-z])\.\s+', r'\1.', value)
    return normalize_title_conjunctions(re.sub(r'\s+', ' ', value).strip())

def _get_records():
    global _records
    with _lock:
        if _records is None:
            _records = tuple(AwardResult(
                work_title=title, work_author=author, award_name=AWARD_NAME,
                award_year=year, category=None, status='Winner', rank=None,
                source_name=SOURCE_NAME if year in _OFFICIAL_YEARS else
                    'Historical winners list (Wikipedia; reviewed archive)',
                source_url=SOURCE_HOME_URL if year in _OFFICIAL_YEARS else _HISTORICAL_URL,
            ) for year, title, author in _WINNERS)
        return _records

def _reset_runtime_state():
    global _records
    with _lock:
        _records = None

def lookup(title, author, series=None):
    if not title.strip() or not author.strip():
        raise ValueError('title and author must be non-empty')
    return [r for r in _get_records() if _key(r.work_title) == _key(title)
            and _key(r.work_author) == _key(author)]
