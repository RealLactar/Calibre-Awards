"""Science Fiction Awards Database Locus Awards source.

The SFADB author page is discovery only. The annual Locus_Awards_YYYY page
establishes the authoritative rank from explicit ``li value`` attributes;
visual list order is not placement. Discovery and annual results are
cross-checked. Qualification is not applied here. Validated author discovery pages and
annual pages may also be loaded from the injected persistent cache.
"""

from __future__ import annotations

import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.parse import quote, unquote, urljoin, urlparse

from .. import cache
from ..matching import normalize_title_conjunctions
from ..model import AwardResult

TIMEOUT_SECONDS = 30
SFADB_ORIGIN = 'https://www.sfadb.com/'
SOURCE_NAME = 'Science Fiction Awards Database'
OFFICIAL_HOSTS = frozenset({'sfadb.com', 'www.sfadb.com'})
CANONICAL_SFADB_HOST = 'www.sfadb.com'

SOURCE_KEY = 'locus'
ANNUAL_ENTRY_KIND = 'annuals'
ANNUAL_CACHE_VERSION = 1
# Temporary uniform annual TTL for Phase L2. Historical vs current-year
# policy and refresh-budget interaction belong to Phase L4.
ANNUAL_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
AUTHOR_ENTRY_KIND = 'authors'
AUTHOR_CACHE_VERSION = 1
# Temporary uniform author TTL for Phase L3. Stale-refresh policy belongs
# to Phase L4.
AUTHOR_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60

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

_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_INITIAL_TOKEN_RE = re.compile(r'^[a-z]\.?$')
_YEAR_HREF_RE = re.compile(r'Locus_Awards_(\d{4})/?$', re.IGNORECASE)
_CANONICAL_ANNUAL_PATH_RE = re.compile(
    r'^/Locus_Awards_(\d{4})$', re.IGNORECASE
)
_PLACE_RE = re.compile(
    r'(\d+)(?:st|nd|rd|th)\s+place(?:\s*\(\s*tie\s*\))?',
    re.IGNORECASE,
)
_DASH_SPLIT_RE = re.compile(r'[\u2014\u2013\u0097]+')
_LEADING_WINNER_LABEL_RE = re.compile(r'^winner:\s*', re.IGNORECASE)
_QUOTE_PAIRS = {
    '"': '"',
    '\u201c': '\u201d',
}

_SUPPORTED_CATEGORY_LABELS = (
    'Novel',
    'Sf Novel',
    'Fantasy Novel',
    'Horror Novel',
    'First Novel',
    'Young Adult Book',
    'Young Adult Novel',
    'Translated Novel',
    'Novella',
    'Novelette',
    'Short Story',
    'Short Fiction',
    'Collection',
)
_SUPPORTED_CATEGORY_KEYS = frozenset(
    label.casefold() for label in _SUPPORTED_CATEGORY_LABELS
)
_DISCOVERY_TO_ANNUAL_CATEGORY = {
    'novel': 'Novel',
    'sf novel': 'Sf Novel',
    'fantasy novel': 'Fantasy Novel',
    'horror novel': 'Horror Novel',
    'horror/dark fantasy novel': 'Horror Novel',
    'dark fantasy/horror novel': 'Horror Novel',
    'first novel': 'First Novel',
    'young adult book': 'Young Adult Book',
    'young adult novel': 'Young Adult Novel',
    'translated novel': 'Translated Novel',
    'novella': 'Novella',
    'novelette': 'Novelette',
    'short story': 'Short Story',
    'short fiction': 'Short Fiction',
    'collection': 'Collection',
}
_DISCOVERY_SUPPORTED_KEYS = frozenset(_DISCOVERY_TO_ANNUAL_CATEGORY)
_TRANSLATED_BY_RE = re.compile(r'translated\s+by', re.IGNORECASE)
_EDITED_BY_RE = re.compile(r'edited\s+by', re.IGNORECASE)
_TRANS_GLITCH_RE = re.compile(r',\s*trans(?:lators?|\d+)\b', re.IGNORECASE)
# Known SFADB labels that are not book-work lookups. Unknown labels fail closed.
_RECOGNIZED_UNSUPPORTED_KEYS = frozenset({
    'anthology',
    'anthology/collection',
    'magazine',
    'publisher',
    'publisher/imprint',
    'book publisher',
    'editor',
    'artist',
    'nonfiction',
    'non-fiction',
    'art book',
    'illustrated and art book',
})


class LocusSourceError(RuntimeError):
    """Raised when SFADB Locus pages cannot be retrieved or validated."""


@dataclass(frozen=True, slots=True)
class _DiscoveryEntry:
    award_year: int
    annual_url: str
    work_title: str
    category_text: str
    rank: int | None
    winner: bool


@dataclass(frozen=True, slots=True)
class _AuthorPage:
    page_url: str
    page_name: str
    entries: tuple[_DiscoveryEntry, ...]


@dataclass(frozen=True, slots=True)
class _AnnualRecord:
    award_year: int
    category: str
    work_title: str
    work_author: str
    linked_authors: tuple[str, ...]
    rank: int
    winner: bool
    tied: bool
    source_url: str


_ANNUAL_RECORD_CACHE_FIELDS = (
    'award_year',
    'category',
    'linked_authors',
    'rank',
    'source_url',
    'tied',
    'winner',
    'work_author',
    'work_title',
)
_DISCOVERY_ENTRY_CACHE_FIELDS = (
    'annual_url',
    'award_year',
    'category_text',
    'rank',
    'winner',
    'work_title',
)
_AUTHOR_PAGE_CACHE_FIELDS = (
    'entries',
    'page_name',
    'page_url',
)


_cache_lock = threading.Lock()
_author_page_cache: dict[str, _AuthorPage] = {}
_annual_page_cache: dict[str, tuple[_AnnualRecord, ...]] = {}


def _reset_runtime_state() -> None:
    """Clear in-process caches. Used by tests. Does not delete disk cache."""
    with _cache_lock:
        _author_page_cache.clear()
        _annual_page_cache.clear()


# ---------------------------------------------------------------------------
# HTTP retrieval
# ---------------------------------------------------------------------------

def _build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )


def _read_response_body(response) -> str:
    charset = None
    headers = getattr(response, 'headers', None)
    if headers is not None:
        getter = getattr(headers, 'get_content_charset', None)
        if callable(getter):
            charset = getter()
    return response.read().decode(charset or 'utf-8', errors='replace')


