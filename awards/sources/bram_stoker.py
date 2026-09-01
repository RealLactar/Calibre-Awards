"""Official Horror Writers Association Bram Stoker Award Winners and Finalists.

Phase 1 covers bibliographic work categories on HWA HTML year-census pages
from 1987 through the latest completed publication-year cycle. Preliminary
Ballot, recommendation lists, screenplay, other-media, and person/service
honors are ignored. Historical category names are preserved.
"""

from __future__ import annotations

import json
import re
import threading
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.parse import urlparse

from .. import cache
from ..matching import normalize_title_conjunctions
from ..model import AwardResult

TIMEOUT_SECONDS = 30
SOURCE_KEY = 'bram_stoker'
AWARD_NAME = 'Bram Stoker Award'
SOURCE_NAME = 'Horror Writers Association'
SITE_ORIGIN = 'https://bramstokerawards.horror.org'
SOURCE_HOME_URL = SITE_ORIGIN + '/'
MIN_SUPPORTED_YEAR = 1987
MAX_VERIFIED_YEAR = 2025
INDEX_CACHE_VERSION = 1
YEAR_CACHE_VERSION = 1
INDEX_ENTRY_KIND = 'index'
INDEX_ENTRY_KEY = 'years'
YEAR_ENTRY_KIND = 'years'
HISTORICAL_CACHE_TTL_SECONDS = 180 * 24 * 60 * 60
CURRENT_CACHE_BASE_TTL_SECONDS = 7 * 24 * 60 * 60
CURRENT_CACHE_REFRESH_OFFSET_SECONDS = 16 * 60 * 60
CURRENT_CACHE_TTL_SECONDS = (
    CURRENT_CACHE_BASE_TTL_SECONDS + CURRENT_CACHE_REFRESH_OFFSET_SECONDS
)
SOURCEINFO_CATEGORIES = (
    'Novel',
    'First Novel',
    'Long Fiction',
    'Short Fiction',
    'Fiction Collection',
    'Anthology',
    'Poetry',
    'Nonfiction',
    'Short Non-Fiction',
    'Graphic Novel',
    'Young Adult Novel',
    'Middle Grade Novel',
)

_YEAR_STATES = frozenset({'absent', 'finalist', 'winner'})
_PARSED_STATUSES = frozenset({'Winner', 'Finalist'})
_STATUS_WEIGHT = {
    'Finalist': 1,
    'Winner': 2,
}
_RECORD_CACHE_FIELDS = (
    'award_year',
    'category',
    'source_url',
    'status',
    'work_author',
    'work_title',
)
_INDEX_COVERAGE_FIELDS = frozenset({
    'kind',
    'latest_completed_year',
    'year_urls',
    'winner_urls',
})
_YEAR_COVERAGE_FIELDS = frozenset({'award_year', 'state'})
_OFFICIAL_HTML_HOSTS = frozenset({
    'bramstokerawards.horror.org',
    'www.bramstokerawards.horror.org',
})
_VOID_TAGS = frozenset({
    'area',
    'base',
    'br',
    'col',
    'embed',
    'hr',
    'img',
    'input',
    'link',
    'meta',
    'source',
    'track',
    'wbr',
})
_IGNORE_TAGS = frozenset({'script', 'style', 'svg', 'noscript', 'iframe'})
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept': (
        'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'identity',
}
_JSON_HEADERS = {
    **_BROWSER_HEADERS,
    'Accept': 'application/json,text/html;q=0.8,*/*;q=0.7',
}

# Explicit official census URLs. Do not guess year slugs.
HISTORICAL_CENSUS_PATHS: dict[int, str] = {
    1987: '/about-the-awards/1987-bram-stoker-award-nominees-winner/',
    1988: '/about-the-awards/1988-bram-stoker-award-winners-nominees/',
    1989: '/about-the-awards/1989-bram-stoker-award-winners-nominees/',
    1990: '/about-the-awards/1990-bram-stoker-award-winners-nominees/',
    1991: '/about-the-awards/1991-bram-stoker-award-winners-nominees/',
    1992: '/about-the-awards/1992-bram-stoker-award-winners-nominees/',
    1993: '/about-the-awards/1993-bram-stoker-award-winners-nominees/',
    1994: '/about-the-awards/1994-bram-stoker-award-winners-nominees/',
    1995: '/about-the-awards/1995-bram-stoker-award-winners-nominees/',
    1996: '/about-the-awards/1996-bram-stoker-award-winners-nominees/',
    1997: '/about-the-awards/1997-bram-stoker-award-winners-nominees/',
    1998: '/about-the-awards/1998-bram-stoker-award-winners-nominees/',
    1999: '/about-the-awards/1999-bram-stoker-award-winners-nominees/',
    2000: '/about-the-awards/2000-bram-stoker-award-winners-nominees/',
    2001: '/about-the-awards/2001-bram-stoker-award-winners-nominees/',
    2002: '/about-the-awards/2002-bram-stoker-award-winners-nominees/',
    2003: '/about-the-awards/2003-bram-stoker-award-winners-nominees/',
    2004: '/about-the-awards/2004-bram-stoker-award-winners-nominees/',
    2005: '/about-the-awards/2005-bram-stoker-award-winners-nominees/',
    2006: '/about-the-awards/2006-bram-stoker-award-winners-nominees/',
    2007: '/about-the-awards/2007-bram-stoker-award-winners-nominees/',
    2008: '/about-the-awards/2008-bram-stoker-award-winners-nominees-2/',
    2009: '/about-the-awards/2008-bram-stoker-award-winners-nominees/',
    2010: '/about-the-awards/2010-bram-stoker-award-winners-nominees/',
    2011: '/about-the-awards/2011-bram-stoker-award-winners-nominees/',
    2012: '/about-the-awards/2012-bram-stoker-awards-winners-nominees/',
    2013: '/about-the-awards/2013-bram-stoker-award-winners-nominees/',
    2014: '/about-the-awards/2014-bram-stoker-award-winners-nominees/',
    2015: '/about-the-awards/2015-bram-stoker-award-nominees-winners/',
    2016: '/about-the-awards/2016-bram-stoker-award-winners-nominees/',
    2017: '/about-the-awards/2017-bram-stoker-award-winners-nominees/',
    2018: '/news/2018-bram-stoker-awards-winners-nominees/',
    2019: '/news/the-2019-bram-stoker-award-winners/',
    2020: '/news/4394/',
    2021: '/news/4491/',
    2022: '/front-page/the-2022-bram-stoker-awards-final-ballot/',
    2023: '/front-page/the-2023-bram-stoker-awards-final-ballot/',
    2024: '/front-page/the-2024-bram-stoker-award-winners/',
    2025: '/front-page/6370/',
}

