"""Official Pulitzer Prize website source (Fiction and Novel categories)."""

from __future__ import annotations

import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.parse import urljoin, urlparse

from ..matching import normalize_title_conjunctions
from ..model import AwardResult

TIMEOUT_SECONDS = 30
FICTION_URL = 'https://www.pulitzer.org/prize-winners-by-category/219'
NOVEL_URL = 'https://www.pulitzer.org/prize-winners-by-category/261'
_DETAIL_ORIGIN = 'https://www.pulitzer.org'

_CATEGORY_URLS = (
    ('Fiction', FICTION_URL),
    ('Novel', NOVEL_URL),
)

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

_YEAR_HREF_RE = re.compile(r'/prize-winners-by-year/(\d{4})(?:/|$|\?)')
_CITATION_RE = re.compile(
    r'^(?P<title>.+?),\s*by\s+(?P<author>.+?)(?:\s*\((?P<publisher>.*)\))?\s*$',
    re.IGNORECASE | re.DOTALL,
)
_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_DETAIL_SLUG_RE = re.compile(r'^[0-9A-Za-z][0-9A-Za-z_-]*$')
_OFFICIAL_HTML_HOSTS = frozenset({'pulitzer.org', 'www.pulitzer.org'})
_FICTION_MIN_YEAR = 1948
_NOVEL_MIN_YEAR = 1918
_NOVEL_MAX_YEAR = 1947
_PLAUSIBLE_YEAR_MAX = 2099


class PulitzerSourceError(RuntimeError):
    """Raised when the official Pulitzer site blocks or fails retrieval."""


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    award_year: int
    category: str
    status: str
    work_title: str
    work_author: str
    source_url: str


# ---------------------------------------------------------------------------
# HTTP / session retrieval
# ---------------------------------------------------------------------------

def _build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )


def _is_cloudflare_challenge(html: str) -> bool:
    lowered = html.casefold()
    return (
        'just a moment...' in lowered
        or 'checking your browser' in lowered
        or 'cf-browser-verification' in lowered
        or 'enable javascript and cookies to continue' in lowered
        or 'cf_chl_' in lowered
        or 'cdn-cgi/challenge' in lowered
    )


def _read_response_body(response) -> str:
    return response.read().decode('utf-8', errors='replace')


def _blocked_error(url: str, status: int) -> PulitzerSourceError:
    return PulitzerSourceError(
        'Pulitzer temporarily blocked automated retrieval '
        f'(HTTP {status}) for {url}'
    )


def _fetch_html(opener: urllib.request.OpenerDirector, url: str) -> str:
    request = urllib.request.Request(url, headers=dict(_BROWSER_HEADERS))
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, 'status', None) or response.getcode()
            html = _read_response_body(response)
    except urllib.error.HTTPError as exc:
        body = _read_response_body(exc)
        if exc.code == 403 or _is_cloudflare_challenge(body):
            raise _blocked_error(url, exc.code) from exc
        raise PulitzerSourceError(
            f'Pulitzer request failed with HTTP {exc.code} for {url}'
        ) from exc
    except urllib.error.URLError as exc:
        raise PulitzerSourceError(
            f'Pulitzer request failed for {url}: {exc.reason}'
        ) from exc

    if status == 403 or _is_cloudflare_challenge(html):
        raise _blocked_error(url, status)
    if status != 200:
        raise PulitzerSourceError(
            f'Pulitzer request failed with HTTP {status} for {url}'
        )
    return html


_category_pages_cache: tuple[tuple[str, str, str], ...] | None = None
_cache_lock = threading.Lock()


def _reset_runtime_state() -> None:
    global _category_pages_cache
    with _cache_lock:
        _category_pages_cache = None