def _request_html(opener: urllib.request.OpenerDirector, url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers=dict(_BROWSER_HEADERS))
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, 'status', None) or response.getcode()
            body = _read_response_body(response)
            final_url = response.geturl() or url
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return 404, ''
        body = _read_response_body(exc)
        raise LocusSourceError(
            f'Locus request failed with HTTP {exc.code} for {url}'
            + (f': {body[:200].strip()}' if body.strip() else '')
        ) from exc
    except urllib.error.URLError as exc:
        raise LocusSourceError(
            f'Locus request failed for {url}: {exc.reason}'
        ) from exc
    if int(status) not in {200, 404}:
        raise LocusSourceError(
            f'Locus request failed with HTTP {status} for {url}'
        )
    if int(status) == 200 and not _is_sfadb_url(final_url):
        # A 200 that landed off SFADB is not a usable author or annual page.
        raise LocusSourceError(
            f'Locus request redirected off SFADB: {url} -> {final_url}'
        )
    return int(status), body


def _is_sfadb_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'}:
        return False
    host = (parsed.hostname or '').casefold().rstrip('.')
    return host in OFFICIAL_HOSTS


def _author_page_url(slug: str) -> str:
    return urljoin(SFADB_ORIGIN, quote(slug, safe='_-'))


def _absolute_sfadb_url(href: str, base: str) -> str | None:
    joined = urljoin(base, href.strip())
    if not _is_sfadb_url(joined):
        return None
    return joined


def _year_from_locus_href(href: str) -> int | None:
    parsed = urlparse(href.strip())
    path = parsed.path.rstrip('/')
    match = _YEAR_HREF_RE.search(path)
    if match is None:
        return None
    return int(match.group(1))


def _canonical_annual_url(url: str) -> str | None:
    """Return https://www.sfadb.com/Locus_Awards_YYYY, or None if unusable."""
    if not isinstance(url, str) or not url.strip():
        return None
    parsed = urlparse(url.strip())
    if parsed.scheme not in {'http', 'https'}:
        return None
    host = (parsed.hostname or '').casefold().rstrip('.')
    if host not in OFFICIAL_HOSTS:
        return None
    path = parsed.path.rstrip('/')
    if not path.startswith('/'):
        path = '/' + path
    match = _CANONICAL_ANNUAL_PATH_RE.fullmatch(path)
    if match is None:
        return None
    year = int(match.group(1))
    if year <= 0:
        return None
    return f'https://{CANONICAL_SFADB_HOST}/Locus_Awards_{year}'


def _canonical_author_url(url: str) -> str | None:
    """Return https://www.sfadb.com/<slug>, or None if unusable.

    The slug's case and Unicode are preserved. Annual Locus_Awards_YYYY
    paths are not author-page identities.
    """
    if not isinstance(url, str) or not url.strip():
        return None
    parsed = urlparse(url.strip())
    if parsed.scheme not in {'http', 'https'}:
        return None
    host = (parsed.hostname or '').casefold().rstrip('.')
    if host not in OFFICIAL_HOSTS:
        return None
    path = parsed.path.rstrip('/')
    if not path.startswith('/'):
        path = '/' + path
    if path.count('/') != 1:
        return None
    raw_slug = path[1:]
    if not raw_slug:
        return None
    slug = unquote(raw_slug)
    if not slug or slug in {'.', '..'}:
        return None
    if '/' in slug or '\\' in slug or '\x00' in slug:
        return None
    if any(char.isspace() for char in slug):
        return None
    if _CANONICAL_ANNUAL_PATH_RE.fullmatch('/' + slug):
        return None
    return urljoin(SFADB_ORIGIN, quote(slug, safe='_-'))


# ---------------------------------------------------------------------------
# Normalization / matching
# ---------------------------------------------------------------------------

def _collapse_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _ascii_fold(text: str) -> str:
    return ''.join(
        char
        for char in unicodedata.normalize('NFKD', text)
        if not unicodedata.combining(char)
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
        .replace('\u2026', '...')
    )
    text = _collapse_ws(text)
    text = text.casefold()
    text = _INITIALS_SPACE_RE.sub(r'\1.', text)
    return text


def _titles_equivalent(query_title: str, record_title: str) -> bool:
    query_norm = normalize_title_conjunctions(_normalize_text(query_title))
    record_norm = normalize_title_conjunctions(_normalize_text(record_title))
    if query_norm == record_norm:
        return True

    query_has_subtitle = ':' in query_norm
    record_has_subtitle = ':' in record_norm
    if query_has_subtitle == record_has_subtitle:
        return False

    query_base = (
        query_norm.split(':', 1)[0].strip() if query_has_subtitle else query_norm
    )
    record_base = (
        record_norm.split(':', 1)[0].strip() if record_has_subtitle else record_norm
    )
    return bool(query_base) and query_base == record_base


def _authors_equivalent(left: str, right: str) -> bool:
    if _normalize_text(left) == _normalize_text(right):
        return True
    return _normalize_text(_ascii_fold(left)) == _normalize_text(_ascii_fold(right))


def _author_tokens(name: str) -> tuple[str, ...]:
    # Do not use _normalize_text: it glues "M. " onto the next token.
    text = _collapse_ws(_ascii_fold(unicodedata.normalize('NFKC', name)))
    text = text.casefold()
    if not text:
        return ()
    return tuple(text.split())


def _is_initial_token(token: str) -> bool:
    return _INITIAL_TOKEN_RE.fullmatch(token) is not None


def _omitted_middle_initial_candidate(left: str, right: str) -> bool:
    """True when names differ only by omitted interior initials.

    Future bounded source-identity rules such as suffix differences
    (Jr., Sr., II, III, IV) belong at this candidate-matching boundary.
    """
    if _authors_equivalent(left, right):
        return False
    a = _author_tokens(left)
    b = _author_tokens(right)
    if len(a) < 2 or len(b) < 2:
        return False
    if a[0] != b[0] or a[-1] != b[-1]:
        return False
    a_mid = a[1:-1]
    b_mid = b[1:-1]
    a_core = tuple(token for token in a_mid if not _is_initial_token(token))
    b_core = tuple(token for token in b_mid if not _is_initial_token(token))
    if a_core != b_core:
        return False
    a_initials = tuple(token for token in a_mid if _is_initial_token(token))
    b_initials = tuple(token for token in b_mid if _is_initial_token(token))
    if a_initials == b_initials:
        return False
    return _is_token_prefix(a_initials, b_initials) or _is_token_prefix(
        b_initials, a_initials
    )


def _is_token_prefix(short: tuple[str, ...], long: tuple[str, ...]) -> bool:
    return long[: len(short)] == short


def _raw_name_tokens(author: str, *, fold: bool) -> tuple[str, ...]:
    text = unicodedata.normalize('NFKC', author)
    if fold:
        text = _ascii_fold(text)
    text = _collapse_ws(text)
    if not text:
        return ()
    return tuple(text.split())


