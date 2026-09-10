"""Official Pulitzer Prize website source (Fiction and Novel categories).

HTTP 200 is not proof of a usable page: Pulitzer.org can return a browser
challenge with a success status. This source does not attempt to bypass that
block. Only a fully validated parsed Fiction/Novel archive is cached, never
raw HTML, challenge pages, or HTTP error bodies.

A reviewed bundled seed of official Fiction/Novel facts is the cold-start
archive when unattended HTTP is blocked. Live category-page retrieval remains
the opportunistic refresh path. Failed live refresh never discards a usable
disk archive or the bundled seed.
"""

from __future__ import annotations

import json
import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urljoin, urlparse

from .. import cache
from ..matching import normalize_title_conjunctions
from ..model import AwardResult

TIMEOUT_SECONDS = 30
SOURCE_HOME_URL = 'https://www.pulitzer.org/'
FICTION_URL = 'https://www.pulitzer.org/prize-winners-by-category/219'
NOVEL_URL = 'https://www.pulitzer.org/prize-winners-by-category/261'
_DETAIL_ORIGIN = 'https://www.pulitzer.org'

_CATEGORY_URLS = (
    ('Fiction', FICTION_URL),
    ('Novel', NOVEL_URL),
)

SOURCE_KEY = 'pulitzer'
CACHE_VERSION = 1
# Persistent cache payload shape is unchanged: parsed records only.
# 7-day base plus an explicit stagger. Do not derive from AWARD_SOURCES order.
CACHE_BASE_TTL_SECONDS = 7 * 24 * 60 * 60
CACHE_REFRESH_OFFSET_SECONDS = 5 * 60 * 60
CACHE_TTL_SECONDS = CACHE_BASE_TTL_SECONDS + CACHE_REFRESH_OFFSET_SECONDS
SEED_SCHEMA_VERSION = 1
SEED_REVIEWED_THROUGH_AWARD_YEAR = 2026
_SEED_ZIP_PATH = 'awards/data/pulitzer_seed.json'
# Official Novel category era begins 1917; 1917 was a no-award year, so
# parsed Novel records remain 1918-1947 (_NOVEL_MIN_YEAR below).
_NOVEL_CATEGORY_START_YEAR = 1917
_OFFICIAL_FINALISTS_FROM_YEAR = 1980

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
# Fiction and Novel occupy distinct official year ranges; mixing them is a parse error.
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


_PARSED_CATEGORIES = frozenset({'Fiction', 'Novel'})
_PARSED_STATUSES = frozenset({'Winner', 'Finalist'})
_RECORD_CACHE_FIELDS = (
    'award_year',
    'category',
    'source_url',
    'status',
    'work_author',
    'work_title',
)
_SEED_TOP_LEVEL_FIELDS = frozenset({
    'coverage',
    'official_source_urls',
    'records',
    'reviewed_at',
    'reviewed_through_award_year',
    'seed_schema_version',
    'source_key',
})
_SEED_COVERAGE_FIELDS = frozenset({
    'fiction_max_year',
    'fiction_min_year',
    'novel_category_start_year',
    'novel_max_year',
    'novel_record_min_year',
    'official_finalists_from_year',
})
_SEED_SENTINELS = (
    (2026, 'Fiction', 'Winner', 'Angel Down', 'Daniel Kraus'),
    (2026, 'Fiction', 'Finalist', 'Audition', 'Katie Kitamura'),
    (2025, 'Fiction', 'Winner', 'James', 'Percival Everett'),
    (2024, 'Fiction', 'Winner', 'Night Watch', 'Jayne Anne Phillips'),
    (2023, 'Fiction', 'Winner', 'Trust', 'Hernan Diaz'),
    (2023, 'Fiction', 'Winner', 'Demon Copperhead', 'Barbara Kingsolver'),
    (1988, 'Fiction', 'Winner', 'Beloved', 'Toni Morrison'),
    (1948, 'Fiction', 'Winner', 'Tales of the South Pacific', 'James A. Michener'),
    (1940, 'Novel', 'Winner', 'The Grapes of Wrath', 'John Steinbeck'),
)


# ---------------------------------------------------------------------------
# HTTP / session retrieval
# ---------------------------------------------------------------------------