def _validate_category_records(
    category: str,
    url: str,
    records: list[_ParsedRecord],
) -> None:
    if not records:
        raise PulitzerSourceError(
            f'Pulitzer {category} page did not contain prize records for {url}'
        )
    if any(record.category != category for record in records):
        raise PulitzerSourceError(
            f'Pulitzer {category} page contained mixed categories for {url}'
        )
    winners = [record for record in records if record.status == 'Winner']
    if not winners:
        raise PulitzerSourceError(
            f'Pulitzer {category} page did not contain a Winner for {url}'
        )
    years = [record.award_year for record in records]
    if category == 'Fiction':
        plausible = all(
            _FICTION_MIN_YEAR <= year <= _PLAUSIBLE_YEAR_MAX for year in years
        )
    elif category == 'Novel':
        plausible = all(
            _NOVEL_MIN_YEAR <= year <= _NOVEL_MAX_YEAR for year in years
        )
    else:
        raise PulitzerSourceError(
            f'Pulitzer retrieval received an unexpected category {category!r}'
        )
    if not plausible:
        raise PulitzerSourceError(
            f'Pulitzer {category} page years were not plausible for {url}'
        )


def _fetch_category_pages(
    opener: urllib.request.OpenerDirector,
) -> tuple[tuple[str, str, str], ...]:
    """Fetch and structurally validate Fiction then Novel pages."""
    pages: list[tuple[str, str, str]] = []
    for category, url in _CATEGORY_URLS:
        html = _fetch_html(opener, url)
        records = _parse_category_html(html, category, url)
        _validate_category_records(category, url, records)
        pages.append((category, url, html))
    return tuple(pages)


def _get_category_pages() -> tuple[tuple[str, str, str], ...]:
    """Return cached category pages, fetching once per process on success."""
    global _category_pages_cache
    with _cache_lock:
        if _category_pages_cache is not None:
            return _category_pages_cache
        opener = _build_opener()
        pages = _fetch_category_pages(opener)
        _category_pages_cache = pages
        return pages


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

def _collapse_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _parse_citation(text: str) -> tuple[str, str] | None:
    cleaned = _collapse_ws(text)
    if not cleaned:
        return None
    if cleaned.casefold() == 'no award':
        return None
    match = _CITATION_RE.match(cleaned)
    if not match:
        return None
    title = _collapse_ws(match.group('title'))
    author = _collapse_ws(match.group('author'))
    if not title or not author:
        return None
    return title, author


def _safe_detail_url(href: str | None, *, status: str, fallback: str) -> str:
    """Return an official Pulitzer winner/finalist URL, or the category fallback."""
    if not href or not href.strip():
        return fallback
    resolved = urljoin(f'{_DETAIL_ORIGIN}/', href.strip())
    parsed = urlparse(resolved)
    if parsed.scheme != 'https':
        return fallback
    host = (parsed.hostname or '').casefold().rstrip('.')
    if host not in _OFFICIAL_HTML_HOSTS:
        return fallback
    parts = [piece for piece in parsed.path.split('/') if piece]
    if len(parts) != 2:
        return fallback
    kind, slug = parts
    expected = 'winners' if status == 'Winner' else 'finalists'
    if kind != expected or not _DETAIL_SLUG_RE.fullmatch(slug):
        return fallback
    return f'{_DETAIL_ORIGIN}/{kind}/{slug}'