def _is_raw_initial_token(token: str) -> bool:
    stripped = token.rstrip('.')
    return len(stripped) == 1 and stripped.isalpha()


def _omitted_middle_initial_author_form(author: str, *, fold: bool) -> str | None:
    tokens = _raw_name_tokens(author, fold=fold)
    if len(tokens) < 3:
        return None
    kept = [tokens[0]]
    dropped = False
    for token in tokens[1:-1]:
        if _is_raw_initial_token(token):
            dropped = True
            continue
        kept.append(token)
    kept.append(tokens[-1])
    if not dropped:
        return None
    return ' '.join(kept)


def _author_matches_record(query_author: str, record: _AnnualRecord) -> bool:
    if _authors_equivalent(query_author, record.work_author):
        return True
    return any(
        _authors_equivalent(query_author, name) for name in record.linked_authors
    )


def _author_candidate_matches_record(
    query_author: str, record: _AnnualRecord
) -> bool:
    if _omitted_middle_initial_candidate(query_author, record.work_author):
        return True
    return any(
        _omitted_middle_initial_candidate(query_author, name)
        for name in record.linked_authors
    )


def _record_matches(record: _AnnualRecord, title: str, author: str) -> bool:
    return _titles_equivalent(title, record.work_title) and _author_matches_record(
        author, record
    )


def _slug_from_author(author: str, *, fold: bool) -> str | None:
    text = unicodedata.normalize('NFKC', author)
    if fold:
        text = _ascii_fold(text)
    text = _collapse_ws(text)
    text = text.replace('.', '')
    text = re.sub(r"['’`´‘]", '', text)
    text = text.replace(',', '')
    text = _collapse_ws(text)
    if not text:
        return None
    slug = re.sub(r'_+', '_', text.replace(' ', '_')).strip('_')
    return slug or None


def _author_slug_candidates(author: str) -> tuple[str, ...]:
    folded = _slug_from_author(author, fold=True)
    raw = _slug_from_author(author, fold=False)
    candidates: list[str] = []
    for slug in (folded, raw):
        if slug and slug not in candidates:
            candidates.append(slug)
    omitted_folded = _omitted_middle_initial_author_form(author, fold=True)
    omitted_raw = _omitted_middle_initial_author_form(author, fold=False)
    for form in (omitted_folded, omitted_raw):
        if not form:
            continue
        slug = _slug_from_author(form, fold=False)
        if slug and slug not in candidates:
            candidates.append(slug)
    return tuple(candidates)


def _ordinal(rank: int) -> str:
    if 11 <= rank % 100 <= 13:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(rank % 10, 'th')
    return f'{rank}{suffix}'


def _status_for_rank(rank: int, *, winner: bool) -> str:
    if winner:
        return 'Winner'
    return f'{_ordinal(rank)} place'


def _category_kind(heading: str) -> str | None:
    key = heading.casefold()
    if key in _SUPPORTED_CATEGORY_KEYS:
        return 'supported'
    if key in _RECOGNIZED_UNSUPPORTED_KEYS:
        return 'recognized'
    return None


def _annual_category_for_discovery(category_text: str) -> str | None:
    return _DISCOVERY_TO_ANNUAL_CATEGORY.get(category_text.casefold())


def _discovery_category_supported(category_text: str) -> bool:
    return _annual_category_for_discovery(category_text) is not None


def _earliest_role_cutoff(text: str) -> re.Match[str] | None:
    matches = [
        match
        for match in (
            _TRANSLATED_BY_RE.search(text),
            _EDITED_BY_RE.search(text),
        )
        if match is not None
    ]
    if not matches:
        return None
    return min(matches, key=lambda match: match.start())


def _work_authors_from_links(
    linked: tuple[str, ...], li_text: str
) -> tuple[str, ...]:
    # Cut off translator/editor credits so Collection rows keep work authors.
    collapsed = _collapse_ws(li_text)
    cutoff = _earliest_role_cutoff(collapsed)
    if cutoff is not None:
        before = collapsed[: cutoff.start()]
        return tuple(name for name in linked if name in before)
    if _TRANS_GLITCH_RE.search(collapsed):
        return linked[:1]
    return linked


# ---------------------------------------------------------------------------
# Author-page parsing (discovery only)
# ---------------------------------------------------------------------------

def _extract_leading_quoted_title(text: str) -> str | None:
    """Return a complete leading double-quoted title, or None.

    Activates only when, after leading whitespace, ``text`` begins with an
    ASCII or curly double quote and contains that quote's matching closer.
    Exactly one surrounding pair is stripped; interior quotes are left intact.
    Whitespace inside the pair is collapsed. Single-quoted forms, unmatched
    double quotes, and empty quotes return None.
    """
    stripped = text.lstrip()
    if not stripped:
        return None
    closer = _QUOTE_PAIRS.get(stripped[0])
    if closer is None:
        return None
    close_at = stripped.find(closer, 1)
    if close_at < 0:
        return None
    title = _collapse_ws(stripped[1:close_at])
    if not title:
        return None
    return title


def _extract_annual_quoted_title(li_text: str) -> str | None:
    """Extract a quoted annual-page title, allowing a leading Winner: label.

    Tries a complete leading double-quoted title first. If that fails, removes
    only a leading ``Winner:`` label (whitespace-tolerant, case-insensitive)
    and retries the same helper. Other prefixes are not stripped.
    """
    quoted = _extract_leading_quoted_title(li_text)
    if quoted is not None:
        return quoted
    stripped = li_text.lstrip()
    match = _LEADING_WINNER_LABEL_RE.match(stripped)
    if match is None:
        return None
    return _extract_leading_quoted_title(stripped[match.end() :])


def _parse_discovery_placement(
    text: str, *, winner_markup: bool
) -> tuple[int | None, bool, bool]:
    collapsed = _collapse_ws(text)
    tied = bool(re.search(r'\(\s*tie\s*\)', collapsed, re.IGNORECASE))
    if winner_markup or re.search(r'\bwinner\b', collapsed, re.IGNORECASE):
        return 1, True, tied
    match = _PLACE_RE.search(collapsed)
    if match is None:
        return None, False, tied
    rank = int(match.group(1))
    if rank <= 0:
        return None, False, tied
    return rank, False, tied