def _build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )


def _is_cloudflare_challenge(html: str) -> bool:
    # Challenge pages often arrive as HTTP 200. Status alone is not success.
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


_archive_records_cache: tuple[_ParsedRecord, ...] | None = None
_cache_lock = threading.Lock()
_refresh_requested = False
_live_suppressed = False
_seed_path_override: Path | None = None


def _reset_runtime_state() -> None:
    """Clear in-process caches and live-refresh flags. Does not delete disk."""
    global _archive_records_cache, _refresh_requested, _live_suppressed
    with _cache_lock:
        _archive_records_cache = None
        _refresh_requested = False
        _live_suppressed = False


def mark_official_refresh_requested() -> bool:
    """Clear RAM and request a lazy live refresh without deleting last-known-good data.

    Manual Refresh must not HTTP. The next lookup may attempt official
    category pages. A failed attempt still returns disk cache or the bundled
    seed. The bundled seed file is never modified.
    """
    global _archive_records_cache, _refresh_requested, _live_suppressed
    with _cache_lock:
        _archive_records_cache = None
        _refresh_requested = True
        _live_suppressed = False
    return True


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


def _load_live_archive() -> tuple[_ParsedRecord, ...]:
    """Fetch Fiction then Novel HTML, parse, and validate. HTML is not kept."""
    opener = _build_opener()
    combined: list[_ParsedRecord] = []
    for category, url in _CATEGORY_URLS:
        html = _fetch_html(opener, url)
        records = _parse_category_html(html, category, url)
        _validate_category_records(category, url, records)
        combined.extend(records)
    archive = tuple(combined)
    _validate_cached_archive(archive)
    return archive


def _optional_live_archive() -> tuple[_ParsedRecord, ...] | None:
    """Try official live retrieval. On failure, suppress further live attempts.

    Challenge/403 bodies are never stored. Suppression is deliberately
    process-local and lasts until restart or explicit Refresh, preventing
    repeated requests to Pulitzer.org after a known block.
    """
    global _live_suppressed
    if _live_suppressed:
        return None
    try:
        live = _load_live_archive()
    except Exception:
        _live_suppressed = True
        return None
    _save_persistent_archive(live)
    return live


def _fallback_archive(
    disk_records: tuple[_ParsedRecord, ...] | None,
) -> tuple[_ParsedRecord, ...]:
    if disk_records is not None:
        return disk_records
    return _load_bundled_seed()


def _get_archive_records() -> tuple[_ParsedRecord, ...]:
    """Return records: RAM, disk, bundled seed; live fetch is opportunistic.

    Cold start with a valid seed uses zero HTTP. Fresh disk is used with
    zero HTTP. Stale disk live-refreshes only with a stale-refresh slot.
    Manual Refresh requests one lazy live attempt on the next lookup.
    Failed live retrieval never replaces disk or seed with a partial archive.
    """
    global _archive_records_cache, _refresh_requested
    with _cache_lock:
        if _archive_records_cache is not None:
            return _archive_records_cache
        disk = _load_persistent_archive()
        disk_records = disk[0] if disk is not None else None
        disk_payload = disk[1] if disk is not None else None

        if _refresh_requested:
            _refresh_requested = False
            live = _optional_live_archive()
            if live is not None:
                _archive_records_cache = live
                return live
            records = _fallback_archive(disk_records)
            _archive_records_cache = records
            return records

        if disk_records is not None:
            if cache.cache_is_fresh(disk_payload):
                _archive_records_cache = disk_records
                return disk_records
            if not cache.try_claim_stale_refresh():
                _archive_records_cache = disk_records
                return disk_records
            live = _optional_live_archive()
            if live is not None:
                _archive_records_cache = live
                return live
            _archive_records_cache = disk_records
            return disk_records

        try:
            seed = _load_bundled_seed()
        except PulitzerSourceError:
            live = _optional_live_archive()
            if live is not None:
                _archive_records_cache = live
                return live
            raise
        _archive_records_cache = seed
        return seed


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