_INCLUDED_HEADING_KEYS = frozenset({
    'novel',
    'first novel',
    'long fiction',
    'short fiction',
    'fiction collection',
    'collection',
    'anthology',
    'poetry collection',
    'poetry',
    'poetry (collection and long form)',
    'non-fiction',
    'nonfiction',
    'long non-fiction',
    'long nonfiction',
    'short non-fiction',
    'short nonfiction',
    'graphic novel',
    'illustrated narrative',
    'work for young readers',
    'young adult novel',
    'ya novel',
    'middle grade novel',
    'novella',
    'novelet',
    'novelette',
    'short story',
})
_EXCLUDED_HEADING_KEYS = frozenset({
    'screenplay',
    'other media',
    'alternative forms',
    'final frame',
    'final frame film competition',
    'final frame grand prize winner',
    'vampire novel of the century',
    'lifetime achievement',
    'lifetime achievement award',
    'lifetime achievement awards',
    'specialty press',
    'specialty press award',
    'specialty awards',
    'silver hammer',
    'silver hammer award',
    'karen lansdale silver hammer award',
    'richard laymon presidents award',
    "richard laymon president's award",
    'richard h. laymon presidents award',
    "richard h. laymon president's award",
    'mentor of the year',
    'mentor of the year award',
})
_IGNORE_HEADING_PREFIXES = (
    'bram stoker',
    'the bram stoker',
    'horror writers',
    'the horror writers',
    'presented in',
    'the winners were',
    'winners were announced',
    'from left to right',
    'photo by',
    'also presented',
    'named in honor',
    'works appearing',
    'the hwa',
    'contact:',
    'for press',
    'for media',
    'note to',
    'note:',
    'active and lifetime',
    'bookings',
    'questions',
    'please direct',
    'our voting',
    'if your work',
    'laura blackwell',
    'we proudly',
    'due to a tie',
    '*due to a tie',
)
_TIE_HEADING_TAIL_RE = re.compile(
    r'\s*[\(\[]\s*tie\s*[\)\]]\s*$',
    re.IGNORECASE,
)
_TIE_NOTE_RE = re.compile(
    r'^(?:\*?due to a tie\b|there are six nominees\b)',
    re.IGNORECASE,
)
_SUPERIOR_RE = re.compile(
    r'^superior achievement in (?:a |an )?(?P<name>.+)$',
    re.IGNORECASE,
)
_WINNER_PREFIX_RE = re.compile(
    r'^(?:(?:\[tie\]|\(tie\))\s*)?(?:winner(?:\s*\(\s*tie\s*\))?)\s*[:.\-–—]?\s*',
    re.IGNORECASE,
)
_WINNER_SUFFIX_RE = re.compile(
    r'(?:\s*[-–—,:(]\s*)(?:winner(?:\s*\(\s*tie\s*\))?|winner(?:\s*,\s*tie)?|win)\s*\)?\s*$',
    re.IGNORECASE,
)
_WINNER_GLUED_RE = re.compile(
    r'\(\s*winner(?:\s*,\s*tie)?\s*\)\s*$',
    re.IGNORECASE,
)
_STANDALONE_TIE_RE = re.compile(r'^(?:\[tie\]|\(tie\)|tie)$', re.IGNORECASE)
_ALSO_NOMINATED_RE = re.compile(r'^also nominated:?$', re.IGNORECASE)
_NO_AWARD_RE = re.compile(r'^no award\b', re.IGNORECASE)
_NO_NOMINEES_RE = re.compile(r'^no nominees?\b', re.IGNORECASE)
_BULLET_RE = re.compile(r'^(?:[\u2022\u25cf\u25e6\-\*\u25aa]+)\s*')
_EDITED_BY_RE = re.compile(r'\sedited by\s+', re.IGNORECASE)
_BY_SEP_RE = re.compile(r'\s+by\s+', re.IGNORECASE)
_DASH_SPLIT_RE = re.compile(r'\s*[—–]+\s*')
_PUBLISHER_TAIL_RE = re.compile(r'\s*\([^()]*(?:\([^()]*\)[^()]*)*\)$')
_ROLE_RE = re.compile(
    r'^(?P<name>.+?)\s*\(\s*(?P<role>writer|author|artist|editor|'
    r'colorist|letterer|inker)\s*\)$',
    re.IGNORECASE,
)
_EDITOR_SUFFIX_RE = re.compile(
    r'^(?P<body>.*?)(?P<suffix>\s*,?\s*(?:eds?\.|\(\s*editors?\s*\)|'
    r'\(\s*ed\.?\s*\)))\s*$',
    re.IGNORECASE,
)
_LEADING_AND_RE = re.compile(r'^and\s+', re.IGNORECASE)
_THE_SUFFIX_RE = re.compile(r',\s*the$', re.IGNORECASE)
_YEAR_TITLE_HEADING_RE = re.compile(
    r'^\d{4}\s+bram stoker\b',
    re.IGNORECASE,
)
_REST_SEARCH = SITE_ORIGIN + '/wp-json/wp/v2/posts'

# Match-time aliases only. Stored titles remain the census-page strings.
_TITLE_MATCH_ALIASES = {
    (2025, 'young adult novel'): {
        'a girl walks intothe forest': 'a girl walks into the forest',
        'a girl walks into the forest': 'a girl walks into the forest',
    },
}
_AUTHOR_MATCH_ALIASES = {
    (2024, 'short fiction'): {
        'raven jabukowski': 'raven jakubowski',
        'raven jakubowski': 'raven jakubowski',
    },
}


class BramStokerSourceError(RuntimeError):
    """Raised when official Bram Stoker pages are blocked or unusable."""


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    category: str
    status: str
    work_title: str
    work_author: str
    source_url: str


@dataclass(frozen=True, slots=True)
class _IndexSnapshot:
    year_urls: dict[int, str]
    latest_completed_year: int
    winner_urls: dict[int, str]


@dataclass(frozen=True, slots=True)
class _YearSnapshot:
    award_year: int
    state: str
    source_urls: tuple[str, ...]
    records: tuple[_ParsedRecord, ...]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _current_calendar_year() -> int:
    return _utc_now().year


def _collapse_ws(text: str) -> str:
    text = (
        text.replace('\xa0', ' ')
        .replace('\u2009', ' ')
        .replace('\u202f', ' ')
    )
    return re.sub(r'\s+', ' ', text).strip()


def _year_entry_key(year: int) -> str:
    return str(year)


def _census_url(year: int) -> str:
    path = HISTORICAL_CENSUS_PATHS.get(year)
    if path is None:
        raise BramStokerSourceError(
            f'Bram Stoker {year} has no validated census URL'
        )
    return SITE_ORIGIN + path


def _class_tokens(attrs) -> tuple[str, ...]:
    attr = {key: value or '' for key, value in attrs}
    return tuple(part for part in attr.get('class', '').split() if part)


def _official_page_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or '').casefold()
    if host not in _OFFICIAL_HTML_HOSTS:
        return None
    if parsed.scheme != 'https':
        return None
    cleaned = url.split('#', 1)[0].split('?', 1)[0]
    if cleaned.endswith('/') and cleaned.count('/') > 3:
        pass
    return cleaned


def _canonical_census_url(url: str) -> str | None:
    official = _official_page_url(url)
    if official is None:
        return None
    parsed = urlparse(official)
    path = parsed.path or '/'
    if path != '/' and not path.endswith('/'):
        path = path + '/'
    return f'{SITE_ORIGIN}{path}'