class _PulitzerCategoryParser(HTMLParser):
    """Parse one official Pulitzer category page into winner/finalist records."""

    def __init__(self, category: str, source_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.category = category
        self.source_url = source_url
        self.records: list[_ParsedRecord] = []
        self._year: int | None = None
        self._capture: str | None = None
        self._buffer: list[str] = []
        self._em_buffer: list[str] = []
        self._citation_href: str | None = None
        self._in_em = False
        self._finalist_depth = 0
        self._seen: set[tuple[int, str, str, str]] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: (value or '') for name, value in attrs}
        classes = attr.get('class', '').split()

        if tag == 'a':
            href = attr.get('href', '')
            year_match = _YEAR_HREF_RE.search(href)
            if year_match:
                self._year = int(year_match.group(1))
            elif (
                self._capture in {'winner', 'finalist'}
                and href
                and self._citation_href is None
            ):
                self._citation_href = href

        if tag == 'h2' and self._capture is None:
            self._capture = 'winner'
            self._buffer = []
            self._em_buffer = []
            self._citation_href = None
            return

        if tag == 'div' and 'finalist-title' in classes and self._capture is None:
            self._capture = 'finalist'
            self._finalist_depth = 1
            self._buffer = []
            self._em_buffer = []
            self._citation_href = None
            return

        if tag == 'div' and self._capture == 'finalist':
            self._finalist_depth += 1

        if (
            tag == 'div'
            and 'winner-citation' in classes
            and self._capture is None
        ):
            self._capture = 'winner_citation'
            self._buffer = []
            return

        if self._capture in {'winner', 'finalist'} and tag == 'em':
            self._in_em = True

    def handle_endtag(self, tag: str) -> None:
        if self._capture in {'winner', 'finalist'} and tag == 'em' and self._in_em:
            self._in_em = False
            return

        if self._capture == 'winner' and tag == 'h2':
            self._finish_citation(status='Winner')
            self._capture = None
            return

        if self._capture == 'finalist' and tag == 'div':
            self._finalist_depth -= 1
            if self._finalist_depth <= 0:
                self._finish_citation(status='Finalist')
                self._capture = None
                self._finalist_depth = 0
            return

        if self._capture == 'winner_citation' and tag == 'div':
            citation = _collapse_ws(''.join(self._buffer))
            # "No award" years have an empty winner heading and this citation.
            self._capture = None
            self._buffer = []
            if citation.casefold() == 'no award':
                return

    def handle_data(self, data: str) -> None:
        if self._capture is None:
            return
        self._buffer.append(data)
        if self._in_em:
            self._em_buffer.append(data)

    def _finish_citation(self, *, status: str) -> None:
        if self._year is None:
            self._buffer = []
            self._em_buffer = []
            self._citation_href = None
            return

        full_text = ''.join(self._buffer)
        em_title = _collapse_ws(''.join(self._em_buffer))
        parsed = _parse_citation(full_text)
        if parsed is None:
            self._buffer = []
            self._em_buffer = []
            self._citation_href = None
            return

        title, author = parsed
        if em_title:
            title = em_title

        key = (self._year, status, title.casefold(), author.casefold())
        if key in self._seen:
            self._buffer = []
            self._em_buffer = []
            self._citation_href = None
            return
        self._seen.add(key)

        self.records.append(
            _ParsedRecord(
                award_year=self._year,
                category=self.category,
                status=status,
                work_title=title,
                work_author=author,
                source_url=_safe_detail_url(
                    self._citation_href,
                    status=status,
                    fallback=self.source_url,
                ),
            )
        )
        self._buffer = []
        self._em_buffer = []
        self._citation_href = None


def _parse_category_html(
    html: str,
    category: str,
    source_url: str,
) -> list[_ParsedRecord]:
    parser = _PulitzerCategoryParser(category, source_url)
    parser.feed(html)
    parser.close()
    return parser.records


# ---------------------------------------------------------------------------
# Normalization / matching
# ---------------------------------------------------------------------------

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
    if query_norm == record_norm:
        return True

    query_has_subtitle = ':' in query_norm
    record_has_subtitle = ':' in record_norm
    # Conservative subtitle fallback only when exactly one side has a colon.
    if query_has_subtitle == record_has_subtitle:
        return False

    query_base = (
        query_norm.split(':', 1)[0].strip() if query_has_subtitle else query_norm
    )
    record_base = (
        record_norm.split(':', 1)[0].strip() if record_has_subtitle else record_norm
    )
    return bool(query_base) and query_base == record_base


def _authors_match(query_author: str, record_author: str) -> bool:
    return _normalize_text(query_author) == _normalize_text(record_author)


def _record_matches(record: _ParsedRecord, title: str, author: str) -> bool:
    return _titles_match(title, record.work_title) and _authors_match(
        author, record.work_author
    )


def _to_award_result(record: _ParsedRecord) -> AwardResult:
    return AwardResult(
        work_title=record.work_title,
        work_author=record.work_author,
        award_name='Pulitzer Prize',
        award_year=record.award_year,
        category=record.category,
        status=record.status,
        rank=None,
        source_name='Pulitzer Prizes',
        source_url=record.source_url,
        notes=None,
    )


# ---------------------------------------------------------------------------
# Public lookup
# ---------------------------------------------------------------------------

def lookup(title: str, author: str, series: str | None = None) -> list[AwardResult]:
    """Look up Pulitzer Fiction/Novel results for a title and author."""
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')

    pages = _get_category_pages()

    matches: list[AwardResult] = []
    for category, url, html in pages:
        for record in _parse_category_html(html, category, url):
            if _record_matches(record, cleaned_title, cleaned_author):
                matches.append(_to_award_result(record))
    return matches