def _collapse_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _parse_citation(text: str) -> tuple[str, str] | None:
    cleaned = _collapse_ws(text)
    if not cleaned:
        return None
    # "No award" years are not works.
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
    """Return an official Pulitzer winner/finalist URL, or the category fallback.

    Off-host hrefs and unexpected path shapes are discarded rather than stored.
    """
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
# Persistent parsed-archive cache
# ---------------------------------------------------------------------------

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
    if isinstance(award_year, bool) or not isinstance(award_year, int) or award_year <= 0:
        return None
    category = data.get('category')
    status = data.get('status')
    work_title = data.get('work_title')
    work_author = data.get('work_author')
    source_url = data.get('source_url')
    if category not in _PARSED_CATEGORIES:
        return None
    if status not in _PARSED_STATUSES:
        return None
    if not isinstance(work_title, str) or not work_title.strip() or work_title != work_title.strip():
        return None
    if not isinstance(work_author, str) or not work_author.strip() or work_author != work_author.strip():
        return None
    if (
        not isinstance(source_url, str)
        or not source_url.strip()
        or source_url != source_url.strip()
    ):
        return None
    return _ParsedRecord(
        award_year=award_year,
        category=category,
        status=status,
        work_title=work_title,
        work_author=work_author,
        source_url=source_url,
    )


def _archive_source_urls() -> tuple[str, ...]:
    return tuple(url for _category, url in _CATEGORY_URLS)


def _category_url(category: str) -> str:
    for name, url in _CATEGORY_URLS:
        if name == category:
            return url
    raise PulitzerSourceError(
        f'Pulitzer retrieval received an unexpected category {category!r}'
    )


def _source_url_is_usable(record: _ParsedRecord) -> bool:
    fallback = _category_url(record.category)
    if record.source_url == fallback:
        return True
    reconstructed = _safe_detail_url(
        record.source_url,
        status=record.status,
        fallback=fallback,
    )
    return reconstructed == record.source_url


def _coverage_from_records(records: tuple[_ParsedRecord, ...]) -> dict:
    categories = []
    for category, _url in _CATEGORY_URLS:
        subset = [record for record in records if record.category == category]
        years = [record.award_year for record in subset]
        categories.append(
            {
                'category': category,
                'finalist_count': sum(
                    1 for record in subset if record.status == 'Finalist'
                ),
                'max_year': max(years) if years else None,
                'min_year': min(years) if years else None,
                'record_count': len(subset),
                'winner_count': sum(
                    1 for record in subset if record.status == 'Winner'
                ),
            }
        )
    years = [record.award_year for record in records]
    return {
        'categories': categories,
        'finalist_count': sum(
            1 for record in records if record.status == 'Finalist'
        ),
        'max_year': max(years) if years else None,
        'min_year': min(years) if years else None,
        'record_count': len(records),
        'winner_count': sum(
            1 for record in records if record.status == 'Winner'
        ),
    }


def _validate_cached_archive(records: tuple[_ParsedRecord, ...]) -> None:
    """Fail closed if reconstructed records are not a usable Fiction/Novel archive.

    Live-only checks that cannot be replayed from parsed records: HTTP status,
    Cloudflare/challenge markup, and raw category-page HTML structure.
    """
    if not records:
        raise PulitzerSourceError(
            'Pulitzer persistent cache contained no prize records'
        )
    by_category: dict[str, list[_ParsedRecord]] = {
        category: [] for category, _url in _CATEGORY_URLS
    }
    for record in records:
        if record.category not in _PARSED_CATEGORIES:
            raise PulitzerSourceError(
                f'Pulitzer archive produced an unsupported category: '
                f'{record.category!r}'
            )
        if record.status not in _PARSED_STATUSES:
            raise PulitzerSourceError(
                'Pulitzer archive produced an unexpected status: '
                f'{record.status!r}'
            )
        if not _source_url_is_usable(record):
            raise PulitzerSourceError(
                'Pulitzer archive produced an unexpected source URL: '
                f'{record.source_url!r}'
            )
        by_category[record.category].append(record)
    for category, url in _CATEGORY_URLS:
        subset = by_category[category]
        keys = [
            (
                item.award_year,
                item.status,
                item.work_title.casefold(),
                item.work_author.casefold(),
            )
            for item in subset
        ]
        if len(keys) != len(set(keys)):
            raise PulitzerSourceError(
                f'Pulitzer {category} archive contained duplicate prize records'
            )
        _validate_category_records(category, url, subset)