def _parse_discovery_category(text: str, title: str) -> str:
    collapsed = _collapse_ws(text)
    remainder = collapsed
    title_collapsed = _collapse_ws(title)
    if title_collapsed and collapsed.casefold().startswith(title_collapsed.casefold()):
        remainder = collapsed[len(title_collapsed):].strip()
    remainder = re.sub(r'^\([^)]*\)\s*', '', remainder)
    remainder = remainder.lstrip(' \t\u2014\u2013\u0097-')
    parts = [
        _collapse_ws(part)
        for part in _DASH_SPLIT_RE.split(remainder)
        if _collapse_ws(part)
    ]
    if parts:
        candidate = parts[0]
        if candidate.casefold() in _DISCOVERY_SUPPORTED_KEYS:
            return candidate
    folded = remainder.casefold()
    for key in sorted(_DISCOVERY_SUPPORTED_KEYS, key=len, reverse=True):
        if re.search(r'(?<![a-z])' + re.escape(key) + r'(?![a-z])', folded):
            return key
    return ''


class _AuthorPageParser(HTMLParser):
    """Parse pagetitle identity and the Locus Awards and Poll discovery list."""

    def __init__(self, page_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.page_name = ''
        self.entries: list[_DiscoveryEntry] = []
        self.locus_header_seen = False
        self.year_links_in_section = 0
        self._in_pagetitle = False
        self._pagetitle_parts: list[str] = []
        self._in_header = False
        self._header_parts: list[str] = []
        self._in_locus_section = False
        self._in_date = False
        self._date_href: str | None = None
        self._in_titlemid = False
        self._title_parts: list[str] = []
        self._titlemid_parts: list[str] = []
        self._in_b = False
        self._winner_markup = False
        self._pending_year: int | None = None
        self._pending_annual_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: (value or '') for name, value in attrs}
        classes = attr.get('class', '').split()
        if tag == 'div' and 'pagetitle' in classes:
            self._in_pagetitle = True
            self._pagetitle_parts = []
        if tag == 'div' and 'awardlistingsectionheader' in classes:
            self._flush_pending()
            self._in_header = True
            self._header_parts = []
        if not self._in_locus_section:
            if tag == 'a' and self._in_date:
                return
            return
        if tag == 'div' and 'dateleftindent' in classes:
            self._flush_pending()
            self._in_date = True
            self._date_href = None
        if tag == 'div' and 'titlemid' in classes:
            self._in_titlemid = True
            self._title_parts = []
            self._titlemid_parts = []
            self._winner_markup = False
        if tag == 'a' and self._in_date and self._date_href is None:
            href = attr.get('href', '').strip()
            if href:
                self._date_href = href
        if tag == 'b' and self._in_titlemid and not self._title_parts:
            self._in_b = True
        if (
            tag == 'span'
            and self._in_titlemid
            and 'win' in classes
        ):
            self._winner_markup = True

    def handle_endtag(self, tag: str) -> None:
        if tag == 'div' and self._in_pagetitle:
            self.page_name = _collapse_ws(''.join(self._pagetitle_parts))
            self._in_pagetitle = False
            self._pagetitle_parts = []
        if tag == 'div' and self._in_header:
            heading = _collapse_ws(''.join(self._header_parts))
            self._in_header = False
            self._header_parts = []
            if 'locus awards and poll' in heading.casefold():
                self.locus_header_seen = True
                self._in_locus_section = True
            elif self._in_locus_section:
                self._flush_pending()
                self._in_locus_section = False
        if tag == 'b' and self._in_b:
            self._in_b = False
        if tag == 'div' and self._in_date:
            self._capture_pending_year()
            self._in_date = False
        if tag == 'div' and self._in_titlemid:
            self._finish_titlemid()
            self._in_titlemid = False

    def handle_data(self, data: str) -> None:
        if self._in_pagetitle:
            self._pagetitle_parts.append(data)
        if self._in_header:
            self._header_parts.append(data)
        if self._in_titlemid:
            self._titlemid_parts.append(data)
            if self._in_b:
                self._title_parts.append(data)

    def _capture_pending_year(self) -> None:
        href = self._date_href
        self._date_href = None
        if not href:
            return
        annual_url = _absolute_sfadb_url(href, self.page_url)
        year = _year_from_locus_href(href)
        if annual_url is None or year is None:
            return
        self.year_links_in_section += 1
        self._pending_year = year
        self._pending_annual_url = annual_url

    def _finish_titlemid(self) -> None:
        bold_title = _collapse_ws(''.join(self._title_parts))
        meta_text = ''.join(self._titlemid_parts)
        quoted_title = _extract_leading_quoted_title(meta_text)
        title = quoted_title if quoted_title is not None else bold_title
        winner_markup = self._winner_markup
        year = self._pending_year
        annual_url = self._pending_annual_url
        self._title_parts = []
        self._titlemid_parts = []
        self._winner_markup = False
        self._pending_year = None
        self._pending_annual_url = None
        if not title or year is None or annual_url is None:
            return
        rank, winner, _tied = _parse_discovery_placement(
            meta_text, winner_markup=winner_markup
        )
        category_text = _parse_discovery_category(meta_text, title)
        self.entries.append(
            _DiscoveryEntry(
                award_year=year,
                annual_url=annual_url,
                work_title=title,
                category_text=category_text,
                rank=rank,
                winner=winner,
            )
        )

    def _flush_pending(self) -> None:
        self._pending_year = None
        self._pending_annual_url = None


def _parse_author_page(html: str, page_url: str) -> _AuthorPage:
    parser = _AuthorPageParser(page_url)
    parser.feed(html)
    parser.close()
    if parser.locus_header_seen and parser.year_links_in_section and not parser.entries:
        raise LocusSourceError(
            f'SFADB author page Locus section was malformed: {page_url}'
        )
    return _AuthorPage(
        page_url=page_url,
        page_name=parser.page_name,
        entries=tuple(parser.entries),
    )


def _author_page_matches_query(page: _AuthorPage, author: str) -> bool:
    if not page.page_name:
        return False
    if _authors_equivalent(author, page.page_name):
        return True
    return _omitted_middle_initial_candidate(author, page.page_name)


def _candidate_author_urls(author: str) -> tuple[str, ...]:
    urls: list[str] = []
    for slug in _author_slug_candidates(author):
        canonical = _canonical_author_url(_author_page_url(slug))
        if canonical is None or canonical in urls:
            continue
        urls.append(canonical)
    return tuple(urls)


