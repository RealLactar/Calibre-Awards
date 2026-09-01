"""Official International Prize for Arabic Fiction Winners and Shortlists.

Phase 1 covers populated English prize-year pages on en.arabicfiction.org
from 2020 onward. Longlist is ignored. The 2008-2019 archive has not yet
been migrated to the current site and is out of scope. The 2020 Winner is
taken from the official book profile because that year page has no visible
Winner card. Next.js RSC / framework JSON is not parsed.
"""

from __future__ import annotations

import re
import threading
import unicodedata
import urllib.error
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
SOURCE_KEY = 'ipaf'
AWARD_NAME = 'International Prize for Arabic Fiction'
SOURCE_NAME = 'International Prize for Arabic Fiction'
CATEGORY = 'Fiction'
SITE_ORIGIN = 'https://en.arabicfiction.org'
SOURCE_HOME_URL = SITE_ORIGIN + '/'
PRIZE_YEARS_INDEX_URL = SITE_ORIGIN + '/prize-years'
WINNER_2020_PROFILE_URL = SITE_ORIGIN + '/books/spartan-court'
MIN_SUPPORTED_YEAR = 2020
MAX_VERIFIED_YEAR = 2026
INDEX_CACHE_VERSION = 1
YEAR_CACHE_VERSION = 1
INDEX_ENTRY_KIND = 'index'
INDEX_ENTRY_KEY = 'prize-years'
YEAR_ENTRY_KIND = 'years'
HISTORICAL_CACHE_TTL_SECONDS = 180 * 24 * 60 * 60
CURRENT_CACHE_BASE_TTL_SECONDS = 7 * 24 * 60 * 60
CURRENT_CACHE_REFRESH_OFFSET_SECONDS = 15 * 60 * 60
CURRENT_CACHE_TTL_SECONDS = (
    CURRENT_CACHE_BASE_TTL_SECONDS + CURRENT_CACHE_REFRESH_OFFSET_SECONDS
)
COMPLETED_NONWINNING_SHORTLIST_COUNT = 5
COMPLETED_HONOR_COUNT = 6

_YEAR_STATES = frozenset({'absent', 'shortlisted', 'winner'})
_PARSED_STATUSES = frozenset({'Winner', 'Shortlisted'})
_STATUS_WEIGHT = {
    'Shortlisted': 1,
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
_INDEX_COVERAGE_FIELDS = frozenset({'kind', 'supported_years'})
_YEAR_COVERAGE_FIELDS = frozenset({'award_year', 'state'})
_OFFICIAL_HTML_HOSTS = frozenset({'en.arabicfiction.org'})
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
_IPAF_YEAR_HEADING_RE = re.compile(r'^ipaf\s+(?P<year>20\d{2})$', re.IGNORECASE)
_WINNER_HEADING_RE = re.compile(r'^winner\s+(?P<year>20\d{2})$', re.IGNORECASE)
_PRIZE_WINNER_HEADING_RE = re.compile(
    r'^prize\s+winner\s+(?P<year>20\d{2})$',
    re.IGNORECASE,
)
_YEAR_PATH_RE = re.compile(r'^/prize-years/ipaf-(?P<year>20\d{2})/?$')
_PROFILE_PATH_RE = re.compile(r'^/books/spartan-court/?$')
_SHORTLIST_HEADINGS = frozenset({'shortlist', 'the shortlist'})
_STOP_HEADINGS = frozenset({
    'longlist',
    'the longlist',
    'judges',
    'other prize years',
    'about the author',
    'see more 2020 books',
})
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


class IpafSourceError(RuntimeError):
    """Raised when official IPAF pages are blocked or unusable."""


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
    supported_years: tuple[int, ...]
    source_url: str


@dataclass(frozen=True, slots=True)
class _YearSnapshot:
    award_year: int
    state: str
    source_urls: tuple[str, ...]
    records: tuple[_ParsedRecord, ...]


@dataclass(frozen=True, slots=True)
class _YearPageParse:
    winner: _ParsedRecord | None
    shortlisted: tuple[_ParsedRecord, ...]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _current_calendar_year() -> int:
    """UTC calendar year. Tests may patch _utc_now or this helper."""
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


def _year_page_url(year: int) -> str:
    return f'{SITE_ORIGIN}/prize-years/ipaf-{year}'


def _class_tokens(attrs) -> tuple[str, ...]:
    attr = {key: value or '' for key, value in attrs}
    return tuple(part for part in attr.get('class', '').split() if part)


def _has_class_prefix(tokens: tuple[str, ...], prefix: str) -> bool:
    return any(token.startswith(prefix) for token in tokens)


def _official_page_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or '').casefold()
    if host not in _OFFICIAL_HTML_HOSTS:
        return None
    if parsed.scheme != 'https':
        return None
    return url.split('#', 1)[0]