def _records_from_cache_payload(
    payload: dict,
) -> tuple[_ParsedRecord, ...] | None:
    expected_urls = list(_archive_source_urls())
    if payload.get('source_urls') != expected_urls:
        return None
    raw_records = payload.get('records')
    if not isinstance(raw_records, list):
        return None
    records: list[_ParsedRecord] = []
    for item in raw_records:
        record = _record_from_cache_dict(item)
        if record is None:
            return None
        records.append(record)
    restored = tuple(records)
    try:
        _validate_cached_archive(restored)
    except PulitzerSourceError:
        return None
    return restored


def _load_persistent_archive() -> (
    tuple[tuple[_ParsedRecord, ...], dict] | None
):
    payload = cache.load_source_cache(SOURCE_KEY, CACHE_VERSION)
    if payload is None:
        return None
    records = _records_from_cache_payload(payload)
    if records is None:
        return None
    return records, payload


def _save_persistent_archive(records: tuple[_ParsedRecord, ...]) -> None:
    try:
        cache.save_source_cache(
            SOURCE_KEY,
            CACHE_VERSION,
            records=[_record_to_cache_dict(record) for record in records],
            source_urls=_archive_source_urls(),
            coverage=_coverage_from_records(records),
            ttl_seconds=CACHE_TTL_SECONDS,
        )
    except OSError:
        pass


def _read_bundled_seed_bytes() -> bytes:
    """Read the seed through Calibre's resource API or a development path."""
    if _seed_path_override is not None:
        try:
            return _seed_path_override.read_bytes()
        except OSError as exc:
            raise PulitzerSourceError(
                'Pulitzer bundled seed could not be read'
            ) from exc

    # Calibre injects get_resources into every plugin module. Using it avoids
    # treating this ZIP-loaded module's synthetic __file__ as a filesystem path.
    load_resource = globals().get('get_resources')
    if load_resource is not None:
        raw = load_resource(_SEED_ZIP_PATH)
        if not raw:
            raise PulitzerSourceError(
                'Pulitzer bundled seed could not be read'
            )
        return raw

    # Ordinary Python development/tests run from a source checkout, where
    # Calibre's injected resource API is intentionally absent.
    source_path = (
        Path(__file__).resolve().parents[2]
        / Path(*_SEED_ZIP_PATH.split('/'))
    )
    try:
        return source_path.read_bytes()
    except OSError as exc:
        raise PulitzerSourceError(
            'Pulitzer bundled seed could not be read'
        ) from exc