def _heading_key(text: str) -> str:
    folded = _collapse_ws(text).casefold()
    folded = folded.replace('\u2019', "'").replace('`', "'")
    folded = (
        folded.replace('\u2013', '-')
        .replace('\u2014', '-')
        .replace('\u2212', '-')
    )
    folded = re.sub(r'\s+', ' ', folded)
    return folded


def _strip_superior_wrapper(text: str) -> str:
    cleaned = _collapse_ws(text)
    match = _SUPERIOR_RE.fullmatch(cleaned)
    if match is not None:
        cleaned = _collapse_ws(match.group('name'))
    cleaned = _TIE_HEADING_TAIL_RE.sub('', cleaned)
    cleaned = (
        cleaned.replace('\u2013', '-')
        .replace('\u2014', '-')
        .replace('\u2212', '-')
    )
    return _collapse_ws(cleaned)


def _heading_kind(text: str) -> str:
    """Return include, exclude, ignore, or unknown."""
    stripped = _strip_superior_wrapper(text)
    key = _heading_key(stripped)
    if not key or key == '#':
        return 'ignore'
    if _YEAR_TITLE_HEADING_RE.match(key):
        return 'ignore'
    if key in _INCLUDED_HEADING_KEYS:
        return 'include'
    if key in _EXCLUDED_HEADING_KEYS:
        return 'exclude'
    for extra in (
        'lifetime achievement award winners',
        'hwa liftetime achievement awards',
        'the richard laymon president',
        'the karen lansdale',
        'seventh annual final frame',
        'final frame horror',
    ):
        if extra in key:
            return 'exclude'
    for prefix in _IGNORE_HEADING_PREFIXES:
        if key.startswith(prefix):
            return 'ignore'
    if key.startswith('superior achievement'):
        return 'unknown'
    if _SUPERIOR_RE.fullmatch(_collapse_ws(text)):
        return 'unknown'
    if len(key) > 80:
        return 'ignore'
    if key.startswith('http'):
        return 'ignore'
    return 'unknown'


def _is_category_heading_text(text: str) -> bool:
    """True when a paragraph is an official category heading, not a work row."""
    heading_kind = _heading_kind(text)
    if heading_kind in {'include', 'exclude'}:
        return True
    cleaned = _TIE_HEADING_TAIL_RE.sub('', _collapse_ws(text))
    return heading_kind == 'unknown' and bool(_SUPERIOR_RE.fullmatch(cleaned))