def _url_path(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or '/'
    if path != '/' and path.endswith('/'):
        path = path[:-1]
    return path


def _path_year(url: str) -> int | None:
    match = _YEAR_PATH_RE.fullmatch(_url_path(url))
    if match is None:
        return None
    return int(match.group('year'))


def _build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )


def _read_response_body(response) -> str:
    return response.read().decode('utf-8', errors='replace')


def _fetch_response(url: str) -> tuple[int, str, str]:
    """Return (status, body, final_url). Non-200 raises."""
    request = urllib.request.Request(url, headers=dict(_BROWSER_HEADERS))
    try:
        with _build_opener().open(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, 'status', None) or response.getcode()
            body = _read_response_body(response)
            final_url = response.geturl() or url
    except urllib.error.HTTPError as exc:
        raise IpafSourceError(
            f'IPAF request failed with HTTP {exc.code} for {url}'
        ) from exc
    except urllib.error.URLError as exc:
        raise IpafSourceError(
            f'IPAF request failed for {url}: {exc.reason}'
        ) from exc
    if status != 200:
        raise IpafSourceError(
            f'IPAF request failed with HTTP {status} for {url}'
        )
    return int(status), body, final_url


def _fetch_html(url: str) -> tuple[str, str]:
    _status, body, final_url = _fetch_response(url)
    return body, final_url


_index_snapshot_cache: _IndexSnapshot | None = None
_year_snapshot_cache: dict[int, _YearSnapshot] = {}
_cache_lock = threading.Lock()


def _reset_runtime_state() -> None:
    """Clear in-process IPAF caches. Does not delete disk cache."""
    global _index_snapshot_cache
    with _cache_lock:
        _index_snapshot_cache = None
        _year_snapshot_cache.clear()


def _extract_title(html: str) -> str:
    match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
    if match is None:
        return ''
    return _collapse_ws(match.group(1))


def _html_has_award_identity(html: str) -> bool:
    folded = html.casefold()
    return (
        'international prize for arabic fiction' in folded
        or 'ipaf' in folded
    )


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


def _titles_match(query_title: str, record_title: str) -> bool:
    query_norm = normalize_title_conjunctions(_normalize_text(query_title))
    record_norm = normalize_title_conjunctions(_normalize_text(record_title))
    return query_norm == record_norm


def _authors_match(query_author: str, record_author: str) -> bool:
    return _normalize_text(query_author) == _normalize_text(record_author)


def _title_key(title: str) -> str:
    return normalize_title_conjunctions(_normalize_text(title))


def _identity_key(record: _ParsedRecord) -> tuple[int, str, str]:
    return (
        record.award_year,
        _title_key(record.work_title),
        _normalize_text(record.work_author),
    )


def _record_matches(record: _ParsedRecord, title: str, author: str) -> bool:
    return _titles_match(title, record.work_title) and _authors_match(
        author, record.work_author
    )


def _dedupe_records(records: list[_ParsedRecord]) -> tuple[_ParsedRecord, ...]:
    best: dict[tuple[int, str, str], _ParsedRecord] = {}
    order: list[tuple[int, str, str]] = []
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
    if any(record.status == 'Shortlisted' for record in records):
        return 'shortlisted'
    return 'absent'


def _is_verified_completed_year(award_year: int) -> bool:
    return MIN_SUPPORTED_YEAR < award_year <= MAX_VERIFIED_YEAR