def _resolve_author_page(
    opener: urllib.request.OpenerDirector,
    author: str,
) -> _AuthorPage | None:
    """Return a matching author page from RAM, disk, then live slug probing.

    Persistent candidates for every slug are examined before any live HTTP
    so a later successful slug is reused without repeating an earlier 404.
    404s, wrong-person pages, and malformed Locus sections are not stored.
    Fresh and stale-valid author disk are both used immediately in Phase L3,
    without claiming the shared stale-refresh budget.
    """
    candidate_urls = _candidate_author_urls(author)
    if not candidate_urls:
        return None
    for canonical_url in candidate_urls:
        with _cache_lock:
            cached = _author_page_cache.get(canonical_url)
        if cached is None:
            continue
        if _author_page_matches_query(cached, author):
            return cached
    for canonical_url in candidate_urls:
        disk = _load_persistent_author(canonical_url)
        if disk is None:
            continue
        if not _author_page_matches_query(disk, author):
            continue
        with _cache_lock:
            _author_page_cache[canonical_url] = disk
        return disk
    for canonical_url in candidate_urls:
        with _cache_lock:
            cached = _author_page_cache.get(canonical_url)
        if cached is not None:
            continue
        page = _load_live_author_page(opener, canonical_url)
        if page is None:
            continue
        if not _author_page_matches_query(page, author):
            continue
        persistable = _author_page_for_cache(page, canonical_url)
        stored = persistable if persistable is not None else page
        with _cache_lock:
            _author_page_cache[canonical_url] = stored
        if persistable is not None:
            _save_persistent_author(canonical_url, persistable)
        return stored
    return None


def _load_live_author_page(
    opener: urllib.request.OpenerDirector,
    canonical_url: str,
) -> _AuthorPage | None:
    status, body = _request_html(opener, canonical_url)
    if status == 404:
        return None
    if status != 200 or not body.strip():
        raise LocusSourceError(
            f'Locus author page request failed with HTTP {status} for '
            f'{canonical_url}'
        )
    return _parse_author_page(body, canonical_url)


# ---------------------------------------------------------------------------
# Annual-page parsing (authoritative ranks)
# ---------------------------------------------------------------------------