class _ContentCollector(HTMLParser):
    """Collect title plus entry-content blocks as heading/work text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ''
        self.blocks: list[tuple[str, str]] = []
        self._ignore_depth = 0
        self._capture: str | None = None
        self._parts: list[str] = []
        self._in_title = False
        self._content_depth = 0
        self._content_seen = False

    def _in_content(self) -> bool:
        return self._content_depth > 0

    def handle_starttag(self, tag, attrs):
        if self._ignore_depth:
            if tag not in _VOID_TAGS:
                self._ignore_depth += 1
            return
        if tag in _IGNORE_TAGS:
            self._ignore_depth = 1
            return
        if tag == 'title':
            self._in_title = True
            self._parts = []
            return
        tokens = _class_tokens(attrs)
        entering = any('entry-content' in token for token in tokens)
        if entering:
            self._content_seen = True
        if (entering or self._content_depth) and tag not in _VOID_TAGS:
            self._content_depth += 1
        if tag == 'br' and self._in_content():
            self._flush_text_line()
            return
        if tag in {'h1', 'h2', 'h3', 'h4', 'h5'} and self._in_content():
            self._flush_text_line()
            self._begin_capture('heading')
            return
        if tag in {'p', 'li'} and self._in_content() and self._capture is None:
            self._flush_text_line()
            self._begin_capture('line')

    def handle_endtag(self, tag):
        if self._ignore_depth:
            if tag not in _VOID_TAGS:
                self._ignore_depth -= 1
            return
        if tag == 'title':
            self.title = _collapse_ws(''.join(self._parts))
            self._in_title = False
            self._parts = []
            return
        if self._capture is not None and tag in {
            'h1', 'h2', 'h3', 'h4', 'h5', 'p', 'li',
        }:
            self._finish_capture()
        if self._content_depth and tag not in _VOID_TAGS:
            if tag in {'div', 'article', 'section'}:
                self._flush_text_line()
            self._content_depth -= 1

    def handle_data(self, data):
        if self._ignore_depth:
            return
        if self._in_title:
            self._parts.append(data)
            return
        if not self._in_content():
            return
        if self._capture is None:
            self._begin_capture('line')
        self._parts.append(data)

    def _begin_capture(self, kind: str) -> None:
        if self._capture is not None:
            self._finish_capture()
        self._capture = kind
        self._parts = []

    def _finish_capture(self) -> None:
        kind = self._capture
        text = _collapse_ws(''.join(self._parts))
        self._capture = None
        self._parts = []
        if not kind or not text:
            return
        if kind == 'heading':
            self.blocks.append(('heading', text))
            return
        self.blocks.append(('line', text))

    def _flush_text_line(self) -> None:
        if self._capture == 'line':
            self._finish_capture()

    def close(self) -> None:
        self._flush_text_line()
        super().close()


def _extract_title(html: str) -> str:
    match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
    if match is None:
        return ''
    return _collapse_ws(match.group(1))


def _html_has_award_identity(html: str) -> bool:
    folded = html.casefold()
    return 'bram stoker' in folded and 'horror' in folded


def _page_is_preliminary(title: str, html: str) -> bool:
    title_fold = title.casefold()
    if 'preliminary ballot' in title_fold:
        return True
    if re.search(
        r'<title>[^<]*preliminary ballot[^<]*</title>',
        html,
        re.IGNORECASE,
    ):
        return True
    return False


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize('NFKC', value)
    text = (
        text.replace('\u2018', "'")
        .replace('\u2019', "'")
        .replace('\u201c', '"')
        .replace('\u201d', '"')
        .replace('\u00b4', "'")
        .replace('`', "'")
    )
    text = _collapse_ws(text)
    text = text.casefold()
    text = _INITIALS_SPACE_RE.sub(r'\1.', text)
    return text


def _alias_title(award_year: int, category: str, title: str) -> str:
    table = _TITLE_MATCH_ALIASES.get((award_year, category.casefold()))
    if not table:
        return title
    return table.get(_normalize_text(title), title)


def _alias_author(award_year: int, category: str, author: str) -> str:
    table = _AUTHOR_MATCH_ALIASES.get((award_year, category.casefold()))
    if not table:
        return author
    return table.get(_normalize_text(author), author)


def _titles_match(
    query_title: str,
    record_title: str,
    award_year: int,
    category: str,
) -> bool:
    query_norm = normalize_title_conjunctions(
        _normalize_text(_alias_title(award_year, category, query_title))
    )
    record_norm = normalize_title_conjunctions(
        _normalize_text(_alias_title(award_year, category, record_title))
    )
    return query_norm == record_norm


def _authors_match(
    query_author: str,
    record_author: str,
    award_year: int,
    category: str,
) -> bool:
    query_norm = _normalize_text(
        _alias_author(award_year, category, query_author)
    )
    record_norm = _normalize_text(
        _alias_author(award_year, category, record_author)
    )
    if query_norm == record_norm:
        return True
    # Calibre may store "Name (ed.)" while HWA omitted the suffix.
    query_core = re.sub(r'\s*,?\s*eds?\.?$', '', query_norm).strip()
    record_core = re.sub(r'\s*,?\s*eds?\.?$', '', record_norm).strip()
    return query_core == record_core and bool(query_core)


def _title_key(title: str) -> str:
    return normalize_title_conjunctions(_normalize_text(title))


def _identity_key(record: _ParsedRecord) -> tuple[int, str, str, str]:
    return (
        record.award_year,
        record.category.casefold(),
        _title_key(record.work_title),
        _normalize_text(record.work_author),
    )


def _record_matches(record: _ParsedRecord, title: str, author: str) -> bool:
    return _titles_match(
        title, record.work_title, record.award_year, record.category
    ) and _authors_match(
        author, record.work_author, record.award_year, record.category
    )


def _dedupe_records(records: list[_ParsedRecord]) -> tuple[_ParsedRecord, ...]:
    best: dict[tuple[int, str, str, str], _ParsedRecord] = {}
    order: list[tuple[int, str, str, str]] = []
    for record in records:
        key = _identity_key(record)
        existing = best.get(key)
        if existing is None:
            best[key] = record
            order.append(key)
            continue
        if _STATUS_WEIGHT[record.status] > _STATUS_WEIGHT[existing.status]:
            best[key] = record
    return tuple(best[key] for key in order)


def _classify_year_state(records: tuple[_ParsedRecord, ...]) -> str:
    if any(record.status == 'Winner' for record in records):
        return 'winner'
    if any(record.status == 'Finalist' for record in records):
        return 'finalist'
    return 'absent'


def _looks_winners_only(records: tuple[_ParsedRecord, ...]) -> bool:
    if not records:
        return False
    by_category: dict[str, list[_ParsedRecord]] = {}
    for record in records:
        by_category.setdefault(record.category, []).append(record)
    if len(by_category) < 3:
        return False
    for group in by_category.values():
        if len(group) != 1:
            return False
    return True


def _validate_year_records(
    records: tuple[_ParsedRecord, ...],
    award_year: int,
    state: str,
    *,
    allow_winners_only: bool = False,
) -> None:
    seen: set[tuple[int, str, str, str]] = set()
    for record in records:
        if record.award_year != award_year:
            raise BramStokerSourceError(
                f'Bram Stoker {award_year} contained a mismatched year'
            )
        if record.status not in _PARSED_STATUSES:
            raise BramStokerSourceError(
                f'Bram Stoker {award_year} contained an unsupported status'
            )
        if not record.work_title or not record.work_author:
            raise BramStokerSourceError(
                f'Bram Stoker {award_year} contained an incomplete work'
            )
        if _NO_AWARD_RE.match(record.work_title):
            raise BramStokerSourceError(
                f'Bram Stoker {award_year} contained a No Award work row'
            )
        key = _identity_key(record)
        if key in seen:
            raise BramStokerSourceError(
                f'Bram Stoker {award_year} contained duplicate works in '
                f'{record.category}'
            )
        seen.add(key)
    if state == 'absent':
        if records:
            raise BramStokerSourceError(
                f'Bram Stoker {award_year} absent state contained records'
            )
        return
    if state == 'finalist':
        if any(record.status == 'Winner' for record in records):
            raise BramStokerSourceError(
                f'Bram Stoker {award_year} finalist state contained a Winner'
            )
        if not records:
            raise BramStokerSourceError(
                f'Bram Stoker {award_year} did not contain Finalists'
            )
        return
    if state == 'winner':
        if (
            award_year <= MAX_VERIFIED_YEAR
            and not allow_winners_only
            and _looks_winners_only(records)
        ):
            raise BramStokerSourceError(
                f'Bram Stoker {award_year} winners-only page is not a '
                'complete Final Ballot census'
            )
        if not any(record.status == 'Winner' for record in records):
            raise BramStokerSourceError(
                f'Bram Stoker {award_year} did not contain a Winner'
            )
        return
    raise BramStokerSourceError(
        f'Bram Stoker {award_year} had an unsupported state'
    )


def _strip_presentation_quotes(title: str) -> str:
    text = title.strip()
    if len(text) >= 2 and text[0] in '"“\'' and text[-1] in '"”\'':
        return text[1:-1].strip()
    return text


def _strip_publisher_tail(text: str) -> str:
    cleaned = text.strip()
    previous = None
    while cleaned != previous:
        previous = cleaned
        cleaned = _PUBLISHER_TAIL_RE.sub('', cleaned).strip()
    return cleaned


def _invert_simple_name(name: str) -> str:
    text = _collapse_ws(name)
    if not text:
        return text
    if _THE_SUFFIX_RE.search(text):
        return 'The ' + _THE_SUFFIX_RE.sub('', text).strip()
    if text.count(',') != 1:
        return text
    last, first = (part.strip() for part in text.split(',', 1))
    if not last or not first:
        return text
    if ';' in first or re.search(r'\s+and\s+', first, re.IGNORECASE):
        return text
    if re.fullmatch(r'eds?\.?', first, re.IGNORECASE):
        return text
    return f'{first} {last}'.strip()


def _invert_person_chunk(chunk: str) -> str:
    text = _collapse_ws(chunk)
    role = ''
    match = _ROLE_RE.fullmatch(text)
    if match is not None:
        text = match.group('name').strip()
        role = f' ({_collapse_ws(match.group("role"))})'
    return _invert_simple_name(text) + role


def _normalize_author_credit(raw: str) -> str:
    text = _collapse_ws(raw)
    if not text:
        return text
    suffix = ''
    match = _EDITOR_SUFFIX_RE.fullmatch(text)
    if match is not None:
        text = _collapse_ws(match.group('body').rstrip(' ,'))
        suffix_text = _collapse_ws(match.group('suffix')).lstrip(' ,')
        suffix = f', {suffix_text}' if suffix_text else ''
    if ';' in text:
        chunks = [part.strip() for part in text.split(';') if part.strip()]
        rendered: list[str] = []
        for index, chunk in enumerate(chunks):
            leading_and = bool(_LEADING_AND_RE.match(chunk))
            person = _LEADING_AND_RE.sub('', chunk).strip()
            inverted = _invert_person_chunk(person)
            if index == 0:
                rendered.append(inverted)
            elif leading_and:
                rendered.append(f'; and {inverted}')
            else:
                rendered.append(f'; {inverted}')
        return (''.join(rendered) + suffix).strip()
    pieces = re.split(r'\s+(&|and)\s+', text, flags=re.IGNORECASE)
    if len(pieces) >= 3:
        out: list[str] = []
        for index, piece in enumerate(pieces):
            if index % 2 == 1:
                out.append(f' {piece} ')
            else:
                out.append(_invert_person_chunk(piece))
        return (''.join(out).strip() + suffix).strip()
    return (_invert_person_chunk(text) + suffix).strip()


def _split_winner_marker(text: str) -> tuple[str, bool]:
    cleaned = _collapse_ws(text)
    winner = False
    prefixed = _WINNER_PREFIX_RE.sub('', cleaned)
    if prefixed != cleaned:
        winner = True
        cleaned = _collapse_ws(prefixed)
    glued = _WINNER_GLUED_RE.sub('', cleaned)
    if glued != cleaned:
        winner = True
        cleaned = _collapse_ws(glued)
    suffixed = _WINNER_SUFFIX_RE.sub('', cleaned)
    if suffixed != cleaned:
        winner = True
        cleaned = _collapse_ws(suffixed)
    return cleaned, winner


def _looks_like_title_first(left: str) -> bool:
    folded = left.casefold()
    if folded.startswith(('the ', 'a ', 'an ', '"', '“')):
        return True
    if ' ' in left.strip():
        return True
    return False


def _split_title_author(text: str) -> tuple[str, str] | None:
    cleaned = _collapse_ws(text)
    if not cleaned:
        return None
    edited = _EDITED_BY_RE.split(cleaned, maxsplit=1)
    if len(edited) == 2:
        title = _strip_publisher_tail(_strip_presentation_quotes(edited[0]))
        author = _normalize_author_credit(edited[1])
        if title and author:
            return title, author
    by_parts = _BY_SEP_RE.split(cleaned, maxsplit=1)
    if len(by_parts) == 2 and ' edited by ' not in cleaned.casefold():
        title = _strip_publisher_tail(_strip_presentation_quotes(by_parts[0]))
        author = _normalize_author_credit(by_parts[1])
        if title and author:
            return title, author
    dash_parts = _DASH_SPLIT_RE.split(cleaned, maxsplit=1)
    if len(dash_parts) == 2:
        left = _collapse_ws(dash_parts[0])
        right = _strip_publisher_tail(
            _strip_presentation_quotes(_collapse_ws(dash_parts[1]))
        )
        if left and right:
            return right, _normalize_author_credit(left)
    if ',' in cleaned:
        left, right = cleaned.split(',', 1)
        left = _collapse_ws(left)
        right = _strip_publisher_tail(_collapse_ws(right))
        if left and right:
            if _looks_like_title_first(left):
                title = _strip_presentation_quotes(left)
                author = _normalize_author_credit(right)
                if title and author:
                    return title, author
            author = _normalize_author_credit(left + ', ' + right)
            return None
    return None


def _parse_work_line(text: str) -> tuple[str, str, bool] | None:
    stripped = _BULLET_RE.sub('', _collapse_ws(text))
    if not stripped or _STANDALONE_TIE_RE.fullmatch(stripped):
        return None
    if _ALSO_NOMINATED_RE.fullmatch(stripped):
        return None
    if _TIE_NOTE_RE.match(stripped):
        return None
    if _NO_AWARD_RE.match(stripped):
        return None
    if _NO_NOMINEES_RE.match(stripped):
        return None
    remainder, winner = _split_winner_marker(stripped)
    remainder = remainder.strip(' -:;')
    parsed = _split_title_author(remainder)
    if parsed is None:
        return None
    title, author = parsed
    title = _strip_presentation_quotes(_strip_publisher_tail(title))
    author = _collapse_ws(author)
    if not title or not author:
        return None
    if _NO_AWARD_RE.match(title):
        return None
    return title, author, winner


_AUTHOR_THEN_TITLE_RE = re.compile(
    r'^(?P<author>(?:[A-Z][A-Za-z\'’.\-]*|[A-Z]\.)'
    r'(?:\s+(?:[A-Z]\.|[A-Z][A-Za-z\'’.\-]+|de|del|van|von|jr\.?|'
    r'sr\.?|II|III|IV|&)){0,6})'
    r'\s+(?P<title>[A-Z“\"\'\[].+)$'
)


def _split_author_and_following_title(segment: str) -> tuple[str, bool, str]:
    text = _collapse_ws(segment)
    remainder, winner = _split_winner_marker(text)
    if winner:
        match = _AUTHOR_THEN_TITLE_RE.match(remainder)
        if match is not None:
            return (
                match.group('author').strip().rstrip(','),
                True,
                match.group('title').strip(),
            )
        return remainder, True, ''
    match = _AUTHOR_THEN_TITLE_RE.match(text)
    if match is None:
        return text, False, ''
    return (
        match.group('author').strip().rstrip(','),
        False,
        match.group('title').strip(),
    )


def _split_runon_by_works(blob: str) -> list[str]:
    text = _collapse_ws(blob)
    if not text:
        return []
    if _NO_AWARD_RE.match(text):
        return []
    matches = list(_BY_SEP_RE.finditer(text))
    edited = list(_EDITED_BY_RE.finditer(text))
    seps = edited or matches
    if not seps:
        return [text]
    works: list[str] = []
    first_title = text[: seps[0].start()].strip()
    current_title = first_title
    connector = ' edited by ' if edited else ' by '
    for index, match in enumerate(seps):
        if index + 1 < len(seps):
            between = text[match.end() : seps[index + 1].start()]
            author, winner, next_title = _split_author_and_following_title(
                between
            )
            marker = ', Winner' if winner else ''
            works.append(f'{current_title}{connector}{author}{marker}')
            current_title = next_title
        else:
            tail = text[match.end() :]
            author, winner, leftover = _split_author_and_following_title(tail)
            if leftover:
                current_title = leftover
            marker = ', Winner' if winner else ''
            works.append(f'{current_title}{connector}{author}{marker}')
    return [item for item in works if _collapse_ws(item)]


def _iter_category_work_texts(body: str) -> list[str]:
    text = body.strip()
    if not text:
        return []
    if '\n' in text:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) > 1:
            return lines
        text = lines[0] if lines else text
    if _BY_SEP_RE.search(text) or _EDITED_BY_RE.search(text):
        split = _split_runon_by_works(text)
        if len(split) > 1:
            return split
    return [text]


def _make_record(
    award_year: int,
    category: str,
    status: str,
    title: str,
    author: str,
    source_url: str,
) -> _ParsedRecord | None:
    work_title = _collapse_ws(title)
    work_author = _collapse_ws(author)
    if not work_title or not work_author:
        return None
    return _ParsedRecord(
        award_year=award_year,
        category=category,
        status=status,
        work_title=work_title,
        work_author=work_author,
        source_url=source_url,
    )


def _collect_blocks(html: str) -> tuple[str, list[tuple[str, str]]]:
    parser = _ContentCollector()
    parser.feed(html)
    parser.close()
    title = parser.title or _extract_title(html)
    blocks = parser.blocks
    if not parser._content_seen:
        raise BramStokerSourceError(
            'Bram Stoker page did not contain entry-content'
        )
    return title, blocks


def _parse_year_page(
    html: str,
    award_year: int,
    source_url: str,
) -> tuple[_ParsedRecord, ...]:
    title, blocks = _collect_blocks(html)
    if _page_is_preliminary(title, html):
        return ()
    records: list[_ParsedRecord] = []
    category: str | None = None
    kind = 'ignore'
    also_nominated = False
    body_lines: list[str] = []

    def flush() -> None:
        nonlocal body_lines, category, kind, also_nominated
        if category is None or kind != 'include':
            body_lines = []
            also_nominated = False
            return
        texts = _iter_category_work_texts('\n'.join(body_lines))
        forced_finalist = also_nominated
        parsed_any = False
        skipped_no_award = False
        for item in texts:
            if _ALSO_NOMINATED_RE.fullmatch(_collapse_ws(item)):
                forced_finalist = True
                continue
            if _NO_AWARD_RE.match(_collapse_ws(item)):
                skipped_no_award = True
                continue
            if _NO_NOMINEES_RE.match(_collapse_ws(item)):
                skipped_no_award = True
                continue
            parsed = _parse_work_line(item)
            if parsed is None:
                continue
            work_title, work_author, winner = parsed
            status = 'Winner' if winner and not forced_finalist else 'Finalist'
            if forced_finalist:
                status = 'Finalist'
                if winner:
                    status = 'Winner'
            record = _make_record(
                award_year,
                category,
                status,
                work_title,
                work_author,
                source_url,
            )
            if record is not None:
                records.append(record)
                parsed_any = True
        if (
            body_lines
            and not parsed_any
            and not skipped_no_award
            and any(_collapse_ws(line) for line in body_lines)
        ):
            blob = _collapse_ws(' '.join(body_lines))
            if (
                blob
                and not _NO_AWARD_RE.match(blob)
                and not _NO_NOMINEES_RE.match(blob)
            ):
                raise BramStokerSourceError(
                    f'Bram Stoker {award_year} {category} did not parse works'
                )
        body_lines = []
        also_nominated = False

    for block_kind, text in blocks:
        if block_kind == 'heading' or _is_category_heading_text(text):
            flush()
            heading_kind = _heading_kind(text)
            if heading_kind == 'unknown' and _SUPERIOR_RE.fullmatch(
        _TIE_HEADING_TAIL_RE.sub('', _collapse_ws(text))
    ):
                raise BramStokerSourceError(
                    f'Bram Stoker {award_year} contained an unknown '
                    'Superior Achievement heading'
                )
            kind = heading_kind
            if kind == 'include':
                category = _strip_superior_wrapper(text)
            else:
                category = None
            also_nominated = False
            continue
        if kind == 'include' and category is not None:
            if _ALSO_NOMINATED_RE.fullmatch(_collapse_ws(text)):
                also_nominated = True
            body_lines.append(text)
    flush()
    return _dedupe_records(records)


def _merge_winners_into_ballot(
    ballot: tuple[_ParsedRecord, ...],
    winners: tuple[_ParsedRecord, ...],
) -> tuple[_ParsedRecord, ...]:
    winner_ids = {
        _identity_key(record)
        for record in winners
        if record.status == 'Winner'
    }
    merged: list[_ParsedRecord] = []
    seen = set()
    for record in ballot:
        key = _identity_key(record)
        status = record.status
        if key in winner_ids:
            status = 'Winner'
        updated = record if status == record.status else _ParsedRecord(
            award_year=record.award_year,
            category=record.category,
            status=status,
            work_title=record.work_title,
            work_author=record.work_author,
            source_url=record.source_url,
        )
        merged.append(updated)
        seen.add(key)
    for record in winners:
        key = _identity_key(record)
        if key not in seen and record.status == 'Winner':
            merged.append(record)
            seen.add(key)
    return _dedupe_records(merged)


def _require_year_identity(html: str, final_url: str, award_year: int) -> str:
    official = _canonical_census_url(final_url)
    if official is None:
        raise BramStokerSourceError(
            f'Bram Stoker URL is not official: {final_url}'
        )
    if not _html_has_award_identity(html):
        raise BramStokerSourceError(
            'Bram Stoker page did not identify the Bram Stoker Awards'
        )
    title = _extract_title(html)
    if _page_is_preliminary(title, html):
        raise BramStokerSourceError(
            f'Bram Stoker {award_year} page is a Preliminary Ballot'
        )
    if str(award_year) not in title and str(award_year) not in html[:4000]:
        if str(award_year) not in html:
            raise BramStokerSourceError(
                f'Bram Stoker page did not declare award year {award_year}'
            )
    return official


def _build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )


def _read_response_body(response) -> str:
    return response.read().decode('utf-8', errors='replace')


def _fetch_response(url: str, headers: dict[str, str] | None = None) -> tuple[int, str, str]:
    request = urllib.request.Request(
        url, headers=dict(headers or _BROWSER_HEADERS)
    )
    try:
        with _build_opener().open(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, 'status', None) or response.getcode()
            body = _read_response_body(response)
            final_url = response.geturl() or url
    except urllib.error.HTTPError as exc:
        raise BramStokerSourceError(
            f'Bram Stoker request failed with HTTP {exc.code} for {url}'
        ) from exc
    except urllib.error.URLError as exc:
        raise BramStokerSourceError(
            f'Bram Stoker request failed for {url}: {exc.reason}'
        ) from exc
    if status != 200:
        raise BramStokerSourceError(
            f'Bram Stoker request failed with HTTP {status} for {url}'
        )
    return int(status), body, final_url


def _fetch_html(url: str) -> tuple[str, str]:
    _status, body, final_url = _fetch_response(url)
    return body, final_url


def _fetch_json(url: str):
    _status, body, final_url = _fetch_response(url, headers=_JSON_HEADERS)
    official = _official_page_url(final_url)
    if official is None:
        raise BramStokerSourceError(
            f'Bram Stoker REST URL is not official: {final_url}'
        )
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise BramStokerSourceError(
            'Bram Stoker REST response was not JSON'
        ) from exc
    return payload


_index_snapshot_cache: _IndexSnapshot | None = None
_year_snapshot_cache: dict[int, _YearSnapshot] = {}
_cache_lock = threading.Lock()


def _reset_runtime_state() -> None:
    """Clear in-process Bram Stoker caches. Does not delete disk cache."""
    global _index_snapshot_cache
    with _cache_lock:
        _index_snapshot_cache = None
        _year_snapshot_cache.clear()


def _historical_year_urls() -> dict[int, str]:
    return {
        year: SITE_ORIGIN + path
        for year, path in HISTORICAL_CENSUS_PATHS.items()
    }


def _discover_future_year_urls(
    award_year: int,
) -> tuple[str | None, str | None]:
    """Return (census_url, extra_winner_url) from official REST titles.

    Prefer a Final Ballot census when both a ballot page and a winners page
    exist. The winners page is kept as an extra GET so a 2022-style
    winners-only post can annotate the ballot without discarding Finalists.
    Preliminary Ballot posts are ignored.
    """
    query = urllib.parse.urlencode(
        {
            'search': f'{award_year} Bram Stoker Award',
            'per_page': '20',
            '_fields': 'id,slug,link,title',
        }
    )
    payload = _fetch_json(f'{_REST_SEARCH}?{query}')
    if not isinstance(payload, list):
        return None, None
    winners_url = None
    ballot_url = None
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = ''
        raw_title = item.get('title')
        if isinstance(raw_title, dict):
            title = str(raw_title.get('rendered') or '')
        link = item.get('link')
        if not isinstance(link, str):
            continue
        official = _canonical_census_url(link)
        if official is None:
            continue
        folded = title.casefold()
        if str(award_year) not in folded and str(award_year) not in official:
            continue
        if 'preliminary' in folded:
            continue
        if 'winner' in folded:
            winners_url = official
        elif 'final ballot' in folded:
            ballot_url = official
    if ballot_url and winners_url:
        return ballot_url, winners_url
    return (ballot_url or winners_url), None


def _acquire_live_index() -> _IndexSnapshot:
    year_urls = _historical_year_urls()
    winner_urls: dict[int, str] = {}
    latest = MAX_VERIFIED_YEAR
    calendar_year = _current_calendar_year()
    for year in range(MAX_VERIFIED_YEAR + 1, calendar_year + 1):
        try:
            census_url, extra_winner_url = _discover_future_year_urls(year)
        except BramStokerSourceError:
            continue
        if census_url:
            year_urls[year] = census_url
        if extra_winner_url:
            winner_urls[year] = extra_winner_url
    return _IndexSnapshot(
        year_urls=year_urls,
        latest_completed_year=latest,
        winner_urls=winner_urls,
    )


def _acquire_live_year(
    award_year: int,
    census_url: str,
    *,
    extra_winner_url: str | None = None,
) -> _YearSnapshot:
    if award_year < MIN_SUPPORTED_YEAR:
        raise BramStokerSourceError(
            f'Bram Stoker {award_year} is below the supported floor'
        )
    html, final_url = _fetch_html(census_url)
    official = _require_year_identity(html, final_url, award_year)
    records = _parse_year_page(html, award_year, official)
    source_urls = [official]
    if extra_winner_url:
        try:
            winner_html, winner_final = _fetch_html(extra_winner_url)
            winner_official = _require_year_identity(
                winner_html, winner_final, award_year
            )
            winner_records = _parse_year_page(
                winner_html, award_year, winner_official
            )
            if not _looks_winners_only(winner_records):
                records = winner_records
                source_urls = [winner_official]
            else:
                records = _merge_winners_into_ballot(records, winner_records)
                if winner_official not in source_urls:
                    source_urls.append(winner_official)
        except BramStokerSourceError:
            pass
    state = _classify_year_state(records)
    if (
        award_year <= MAX_VERIFIED_YEAR
        and state != 'winner'
    ):
        raise BramStokerSourceError(
            f'Bram Stoker {award_year} did not contain a validated Winner'
        )
    _validate_year_records(records, award_year, state)
    return _YearSnapshot(
        award_year=award_year,
        state=state,
        source_urls=tuple(source_urls),
        records=records,
    )


def _index_coverage(snapshot: _IndexSnapshot) -> dict:
    return {
        'kind': 'years',
        'latest_completed_year': snapshot.latest_completed_year,
        'year_urls': {
            str(year): url
            for year, url in sorted(snapshot.year_urls.items())
        },
        'winner_urls': {
            str(year): url
            for year, url in sorted(snapshot.winner_urls.items())
        },
    }


def _year_coverage(award_year: int, state: str) -> dict:
    return {'award_year': award_year, 'state': state}


def _year_ttl_seconds(state: str) -> int:
    if state == 'winner':
        return HISTORICAL_CACHE_TTL_SECONDS
    return CURRENT_CACHE_TTL_SECONDS


def _record_to_cache_dict(record: _ParsedRecord) -> dict:
    return {
        'award_year': record.award_year,
        'category': record.category,
        'source_url': record.source_url,
        'status': record.status,
        'work_author': record.work_author,
        'work_title': record.work_title,
    }


def _record_from_cache_dict(data) -> _ParsedRecord | None:
    if not isinstance(data, dict) or set(data) != set(_RECORD_CACHE_FIELDS):
        return None
    award_year = data.get('award_year')
    if isinstance(award_year, bool) or not isinstance(award_year, int):
        return None
    if award_year < MIN_SUPPORTED_YEAR:
        return None
    category = data.get('category')
    status = data.get('status')
    work_title = data.get('work_title')
    work_author = data.get('work_author')
    source_url = data.get('source_url')
    if not isinstance(category, str) or not category.strip() or category != category.strip():
        return None
    if status not in _PARSED_STATUSES:
        return None
    if not isinstance(work_title, str) or not work_title.strip() or work_title != work_title.strip():
        return None
    if not isinstance(work_author, str) or not work_author.strip() or work_author != work_author.strip():
        return None
    if not isinstance(source_url, str) or not source_url.strip() or source_url != source_url.strip():
        return None
    if _official_page_url(source_url) is None:
        return None
    return _ParsedRecord(
        award_year=award_year,
        category=category,
        status=status,
        work_title=work_title,
        work_author=work_author,
        source_url=source_url,
    )


def _year_url_map_from_coverage(raw) -> dict[int, str] | None:
    if not isinstance(raw, dict):
        return None
    year_urls: dict[int, str] = {}
    for key, value in raw.items():
        try:
            year = int(key)
        except (TypeError, ValueError):
            return None
        if year < MIN_SUPPORTED_YEAR:
            return None
        if not isinstance(value, str) or _canonical_census_url(value) is None:
            return None
        year_urls[year] = _canonical_census_url(value) or value
    return year_urls


def _index_from_payload(payload: dict) -> _IndexSnapshot | None:
    coverage = payload.get('coverage')
    if not isinstance(coverage, dict) or set(coverage) != _INDEX_COVERAGE_FIELDS:
        return None
    if coverage.get('kind') != 'years':
        return None
    latest = coverage.get('latest_completed_year')
    if isinstance(latest, bool) or not isinstance(latest, int):
        return None
    if latest < MIN_SUPPORTED_YEAR:
        return None
    year_urls = _year_url_map_from_coverage(coverage.get('year_urls'))
    if not year_urls:
        return None
    winner_urls = _year_url_map_from_coverage(coverage.get('winner_urls'))
    if winner_urls is None:
        return None
    records = payload.get('records')
    if not isinstance(records, list) or records:
        return None
    return _IndexSnapshot(
        year_urls=year_urls,
        latest_completed_year=latest,
        winner_urls=winner_urls,
    )


def _year_from_payload(payload: dict, award_year: int) -> _YearSnapshot | None:
    coverage = payload.get('coverage')
    if not isinstance(coverage, dict) or set(coverage) != _YEAR_COVERAGE_FIELDS:
        return None
    if coverage.get('award_year') != award_year:
        return None
    state = coverage.get('state')
    if state not in _YEAR_STATES:
        return None
    raw_records = payload.get('records')
    if not isinstance(raw_records, list):
        return None
    source_urls = payload.get('source_urls')
    if not isinstance(source_urls, list):
        return None
    urls: list[str] = []
    for item in source_urls:
        if not isinstance(item, str) or _official_page_url(item) is None:
            return None
        urls.append(item)
    if state != 'absent' and not urls:
        return None
    records: list[_ParsedRecord] = []
    for item in raw_records:
        record = _record_from_cache_dict(item)
        if record is None or record.award_year != award_year:
            return None
        records.append(record)
    restored = _dedupe_records(records)
    try:
        _validate_year_records(
            restored,
            award_year,
            state,
            allow_winners_only=award_year > MAX_VERIFIED_YEAR,
        )
    except BramStokerSourceError:
        return None
    return _YearSnapshot(
        award_year=award_year,
        state=state,
        source_urls=tuple(urls),
        records=restored,
    )


def _save_persistent_index(snapshot: _IndexSnapshot) -> None:
    try:
        cache.save_cache_entry(
            SOURCE_KEY,
            INDEX_ENTRY_KIND,
            INDEX_ENTRY_KEY,
            INDEX_CACHE_VERSION,
            records=[],
            source_urls=[SOURCE_HOME_URL],
            coverage=_index_coverage(snapshot),
            ttl_seconds=CURRENT_CACHE_TTL_SECONDS,
        )
    except OSError:
        pass


def _load_persistent_index() -> tuple[_IndexSnapshot, dict] | None:
    payload = cache.load_cache_entry(
        SOURCE_KEY,
        INDEX_ENTRY_KIND,
        INDEX_ENTRY_KEY,
        INDEX_CACHE_VERSION,
    )
    if payload is None:
        return None
    snapshot = _index_from_payload(payload)
    if snapshot is None:
        return None
    return snapshot, payload


def _save_persistent_year(snapshot: _YearSnapshot) -> None:
    try:
        cache.save_cache_entry(
            SOURCE_KEY,
            YEAR_ENTRY_KIND,
            _year_entry_key(snapshot.award_year),
            YEAR_CACHE_VERSION,
            records=[_record_to_cache_dict(record) for record in snapshot.records],
            source_urls=list(snapshot.source_urls),
            coverage=_year_coverage(snapshot.award_year, snapshot.state),
            ttl_seconds=_year_ttl_seconds(snapshot.state),
        )
    except OSError:
        pass


def _load_persistent_year(award_year: int) -> tuple[_YearSnapshot, dict] | None:
    payload = cache.load_cache_entry(
        SOURCE_KEY,
        YEAR_ENTRY_KIND,
        _year_entry_key(award_year),
        YEAR_CACHE_VERSION,
    )
    if payload is None:
        return None
    snapshot = _year_from_payload(payload, award_year)
    if snapshot is None:
        return None
    return snapshot, payload


def _store_index_snapshot(snapshot: _IndexSnapshot) -> None:
    global _index_snapshot_cache
    with _cache_lock:
        _index_snapshot_cache = snapshot


def _store_year_snapshot(snapshot: _YearSnapshot) -> None:
    with _cache_lock:
        _year_snapshot_cache[snapshot.award_year] = snapshot


def _ram_index() -> _IndexSnapshot | None:
    with _cache_lock:
        return _index_snapshot_cache


def _ram_year(award_year: int) -> _YearSnapshot | None:
    with _cache_lock:
        return _year_snapshot_cache.get(award_year)


def _get_index() -> _IndexSnapshot:
    ram = _ram_index()
    if ram is not None:
        return ram
    loaded = _load_persistent_index()
    if loaded is not None:
        snapshot, payload = loaded
        _store_index_snapshot(snapshot)
        calendar_year = _current_calendar_year()
        needs_future = (
            calendar_year > MAX_VERIFIED_YEAR
            and calendar_year not in snapshot.year_urls
            and not cache.cache_is_fresh(payload)
        )
        if not needs_future:
            return snapshot
        try:
            live = _acquire_live_index()
        except Exception:
            return snapshot
        _save_persistent_index(live)
        _store_index_snapshot(live)
        return live
    live = _acquire_live_index()
    _save_persistent_index(live)
    _store_index_snapshot(live)
    return live


def _get_one_year(
    award_year: int,
    census_url: str,
    extra_winner_url: str | None = None,
) -> _YearSnapshot:
    ram = _ram_year(award_year)
    if ram is not None:
        return ram
    loaded = _load_persistent_year(award_year)
    if loaded is not None:
        snapshot, payload = loaded
        if cache.cache_is_fresh(payload) or not cache.try_claim_stale_refresh():
            _store_year_snapshot(snapshot)
            return snapshot
        try:
            live = _acquire_live_year(
                award_year,
                census_url,
                extra_winner_url=extra_winner_url,
            )
        except Exception:
            _store_year_snapshot(snapshot)
            return snapshot
        _save_persistent_year(live)
        _store_year_snapshot(live)
        return live
    live = _acquire_live_year(
        award_year,
        census_url,
        extra_winner_url=extra_winner_url,
    )
    _save_persistent_year(live)
    _store_year_snapshot(live)
    return live


def _years_to_load(index: _IndexSnapshot) -> tuple[int, ...]:
    years = tuple(sorted(index.year_urls))
    calendar_year = _current_calendar_year()
    preferred = tuple(
        year for year in (calendar_year, calendar_year - 1) if year in index.year_urls
    )
    rest = tuple(year for year in years if year not in preferred)
    return preferred + rest


def _get_archive_records() -> tuple[_ParsedRecord, ...]:
    try:
        index = _get_index()
    except BramStokerSourceError:
        index = _IndexSnapshot(
            year_urls=_historical_year_urls(),
            latest_completed_year=MAX_VERIFIED_YEAR,
            winner_urls={},
        )
    collected: list[_ParsedRecord] = []
    for year in _years_to_load(index):
        census_url = index.year_urls.get(year)
        if not census_url:
            continue
        try:
            snapshot = _get_one_year(
                year,
                census_url,
                extra_winner_url=index.winner_urls.get(year),
            )
        except BramStokerSourceError:
            continue
        collected.extend(snapshot.records)
    return tuple(
        sorted(
            collected,
            key=lambda record: (
                record.award_year,
                record.category.casefold(),
                0 if record.status == 'Winner' else 1,
                record.work_title.casefold(),
            ),
        )
    )


def _to_award_result(record: _ParsedRecord) -> AwardResult:
    return AwardResult(
        work_title=record.work_title,
        work_author=record.work_author,
        award_name=AWARD_NAME,
        award_year=record.award_year,
        category=record.category,
        status=record.status,
        rank=None,
        source_name=SOURCE_NAME,
        source_url=record.source_url,
        notes=None,
        identity_kind='work',
    )


def lookup(title: str, author: str, series: str | None = None) -> list[AwardResult]:
    """Look up Bram Stoker Award results.

    series is accepted for AwardSource compatibility and ignored.
    """
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')

    matches: list[AwardResult] = []
    for record in _get_archive_records():
        if _record_matches(record, cleaned_title, cleaned_author):
            matches.append(_to_award_result(record))
    return matches