def _validate_year_records(
    records: tuple[_ParsedRecord, ...],
    award_year: int,
    state: str,
) -> None:
    seen: set[tuple[int, str, str]] = set()
    winners = 0
    shortlisted = 0
    for record in records:
        if record.award_year != award_year:
            raise IpafSourceError(
                f'IPAF {award_year} contained a mismatched year'
            )
        if record.category != CATEGORY:
            raise IpafSourceError(
                f'IPAF {award_year} contained a non-Fiction record'
            )
        if record.status not in _PARSED_STATUSES:
            raise IpafSourceError(
                f'IPAF {award_year} contained an unsupported status'
            )
        if not record.work_title or not record.work_author:
            raise IpafSourceError(
                f'IPAF {award_year} contained an incomplete work'
            )
        key = _identity_key(record)
        if key in seen:
            raise IpafSourceError(
                f'IPAF {award_year} contained duplicate works'
            )
        seen.add(key)
        if record.status == 'Winner':
            winners += 1
        else:
            shortlisted += 1
    if state == 'absent':
        if records:
            raise IpafSourceError(
                f'IPAF {award_year} absent state contained records'
            )
        return
    if state == 'shortlisted':
        if winners:
            raise IpafSourceError(
                f'IPAF {award_year} shortlisted state contained a Winner'
            )
        if award_year == MIN_SUPPORTED_YEAR:
            if shortlisted != COMPLETED_NONWINNING_SHORTLIST_COUNT:
                raise IpafSourceError(
                    f'IPAF {award_year} Shortlisted were not '
                    f'{COMPLETED_NONWINNING_SHORTLIST_COUNT} works'
                )
        elif not shortlisted:
            raise IpafSourceError(
                f'IPAF {award_year} did not contain Shortlisted works'
            )
        return
    if state == 'winner':
        if winners != 1:
            raise IpafSourceError(
                f'IPAF {award_year} did not contain exactly one Winner'
            )
        if award_year <= MAX_VERIFIED_YEAR:
            if shortlisted != COMPLETED_NONWINNING_SHORTLIST_COUNT:
                raise IpafSourceError(
                    f'IPAF {award_year} did not contain '
                    f'{COMPLETED_NONWINNING_SHORTLIST_COUNT} Shortlisted works'
                )
            if winners + shortlisted != COMPLETED_HONOR_COUNT:
                raise IpafSourceError(
                    f'IPAF {award_year} did not contain {COMPLETED_HONOR_COUNT} honors'
                )
        return
    raise IpafSourceError(f'IPAF {award_year} had an unsupported state')


def _make_record(
    award_year: int,
    status: str,
    title: str,
    author: str,
    source_url: str,
) -> _ParsedRecord | None:
    work_title = _collapse_ws(title)
    work_author = _collapse_ws(author)
    if not work_title or not work_author:
        return None
    if work_title != work_title.strip() or work_author != work_author.strip():
        return None
    return _ParsedRecord(
        award_year=award_year,
        category=CATEGORY,
        status=status,
        work_title=work_title,
        work_author=work_author,
        source_url=source_url,
    )