class _AnnualPageParser(HTMLParser):
    """Parse SFADB annual Locus categoryblock / ol / li value lists.

    Rank comes only from the explicit li value attribute. Repeated values
    can be ties. List order is never treated as placement.
    """

    def __init__(self, award_year: int, source_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.award_year = award_year
        self.source_url = source_url
        self.records: list[_AnnualRecord] = []
        self.supported_rank_error: str | None = None
        self._in_category = False
        self._category_parts: list[str] = []
        self._current_category: str | None = None
        self._current_kind: str | None = None
        self._in_ol = False
        self._ol_depth = 0
        self._in_li = False
        self._li_depth = 0
        self._li_value: str | None = None
        self._li_parts: list[str] = []
        self._title_parts: list[str] = []
        self._in_b = False
        self._captured_title = False
        self._author_parts: list[str] = []
        self._in_author_a = False
        self._linked_authors: list[str] = []
        self._winner_markup = False
        self._after_translated_by = False
        self._supported_li_count = 0
        self._supported_ranked_count = 0
        self._category_ranks: dict[str, list[int]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.supported_rank_error is not None:
            return
        attr = {name: (value or '') for name, value in attrs}
        classes = attr.get('class', '').split()
        if tag == 'div' and 'category' in classes and 'categoryblock' not in classes:
            self._in_category = True
            self._category_parts = []
        if tag == 'ol' and self._current_kind is not None:
            if not self._in_ol:
                self._in_ol = True
                self._ol_depth = 1
            else:
                self._ol_depth += 1
        if tag == 'li' and self._in_ol:
            if self._li_depth == 0:
                self._start_li(attr.get('value'))
            self._li_depth += 1
            return
        if not self._in_li:
            return
        if tag == 'span' and 'winner' in classes:
            self._winner_markup = True
        if tag == 'b' and not self._captured_title:
            self._in_b = True
        if tag == 'a' and not self._in_b and not self._after_translated_by:
            href = attr.get('href', '').strip()
            if href:
                self._in_author_a = True
                self._author_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self.supported_rank_error is not None:
            return
        if tag == 'div' and self._in_category:
            heading = _collapse_ws(''.join(self._category_parts))
            self._in_category = False
            self._category_parts = []
            self._current_category = heading or None
            self._current_kind = (
                _category_kind(heading) if heading else None
            )
        if tag == 'b' and self._in_b:
            self._in_b = False
            title = _collapse_ws(''.join(self._title_parts))
            if title:
                self._captured_title = True
        if tag == 'a' and self._in_author_a:
            name = _collapse_ws(''.join(self._author_parts))
            self._in_author_a = False
            self._author_parts = []
            if name:
                self._linked_authors.append(name)
        if tag == 'li' and self._in_ol and self._li_depth:
            self._li_depth -= 1
            if self._li_depth == 0:
                self._finish_li()
        if tag == 'ol' and self._in_ol:
            self._ol_depth -= 1
            if self._ol_depth <= 0:
                self._finish_supported_list()
                self._in_ol = False
                self._ol_depth = 0
                self._current_category = None
                self._current_kind = None

    def handle_data(self, data: str) -> None:
        if self.supported_rank_error is not None:
            return
        if self._in_category:
            self._category_parts.append(data)
        if self._in_li:
            self._li_parts.append(data)
            if self._in_b:
                self._title_parts.append(data)
            if self._in_author_a:
                self._author_parts.append(data)
            if (
                not self._in_b
                and not self._after_translated_by
                and _TRANSLATED_BY_RE.search(data)
            ):
                self._after_translated_by = True

    def _start_li(self, value: str | None) -> None:
        self._in_li = True
        self._li_value = value
        self._li_parts = []
        self._title_parts = []
        self._captured_title = False
        self._author_parts = []
        self._in_author_a = False
        self._linked_authors = []
        self._winner_markup = False
        self._after_translated_by = False
        self._in_b = False

    def _parse_rank(self, raw: str | None) -> int | None:
        if raw is None:
            return None
        text = raw.strip()
        if not text or not re.fullmatch(r'[0-9]+', text):
            return None
        rank = int(text)
        if rank <= 0:
            return None
        return rank

    def _finish_li(self) -> None:
        in_li = self._in_li
        raw_value = self._li_value
        li_text = ''.join(self._li_parts)
        quoted_title = _extract_annual_quoted_title(li_text)
        bold_title = _collapse_ws(''.join(self._title_parts))
        title = quoted_title if quoted_title is not None else bold_title
        linked = tuple(self._linked_authors)
        winner = self._winner_markup
        kind = self._current_kind
        category = self._current_category
        self._in_li = False
        self._li_value = None
        self._li_parts = []
        self._title_parts = []
        self._captured_title = False
        self._linked_authors = []
        self._winner_markup = False
        if not in_li or kind is None or not category:
            return
        rank = self._parse_rank(raw_value)
        if kind == 'supported':
            self._supported_li_count += 1
            if rank is None:
                self.supported_rank_error = (
                    'SFADB Locus annual page has a supported category '
                    f'item without an explicit positive li value: {self.source_url}'
                )
                return
            self._supported_ranked_count += 1
        linked = _work_authors_from_links(linked, li_text)
        if rank is None or not title or not linked:
            return
        if winner and rank != 1:
            self.supported_rank_error = (
                'SFADB Locus annual page marked Winner on a non-first '
                f'placement: {self.source_url}'
            )
            return
        if rank == 1 and kind == 'supported' and not winner:
            self.supported_rank_error = (
                'SFADB Locus annual page rank 1 is missing Winner markup: '
                f'{self.source_url}'
            )
            return
        tied = bool(re.search(r'\(\s*tie\s*\)', li_text, re.IGNORECASE))
        work_author = ' & '.join(linked)
        record = _AnnualRecord(
            award_year=self.award_year,
            category=category,
            work_title=title,
            work_author=work_author,
            linked_authors=linked,
            rank=rank,
            winner=winner,
            tied=tied,
            source_url=self.source_url,
        )
        self.records.append(record)
        self._category_ranks.setdefault(category, []).append(rank)

    def _finish_supported_list(self) -> None:
        if self._current_kind != 'supported':
            self._supported_li_count = 0
            self._supported_ranked_count = 0
            return
        if self._supported_li_count and not self._supported_ranked_count:
            self.supported_rank_error = (
                'SFADB Locus annual page supported category has no usable '
                f'explicit ranks: {self.source_url}'
            )
        self._supported_li_count = 0
        self._supported_ranked_count = 0

    def mark_shared_value_ties(self) -> None:
        shared = {
            category
            for category, ranks in self._category_ranks.items()
            if len(ranks) != len(set(ranks))
        }
        if not shared:
            return
        tied_records = []
        for record in self.records:
            if record.category in shared:
                counts = self._category_ranks[record.category].count(record.rank)
                if counts > 1:
                    tied_records.append(
                        _AnnualRecord(
                            award_year=record.award_year,
                            category=record.category,
                            work_title=record.work_title,
                            work_author=record.work_author,
                            linked_authors=record.linked_authors,
                            rank=record.rank,
                            winner=record.winner,
                            tied=True,
                            source_url=record.source_url,
                        )
                    )
                    continue
            tied_records.append(record)
        self.records = tied_records


def _parse_annual_page(
    html: str, award_year: int, source_url: str
) -> tuple[_AnnualRecord, ...]:
    parser = _AnnualPageParser(award_year, source_url)
    parser.feed(html)
    parser.close()
    if parser.supported_rank_error:
        raise LocusSourceError(parser.supported_rank_error)
    parser.mark_shared_value_ties()
    supported = [record for record in parser.records if record.category.casefold() in _SUPPORTED_CATEGORY_KEYS]
    if not supported:
        recognized = any(
            record.category.casefold() in _RECOGNIZED_UNSUPPORTED_KEYS
            for record in parser.records
        )
        if not recognized:
            raise LocusSourceError(
                'SFADB Locus annual page did not contain recognizable '
                f'category structure: {source_url}'
            )
    seen: set[tuple[int, str, str, str, int]] = set()
    unique: list[_AnnualRecord] = []
    for record in parser.records:
        if record.category.casefold() not in _SUPPORTED_CATEGORY_KEYS:
            continue
        key = (
            record.award_year,
            record.category,
            record.work_title.casefold(),
            record.work_author.casefold(),
            record.rank,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return tuple(unique)


# ---------------------------------------------------------------------------
# Persistent annual-page cache (Phase L2)
# ---------------------------------------------------------------------------

def _award_year_from_canonical_annual_url(url: str) -> int | None:
    canonical = _canonical_annual_url(url)
    if canonical is None:
        return None
    return int(canonical.rsplit('_', 1)[-1])


def _is_positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _stripped_nonempty_str(value) -> str | None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        return None
    return value


def _annual_record_to_cache_dict(record: _AnnualRecord) -> dict:
    return {
        'award_year': record.award_year,
        'category': record.category,
        'linked_authors': list(record.linked_authors),
        'rank': record.rank,
        'source_url': record.source_url,
        'tied': record.tied,
        'winner': record.winner,
        'work_author': record.work_author,
        'work_title': record.work_title,
    }


def _linked_authors_from_cache(value) -> tuple[str, ...] | None:
    if isinstance(value, (str, bytes, bytearray)):
        return None
    if not isinstance(value, (list, tuple)) or not value:
        return None
    names: list[str] = []
    for item in value:
        name = _stripped_nonempty_str(item)
        if name is None:
            return None
        names.append(name)
    return tuple(names)


def _annual_record_from_cache_dict(data) -> _AnnualRecord | None:
    if not isinstance(data, dict) or set(data) != set(_ANNUAL_RECORD_CACHE_FIELDS):
        return None
    award_year = data.get('award_year')
    if not _is_positive_int(award_year):
        return None
    category = data.get('category')
    if category not in _SUPPORTED_CATEGORY_LABELS:
        return None
    work_title = _stripped_nonempty_str(data.get('work_title'))
    work_author = _stripped_nonempty_str(data.get('work_author'))
    if work_title is None or work_author is None:
        return None
    linked_authors = _linked_authors_from_cache(data.get('linked_authors'))
    if linked_authors is None:
        return None
    if work_author != ' & '.join(linked_authors):
        return None
    rank = data.get('rank')
    if not _is_positive_int(rank):
        return None
    winner = data.get('winner')
    tied = data.get('tied')
    if not isinstance(winner, bool) or not isinstance(tied, bool):
        return None
    if winner and rank != 1:
        return None
    if rank == 1 and not winner:
        return None
    source_url = _stripped_nonempty_str(data.get('source_url'))
    if source_url is None:
        return None
    canonical_source = _canonical_annual_url(source_url)
    if canonical_source is None or canonical_source != source_url:
        return None
    return _AnnualRecord(
        award_year=award_year,
        category=category,
        work_title=work_title,
        work_author=work_author,
        linked_authors=linked_authors,
        rank=rank,
        winner=winner,
        tied=tied,
        source_url=source_url,
    )


def _annual_coverage(
    records: tuple[_AnnualRecord, ...],
    award_year: int,
) -> dict:
    ranks = [record.rank for record in records]
    return {
        'award_year': award_year,
        'categories': sorted({record.category for record in records}),
        'max_rank': max(ranks) if ranks else None,
        'min_rank': min(ranks) if ranks else None,
        'record_count': len(records),
        'tied_record_count': sum(1 for record in records if record.tied),
        'winner_count': sum(1 for record in records if record.winner),
    }


def _validate_cached_annual_records(
    records: tuple[_AnnualRecord, ...],
    canonical_url: str,
) -> bool:
    expected_year = _award_year_from_canonical_annual_url(canonical_url)
    if expected_year is None:
        return False
    seen: set[tuple[int, str, str, str, int]] = set()
    for record in records:
        if record.award_year != expected_year:
            return False
        if record.source_url != canonical_url:
            return False
        key = (
            record.award_year,
            record.category,
            record.work_title.casefold(),
            record.work_author.casefold(),
            record.rank,
        )
        if key in seen:
            return False
        seen.add(key)
    return True


def _records_from_annual_cache_payload(
    payload: dict,
    canonical_url: str,
) -> tuple[_AnnualRecord, ...] | None:
    if payload.get('source_urls') != [canonical_url]:
        return None
    raw_records = payload.get('records')
    if not isinstance(raw_records, list):
        return None
    records: list[_AnnualRecord] = []
    for item in raw_records:
        record = _annual_record_from_cache_dict(item)
        if record is None:
            return None
        records.append(record)
    restored = tuple(records)
    if not _validate_cached_annual_records(restored, canonical_url):
        return None
    return restored


def _load_persistent_annual(
    canonical_url: str,
) -> tuple[_AnnualRecord, ...] | None:
    payload = cache.load_cache_entry(
        SOURCE_KEY,
        ANNUAL_ENTRY_KIND,
        canonical_url,
        ANNUAL_CACHE_VERSION,
    )
    if payload is None:
        return None
    return _records_from_annual_cache_payload(payload, canonical_url)


def _save_persistent_annual(
    canonical_url: str,
    records: tuple[_AnnualRecord, ...],
) -> None:
    award_year = _award_year_from_canonical_annual_url(canonical_url)
    if award_year is None:
        return
    try:
        cache.save_cache_entry(
            SOURCE_KEY,
            ANNUAL_ENTRY_KIND,
            canonical_url,
            ANNUAL_CACHE_VERSION,
            records=[
                _annual_record_to_cache_dict(record) for record in records
            ],
            source_urls=[canonical_url],
            coverage=_annual_coverage(records, award_year),
            ttl_seconds=ANNUAL_CACHE_TTL_SECONDS,
        )
    except OSError:
        pass


def _load_live_annual(
    opener: urllib.request.OpenerDirector,
    canonical_url: str,
) -> tuple[_AnnualRecord, ...]:
    award_year = _award_year_from_canonical_annual_url(canonical_url)
    if award_year is None:
        raise LocusSourceError(
            f'SFADB Locus annual URL is not a usable year page: {canonical_url}'
        )
    status, body = _request_html(opener, canonical_url)
    if status != 200 or not body.strip():
        raise LocusSourceError(
            'Locus annual page request failed with HTTP '
            f'{status} for {canonical_url}'
        )
    return _parse_annual_page(body, award_year, canonical_url)


def _get_annual_records(
    opener: urllib.request.OpenerDirector,
    annual_url: str,
) -> tuple[_AnnualRecord, ...]:
    """Return parsed annual records: RAM, then disk, then live parse.

    Disk is used only after the existing annual parse/validation succeeds
    on a previous live load. Fresh and stale-valid annual disk are both
    used immediately in Phase L2, with zero annual HTTP and without
    claiming the shared stale-refresh budget. That stale behavior is
    temporary until Phase L4. A missing or invalid disk entry still
    performs the required live annual fetch.
    """
    canonical_url = _canonical_annual_url(annual_url)
    if canonical_url is None:
        raise LocusSourceError(
            f'SFADB Locus annual URL is not a usable year page: {annual_url}'
        )
    with _cache_lock:
        cached = _annual_page_cache.get(canonical_url)
    if cached is not None:
        return cached
    disk = _load_persistent_annual(canonical_url)
    if disk is not None:
        with _cache_lock:
            _annual_page_cache[canonical_url] = disk
        return disk
    records = _load_live_annual(opener, canonical_url)
    with _cache_lock:
        _annual_page_cache[canonical_url] = records
    _save_persistent_annual(canonical_url, records)
    return records


def _discovery_identity(entry: _DiscoveryEntry) -> tuple:
    return (
        entry.award_year,
        entry.annual_url,
        entry.work_title.casefold(),
        entry.category_text.casefold(),
        entry.rank,
        entry.winner,
    )


def _discovery_entry_to_cache_dict(entry: _DiscoveryEntry) -> dict:
    return {
        'annual_url': entry.annual_url,
        'award_year': entry.award_year,
        'category_text': entry.category_text,
        'rank': entry.rank,
        'winner': entry.winner,
        'work_title': entry.work_title,
    }


def _discovery_entry_from_cache_dict(data) -> _DiscoveryEntry | None:
    if not isinstance(data, dict) or set(data) != set(_DISCOVERY_ENTRY_CACHE_FIELDS):
        return None
    award_year = data.get('award_year')
    if not _is_positive_int(award_year):
        return None
    annual_url = _stripped_nonempty_str(data.get('annual_url'))
    if annual_url is None:
        return None
    canonical_annual = _canonical_annual_url(annual_url)
    if canonical_annual is None or canonical_annual != annual_url:
        return None
    annual_year = _award_year_from_canonical_annual_url(canonical_annual)
    if annual_year != award_year:
        return None
    work_title = _stripped_nonempty_str(data.get('work_title'))
    if work_title is None:
        return None
    category_text = data.get('category_text')
    if not isinstance(category_text, str) or category_text != category_text.strip():
        return None
    rank = data.get('rank')
    if rank is not None and not _is_positive_int(rank):
        return None
    winner = data.get('winner')
    if not isinstance(winner, bool):
        return None
    if winner and rank != 1:
        return None
    return _DiscoveryEntry(
        award_year=award_year,
        annual_url=canonical_annual,
        work_title=work_title,
        category_text=category_text,
        rank=rank,
        winner=winner,
    )


def _author_page_to_cache_dict(page: _AuthorPage) -> dict:
    return {
        'entries': [
            _discovery_entry_to_cache_dict(entry) for entry in page.entries
        ],
        'page_name': page.page_name,
        'page_url': page.page_url,
    }


def _author_page_from_cache_dict(
    data, canonical_url: str
) -> _AuthorPage | None:
    if not isinstance(data, dict) or set(data) != set(_AUTHOR_PAGE_CACHE_FIELDS):
        return None
    page_url = _stripped_nonempty_str(data.get('page_url'))
    page_name = _stripped_nonempty_str(data.get('page_name'))
    if page_url is None or page_name is None:
        return None
    if _canonical_author_url(page_url) != page_url or page_url != canonical_url:
        return None
    raw_entries = data.get('entries')
    if not isinstance(raw_entries, list):
        return None
    entries: list[_DiscoveryEntry] = []
    seen: set[tuple] = set()
    for item in raw_entries:
        entry = _discovery_entry_from_cache_dict(item)
        if entry is None:
            return None
        key = _discovery_identity(entry)
        if key in seen:
            return None
        seen.add(key)
        entries.append(entry)
    return _AuthorPage(
        page_url=page_url,
        page_name=page_name,
        entries=tuple(entries),
    )


def _author_page_for_cache(
    page: _AuthorPage, canonical_url: str
) -> _AuthorPage | None:
    """Return a persistable author page with canonical URLs, or None."""
    if _canonical_author_url(canonical_url) != canonical_url:
        return None
    page_name = _stripped_nonempty_str(page.page_name)
    if page_name is None:
        return None
    entries: list[_DiscoveryEntry] = []
    seen: set[tuple] = set()
    for entry in page.entries:
        canonical_annual = _canonical_annual_url(entry.annual_url)
        if canonical_annual is None:
            return None
        rebuilt = _DiscoveryEntry(
            award_year=entry.award_year,
            annual_url=canonical_annual,
            work_title=entry.work_title,
            category_text=entry.category_text,
            rank=entry.rank,
            winner=entry.winner,
        )
        if _discovery_entry_from_cache_dict(
            _discovery_entry_to_cache_dict(rebuilt)
        ) is None:
            return None
        key = _discovery_identity(rebuilt)
        if key in seen:
            return None
        seen.add(key)
        entries.append(rebuilt)
    return _AuthorPage(
        page_url=canonical_url,
        page_name=page_name,
        entries=tuple(entries),
    )


def _author_coverage(page: _AuthorPage) -> dict:
    years = [entry.award_year for entry in page.entries]
    annuals = {entry.annual_url for entry in page.entries}
    return {
        'annual_url_count': len(annuals),
        'entry_count': len(page.entries),
        'max_year': max(years) if years else None,
        'min_year': min(years) if years else None,
        'page_name': page.page_name,
    }


def _page_from_author_cache_payload(
    payload: dict, canonical_url: str
) -> _AuthorPage | None:
    if payload.get('source_urls') != [canonical_url]:
        return None
    raw_records = payload.get('records')
    if not isinstance(raw_records, list) or len(raw_records) != 1:
        return None
    return _author_page_from_cache_dict(raw_records[0], canonical_url)


def _load_persistent_author(canonical_url: str) -> _AuthorPage | None:
    payload = cache.load_cache_entry(
        SOURCE_KEY,
        AUTHOR_ENTRY_KIND,
        canonical_url,
        AUTHOR_CACHE_VERSION,
    )
    if payload is None:
        return None
    return _page_from_author_cache_payload(payload, canonical_url)


def _save_persistent_author(canonical_url: str, page: _AuthorPage) -> None:
    persistable = _author_page_for_cache(page, canonical_url)
    if persistable is None:
        return
    try:
        cache.save_cache_entry(
            SOURCE_KEY,
            AUTHOR_ENTRY_KIND,
            canonical_url,
            AUTHOR_CACHE_VERSION,
            records=[_author_page_to_cache_dict(persistable)],
            source_urls=[canonical_url],
            coverage=_author_coverage(persistable),
            ttl_seconds=AUTHOR_CACHE_TTL_SECONDS,
        )
    except OSError:
        pass


def _to_award_result(
    record: _AnnualRecord,
    *,
    query_author: str,
    identity_confirmation_required: bool = False,
) -> AwardResult:
    identity_note = None
    if identity_confirmation_required:
        identity_note = (
            f'Source lists the author as {record.work_author}; '
            f'Calibre lists {query_author}.'
        )
    return AwardResult(
        work_title=record.work_title,
        work_author=record.work_author,
        award_name='Locus Award',
        award_year=record.award_year,
        category=record.category,
        status=_status_for_rank(record.rank, winner=record.winner),
        rank=record.rank,
        source_name=SOURCE_NAME,
        source_url=record.source_url,
        notes='tie' if record.tied else None,
        identity_confirmation_required=identity_confirmation_required,
        source_identity_note=identity_note,
    )


# ---------------------------------------------------------------------------
# Public lookup
# ---------------------------------------------------------------------------

def lookup(title: str, author: str, series: str | None = None) -> list[AwardResult]:
    """Look up Locus Award book-category results from SFADB."""
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')

    opener = _build_opener()
    page = _resolve_author_page(opener, cleaned_author)
    if page is None:
        return []

    discoveries = [
        entry
        for entry in page.entries
        if _titles_equivalent(cleaned_title, entry.work_title)
        and _discovery_category_supported(entry.category_text)
    ]
    if not discoveries:
        return []

    matches: list[AwardResult] = []
    seen: set[tuple[int, str, str, str, int, str]] = set()
    for entry in discoveries:
        records = _get_annual_records(opener, entry.annual_url)
        expected_category = _annual_category_for_discovery(entry.category_text)
        if expected_category is None:
            continue
        title_on_annual = [
            record
            for record in records
            if record.category == expected_category
            and _titles_equivalent(cleaned_title, record.work_title)
        ]
        if not title_on_annual:
            raise LocusSourceError(
                'SFADB author-page Locus entry was not present on the '
                f'annual results page: {entry.annual_url}'
            )
        exact = [
            record
            for record in title_on_annual
            if _author_matches_record(cleaned_author, record)
        ]
        candidate = []
        if not exact:
            candidate = [
                record
                for record in title_on_annual
                if _author_candidate_matches_record(cleaned_author, record)
            ]
        found = exact or candidate
        confirmation_required = bool(candidate)
        if not found:
            continue
        for record in found:
            if entry.rank is not None and record.rank != entry.rank:
                raise LocusSourceError(
                    'SFADB author-page Locus placement disagreed with the '
                    f'annual page: discovery={entry.rank} annual={record.rank} '
                    f'url={entry.annual_url}'
                )
            if entry.winner and not record.winner:
                raise LocusSourceError(
                    'SFADB author-page Locus winner disagreed with the '
                    f'annual page: {entry.annual_url}'
                )
            key = (
                record.award_year,
                record.category,
                record.work_title.casefold(),
                record.work_author.casefold(),
                record.rank,
                record.source_url,
            )
            if key in seen:
                continue
            seen.add(key)
            matches.append(
                _to_award_result(
                    record,
                    query_author=cleaned_author,
                    identity_confirmation_required=confirmation_required,
                )
            )
    matches.sort(
        key=lambda result: (
            result.award_year or 0,
            result.category or '',
            result.rank or 0,
            result.work_title.casefold(),
        )
    )
    return matches