def _require_seed_year(value, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PulitzerSourceError(
            f'Pulitzer bundled seed {label} was not a plausible year'
        )
    return value


def _seed_has_sentinel(
    records: tuple[_ParsedRecord, ...],
    award_year: int,
    category: str,
    status: str,
    work_title: str,
    work_author: str,
) -> bool:
    return any(
        record.award_year == award_year
        and record.category == category
        and record.status == status
        and record.work_title == work_title
        and record.work_author == work_author
        for record in records
    )


def _validate_seed_archive(records: tuple[_ParsedRecord, ...], payload: dict) -> None:
    _validate_cached_archive(records)
    reviewed_through = payload['reviewed_through_award_year']
    fiction_years = [
        record.award_year for record in records if record.category == 'Fiction'
    ]
    if max(fiction_years) != reviewed_through:
        raise PulitzerSourceError(
            'Pulitzer bundled seed latest Fiction year did not match '
            'reviewed_through_award_year'
        )
    if reviewed_through < SEED_REVIEWED_THROUGH_AWARD_YEAR:
        raise PulitzerSourceError(
            'Pulitzer bundled seed is not reviewed through the required '
            f'award year {SEED_REVIEWED_THROUGH_AWARD_YEAR}'
        )
    for sentinel in _SEED_SENTINELS:
        if not _seed_has_sentinel(records, *sentinel):
            raise PulitzerSourceError(
                'Pulitzer bundled seed is missing required official record: '
                f'{sentinel!r}'
            )
    if any(record.award_year == 1917 for record in records):
        raise PulitzerSourceError(
            'Pulitzer bundled seed contained a 1917 Novel award record'
        )
    if any(
        record.award_year == 2012
        and record.category == 'Fiction'
        and record.status == 'Winner'
        for record in records
    ):
        raise PulitzerSourceError(
            'Pulitzer bundled seed contained a 2012 Fiction Winner'
        )
    trust = _seed_has_sentinel(
        records, 2023, 'Fiction', 'Winner', 'Trust', 'Hernan Diaz'
    )
    demon = _seed_has_sentinel(
        records,
        2023,
        'Fiction',
        'Winner',
        'Demon Copperhead',
        'Barbara Kingsolver',
    )
    if not (trust and demon):
        raise PulitzerSourceError(
            'Pulitzer bundled seed did not contain both 2023 Fiction Winners'
        )


def _records_from_seed_payload(payload) -> tuple[_ParsedRecord, ...]:
    if not isinstance(payload, dict) or set(payload) != _SEED_TOP_LEVEL_FIELDS:
        raise PulitzerSourceError(
            'Pulitzer bundled seed metadata did not match the expected schema'
        )
    if payload.get('seed_schema_version') != SEED_SCHEMA_VERSION:
        raise PulitzerSourceError(
            'Pulitzer bundled seed schema version is unsupported'
        )
    if payload.get('source_key') != SOURCE_KEY:
        raise PulitzerSourceError(
            'Pulitzer bundled seed source identity is not pulitzer'
        )
    reviewed_at = payload.get('reviewed_at')
    if not isinstance(reviewed_at, str) or not reviewed_at.strip():
        raise PulitzerSourceError(
            'Pulitzer bundled seed is missing reviewed_at'
        )
    reviewed_through = _require_seed_year(
        payload.get('reviewed_through_award_year'),
        label='reviewed_through_award_year',
    )
    payload_with_year = dict(payload)
    payload_with_year['reviewed_through_award_year'] = reviewed_through
    urls = payload.get('official_source_urls')
    if urls != list(_archive_source_urls()):
        raise PulitzerSourceError(
            'Pulitzer bundled seed official_source_urls did not match '
            'the Fiction and Novel category pages'
        )
    coverage = payload.get('coverage')
    if not isinstance(coverage, dict) or set(coverage) != _SEED_COVERAGE_FIELDS:
        raise PulitzerSourceError(
            'Pulitzer bundled seed coverage metadata is incomplete'
        )
    expected_coverage = {
        'fiction_max_year': reviewed_through,
        'fiction_min_year': _FICTION_MIN_YEAR,
        'novel_category_start_year': _NOVEL_CATEGORY_START_YEAR,
        'novel_max_year': _NOVEL_MAX_YEAR,
        'novel_record_min_year': _NOVEL_MIN_YEAR,
        'official_finalists_from_year': _OFFICIAL_FINALISTS_FROM_YEAR,
    }
    for key, expected in expected_coverage.items():
        actual = _require_seed_year(coverage.get(key), label=key)
        if actual != expected:
            raise PulitzerSourceError(
                f'Pulitzer bundled seed coverage {key} was {actual!r}, '
                f'expected {expected!r}'
            )
    raw_records = payload.get('records')
    if not isinstance(raw_records, list):
        raise PulitzerSourceError(
            'Pulitzer bundled seed records were not a list'
        )
    records: list[_ParsedRecord] = []
    for item in raw_records:
        record = _record_from_cache_dict(item)
        if record is None:
            raise PulitzerSourceError(
                'Pulitzer bundled seed contained a malformed prize record'
            )
        records.append(record)
    restored = tuple(records)
    _validate_seed_archive(restored, payload_with_year)
    return restored


def _load_bundled_seed() -> tuple[_ParsedRecord, ...]:
    raw = _read_bundled_seed_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PulitzerSourceError(
            'Pulitzer bundled seed was not valid JSON'
        ) from exc
    return _records_from_seed_payload(payload)


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
    # Exact normalized strings only; no surname-only or token-subset matching.
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

    matches: list[AwardResult] = []
    for record in _get_archive_records():
        if _record_matches(record, cleaned_title, cleaned_author):
            matches.append(_to_award_result(record))
    return matches