class _YearPageParser(HTMLParser):
    """Collect visible Winner and Shortlist cards from a prize-year page."""

    def __init__(self, award_year: int, source_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.award_year = award_year
        self.source_url = source_url
        self.h1_text = ''
        self.winner_title = ''
        self.winner_author = ''
        self.shortlisted: list[tuple[str, str]] = []
        self.saw_winner_heading = False
        self._ignore_depth = 0
        self._section = ''
        self._capture: str | None = None
        self._parts: list[str] = []
        self._card_title = ''
        self._card_author = ''
        self._in_shortlist_card = False
        self._shortlist_card_depth = 0

    def handle_starttag(self, tag, attrs):
        if self._ignore_depth:
            if tag not in _VOID_TAGS:
                self._ignore_depth += 1
            return
        if tag in _IGNORE_TAGS:
            self._ignore_depth = 1
            return
        tokens = _class_tokens(attrs)
        if _has_class_prefix(tokens, 'OtherPrizeYears'):
            self._section = 'stop'
        if _has_class_prefix(tokens, 'ParagraphLonglistBookBlock'):
            self._section = 'stop'
            self._flush_shortlist_card()
        if tag == 'h1':
            self._begin_capture('h1')
            return
        if _has_class_prefix(tokens, 'ParagraphFeaturedBook_title'):
            self._begin_capture('winner_title')
            return
        if _has_class_prefix(tokens, 'ParagraphFeaturedBook_author'):
            self._begin_capture('winner_author')
            return
        if tag in {'h2', 'h3'}:
            self._begin_capture('heading')
            return
        if self._section != 'shortlist':
            return
        if tag == 'article':
            self._flush_shortlist_card()
            self._in_shortlist_card = True
            self._shortlist_card_depth = 1
            return
        if self._in_shortlist_card and tag not in _VOID_TAGS:
            self._shortlist_card_depth += 1
        if self._in_shortlist_card and _has_class_prefix(
            tokens, 'NodeBookCard_title'
        ):
            self._begin_capture('card_title')
            return
        if self._in_shortlist_card and _has_class_prefix(
            tokens, 'NodeBookCard_authors'
        ):
            self._begin_capture('card_author')
            return

    def handle_endtag(self, tag):
        if self._ignore_depth:
            if tag not in _VOID_TAGS:
                self._ignore_depth -= 1
            return
        if self._capture is not None:
            self._finish_capture()
        if self._in_shortlist_card and tag not in _VOID_TAGS:
            self._shortlist_card_depth -= 1
            if self._shortlist_card_depth <= 0:
                self._flush_shortlist_card()

    def handle_data(self, data):
        if self._ignore_depth or self._capture is None:
            return
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
        if not kind:
            return
        if kind == 'h1':
            self.h1_text = text
            return
        if kind == 'heading':
            self._apply_heading(text)
            return
        if kind == 'winner_title':
            self.winner_title = text
            return
        if kind == 'winner_author':
            self.winner_author = text
            return
        if kind == 'card_title':
            self._card_title = text
            return
        if kind == 'card_author':
            self._card_author = text

    def _apply_heading(self, text: str) -> None:
        folded = text.casefold()
        winner_match = _WINNER_HEADING_RE.fullmatch(folded)
        if winner_match is not None:
            if int(winner_match.group('year')) == self.award_year:
                self._section = 'winner'
                self.saw_winner_heading = True
            else:
                self._section = 'stop'
            return
        if folded in _SHORTLIST_HEADINGS:
            self._section = 'shortlist'
            return
        if folded in _STOP_HEADINGS or folded.startswith('see more '):
            self._section = 'stop'
            self._flush_shortlist_card()
            return
        if _IPAF_YEAR_HEADING_RE.fullmatch(folded) and self._section == 'shortlist':
            self._section = 'stop'
            self._flush_shortlist_card()

    def _flush_shortlist_card(self) -> None:
        if self._card_title and self._card_author:
            self.shortlisted.append((self._card_title, self._card_author))
        self._card_title = ''
        self._card_author = ''
        self._in_shortlist_card = False
        self._shortlist_card_depth = 0

    def close(self) -> None:
        if self._capture is not None:
            self._finish_capture()
        self._flush_shortlist_card()
        super().close()


class _WinnerProfileParser(HTMLParser):
    """Collect the hero Winner identity from the 2020 book profile."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.h1_text = ''
        self.winner_heading = ''
        self.author = ''
        self._ignore_depth = 0
        self._stopped = False
        self._capture: str | None = None
        self._parts: list[str] = []
        self._saw_h1 = False

    def handle_starttag(self, tag, attrs):
        if self._stopped or self._ignore_depth:
            if self._ignore_depth and tag not in _VOID_TAGS:
                self._ignore_depth += 1
            return
        if tag in _IGNORE_TAGS:
            self._ignore_depth = 1
            return
        tokens = _class_tokens(attrs)
        if tag == 'h1':
            self._begin_capture('h1')
            return
        if tag in {'h2', 'h3'}:
            self._begin_capture('heading')
            return
        if _has_class_prefix(tokens, 'NodeBook_author'):
            self._begin_capture('author')
            return

    def handle_endtag(self, tag):
        if self._ignore_depth:
            if tag not in _VOID_TAGS:
                self._ignore_depth -= 1
            return
        if self._capture is not None:
            self._finish_capture()

    def handle_data(self, data):
        if self._stopped or self._ignore_depth or self._capture is None:
            return
        self._parts.append(data)

    def _begin_capture(self, kind: str) -> None:
        if self._capture is not None:
            self._finish_capture()
        if self._stopped:
            return
        self._capture = kind
        self._parts = []

    def _finish_capture(self) -> None:
        kind = self._capture
        text = _collapse_ws(''.join(self._parts))
        self._capture = None
        self._parts = []
        if not kind:
            return
        if kind == 'h1':
            self.h1_text = text
            self._saw_h1 = True
            return
        if kind == 'heading':
            folded = text.casefold()
            if _PRIZE_WINNER_HEADING_RE.fullmatch(folded):
                self.winner_heading = text
                return
            if folded in _STOP_HEADINGS or folded.startswith('see more '):
                self._stopped = True
                return
            if folded.startswith('2020 ') or folded.startswith('about '):
                self._stopped = True
            return
        if kind == 'author' and not self.author:
            self.author = text

    def close(self) -> None:
        if self._capture is not None:
            self._finish_capture()
        super().close()


class _IndexParser(HTMLParser):
    """Collect IPAF year headings and prize-year hrefs from the index."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.h1_text = ''
        self.years: set[int] = set()
        self._ignore_depth = 0
        self._capture: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if self._ignore_depth:
            if tag not in _VOID_TAGS:
                self._ignore_depth += 1
            return
        if tag in _IGNORE_TAGS:
            self._ignore_depth = 1
            return
        attr = {key: value or '' for key, value in attrs}
        href = attr.get('href', '')
        path = urlparse(href).path if href else ''
        year_match = _YEAR_PATH_RE.fullmatch(path.rstrip('/') or path)
        if year_match is not None:
            self.years.add(int(year_match.group('year')))
        tokens = _class_tokens(attrs)
        if tag == 'h1':
            self._begin_capture('h1')
            return
        if tag == 'h2' or _has_class_prefix(tokens, 'NodePrizeYearCard_title'):
            self._begin_capture('heading')

    def handle_endtag(self, tag):
        if self._ignore_depth:
            if tag not in _VOID_TAGS:
                self._ignore_depth -= 1
            return
        if self._capture is not None:
            self._finish_capture()

    def handle_data(self, data):
        if self._ignore_depth or self._capture is None:
            return
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
        if kind == 'h1':
            self.h1_text = text
            return
        if kind == 'heading':
            match = _IPAF_YEAR_HEADING_RE.fullmatch(text.casefold())
            if match is not None:
                self.years.add(int(match.group('year')))

    def close(self) -> None:
        if self._capture is not None:
            self._finish_capture()
        super().close()


def _require_official_html(html: str, url: str) -> str:
    official = _official_page_url(url)
    if official is None:
        raise IpafSourceError(f'IPAF URL is not official: {url}')
    if not _html_has_award_identity(html):
        raise IpafSourceError(
            'IPAF page did not identify the International Prize for Arabic Fiction'
        )
    return official


def _require_year_page_identity(html: str, url: str, award_year: int) -> str:
    official = _require_official_html(html, url)
    path_year = _path_year(official)
    if path_year != award_year:
        raise IpafSourceError(
            f'IPAF {award_year} URL did not remain on the prize-year page'
        )
    parser = _YearPageParser(award_year, official)
    parser.feed(html)
    parser.close()
    h1_match = _IPAF_YEAR_HEADING_RE.fullmatch(parser.h1_text.casefold())
    if h1_match is None or int(h1_match.group('year')) != award_year:
        raise IpafSourceError(
            f'IPAF {award_year} page did not declare prize year {award_year}'
        )
    if not parser.winner_title and not parser.shortlisted:
        raise IpafSourceError(
            f'IPAF {award_year} page did not contain Winner or Shortlist facts'
        )
    return official


def _require_index_identity(html: str, url: str) -> str:
    official = _require_official_html(html, url)
    if _url_path(official) not in {'/prize-years'}:
        raise IpafSourceError('IPAF Prize Years index URL is not official')
    title = _extract_title(html).casefold()
    parser = _IndexParser()
    parser.feed(html)
    parser.close()
    if 'prize years' not in title and parser.h1_text.casefold() != 'prize years':
        raise IpafSourceError('IPAF Prize Years index did not identify itself')
    if not parser.years:
        raise IpafSourceError('IPAF Prize Years index did not list any years')
    return official


def _require_winner_profile_identity(html: str, url: str, award_year: int) -> str:
    official = _require_official_html(html, url)
    if not _PROFILE_PATH_RE.fullmatch(_url_path(official)):
        raise IpafSourceError(
            f'IPAF {award_year} Winner profile URL is not official'
        )
    parser = _WinnerProfileParser()
    parser.feed(html)
    parser.close()
    heading_match = _PRIZE_WINNER_HEADING_RE.fullmatch(
        parser.winner_heading.casefold()
    )
    if heading_match is None or int(heading_match.group('year')) != award_year:
        raise IpafSourceError(
            f'IPAF {award_year} Winner profile did not declare Prize Winner {award_year}'
        )
    if not parser.h1_text or not parser.author:
        raise IpafSourceError(
            f'IPAF {award_year} Winner profile did not contain title and author'
        )
    return official


def _parse_year_page(html: str, award_year: int, source_url: str) -> _YearPageParse:
    parser = _YearPageParser(award_year, source_url)
    parser.feed(html)
    parser.close()
    winner = None
    if parser.saw_winner_heading and parser.winner_title and parser.winner_author:
        winner = _make_record(
            award_year,
            'Winner',
            parser.winner_title,
            parser.winner_author,
            source_url,
        )
    shortlisted: list[_ParsedRecord] = []
    for title, author in parser.shortlisted:
        record = _make_record(
            award_year, 'Shortlisted', title, author, source_url
        )
        if record is not None:
            shortlisted.append(record)
    return _YearPageParse(winner=winner, shortlisted=tuple(shortlisted))


def _parse_winner_profile(
    html: str, award_year: int, source_url: str
) -> _ParsedRecord:
    parser = _WinnerProfileParser()
    parser.feed(html)
    parser.close()
    record = _make_record(
        award_year, 'Winner', parser.h1_text, parser.author, source_url
    )
    if record is None:
        raise IpafSourceError(
            f'IPAF {award_year} Winner profile did not parse a Winner'
        )
    return record


def _parse_index_years(html: str) -> tuple[int, ...]:
    parser = _IndexParser()
    parser.feed(html)
    parser.close()
    years = sorted(
        year for year in parser.years if year >= MIN_SUPPORTED_YEAR
    )
    return tuple(years)


def _supported_years_from_index(index_years: tuple[int, ...]) -> tuple[int, ...]:
    verified = tuple(range(MIN_SUPPORTED_YEAR, MAX_VERIFIED_YEAR + 1))
    extra = tuple(
        year for year in index_years
        if year > MAX_VERIFIED_YEAR
    )
    return verified + extra


def _acquire_live_index() -> _IndexSnapshot:
    html, final_url = _fetch_html(PRIZE_YEARS_INDEX_URL)
    official = _require_index_identity(html, final_url)
    years = _parse_index_years(html)
    if not years:
        raise IpafSourceError('IPAF Prize Years index listed no supported years')
    return _IndexSnapshot(supported_years=years, source_url=official)


def _acquire_live_year(award_year: int) -> _YearSnapshot:
    if award_year < MIN_SUPPORTED_YEAR:
        raise IpafSourceError(f'IPAF {award_year} is below the supported floor')
    year_url = _year_page_url(award_year)
    html, final_url = _fetch_html(year_url)
    official = _require_year_page_identity(html, final_url, award_year)
    parsed = _parse_year_page(html, award_year, official)
    records: list[_ParsedRecord] = list(parsed.shortlisted)
    source_urls = [official]
    winner = parsed.winner
    if award_year == MIN_SUPPORTED_YEAR and winner is None:
        try:
            profile_html, profile_final = _fetch_html(WINNER_2020_PROFILE_URL)
            profile_official = _require_winner_profile_identity(
                profile_html, profile_final, award_year
            )
            winner = _parse_winner_profile(
                profile_html, award_year, profile_official
            )
            source_urls.append(profile_official)
        except IpafSourceError:
            winner = None
    if winner is not None:
        records.append(winner)
    merged = _dedupe_records(records)
    state = _classify_year_state(merged)
    if state == 'absent':
        raise IpafSourceError(
            f'IPAF {award_year} page did not parse Winner or Shortlisted works'
        )
    if (
        _is_verified_completed_year(award_year)
        and state != 'winner'
    ):
        raise IpafSourceError(
            f'IPAF {award_year} did not contain a validated Winner'
        )
    _validate_year_records(merged, award_year, state)
    return _YearSnapshot(
        award_year=award_year,
        state=state,
        source_urls=tuple(source_urls),
        records=merged,
    )


def _index_coverage(supported_years: tuple[int, ...]) -> dict:
    return {
        'kind': 'prize-years',
        'supported_years': list(supported_years),
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
    if category != CATEGORY:
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


def _index_from_payload(payload: dict) -> _IndexSnapshot | None:
    coverage = payload.get('coverage')
    if not isinstance(coverage, dict) or set(coverage) != _INDEX_COVERAGE_FIELDS:
        return None
    if coverage.get('kind') != 'prize-years':
        return None
    raw_years = coverage.get('supported_years')
    if not isinstance(raw_years, list) or not raw_years:
        return None
    years: list[int] = []
    for item in raw_years:
        if isinstance(item, bool) or not isinstance(item, int):
            return None
        if item < MIN_SUPPORTED_YEAR:
            return None
        years.append(item)
    source_urls = payload.get('source_urls')
    if not isinstance(source_urls, list) or len(source_urls) != 1:
        return None
    if source_urls[0] != PRIZE_YEARS_INDEX_URL:
        return None
    records = payload.get('records')
    if not isinstance(records, list) or records:
        return None
    return _IndexSnapshot(
        supported_years=tuple(years),
        source_url=PRIZE_YEARS_INDEX_URL,
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
    if state == 'absent':
        return None
    urls: list[str] = []
    for item in source_urls:
        if not isinstance(item, str) or _official_page_url(item) is None:
            return None
        urls.append(item)
    if not urls:
        return None
    records: list[_ParsedRecord] = []
    for item in raw_records:
        record = _record_from_cache_dict(item)
        if record is None or record.award_year != award_year:
            return None
        records.append(record)
    restored = _dedupe_records(records)
    try:
        _validate_year_records(restored, award_year, state)
    except IpafSourceError:
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
            source_urls=[PRIZE_YEARS_INDEX_URL],
            coverage=_index_coverage(snapshot.supported_years),
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
        if cache.cache_is_fresh(payload) or not cache.try_claim_stale_refresh():
            _store_index_snapshot(snapshot)
            return snapshot
        try:
            live = _acquire_live_index()
        except Exception:
            _store_index_snapshot(snapshot)
            return snapshot
        _save_persistent_index(live)
        _store_index_snapshot(live)
        return live
    live = _acquire_live_index()
    _save_persistent_index(live)
    _store_index_snapshot(live)
    return live


def _get_one_year(award_year: int) -> _YearSnapshot:
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
            live = _acquire_live_year(award_year)
        except Exception:
            _store_year_snapshot(snapshot)
            return snapshot
        _save_persistent_year(live)
        _store_year_snapshot(live)
        return live
    live = _acquire_live_year(award_year)
    _save_persistent_year(live)
    _store_year_snapshot(live)
    return live


def _years_to_load(index_years: tuple[int, ...]) -> tuple[int, ...]:
    return _supported_years_from_index(index_years)


def _get_archive_records() -> tuple[_ParsedRecord, ...]:
    try:
        index = _get_index()
        index_years = index.supported_years
    except IpafSourceError:
        index_years = tuple(range(MIN_SUPPORTED_YEAR, MAX_VERIFIED_YEAR + 1))
    collected: list[_ParsedRecord] = []
    for year in _years_to_load(index_years):
        try:
            snapshot = _get_one_year(year)
        except IpafSourceError:
            continue
        collected.extend(snapshot.records)
    return tuple(
        sorted(
            collected,
            key=lambda record: (
                record.award_year,
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
    """Look up International Prize for Arabic Fiction results.

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
