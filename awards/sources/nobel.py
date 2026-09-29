"""Official Nobel Prize in Literature source (api.nobelprize.org).

Literature prizes are author-level. A finite reviewed mapping marks queries
whose Calibre title is explicitly cited in the official motivation; those
results remain identity_kind='author'. Motivation prose is not parsed into
titles. A validated laureate archive may also be loaded from the injected
persistent cache.
"""

from __future__ import annotations

import html
import json
import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar
from urllib.parse import urlparse

from .. import cache
from ..model import AwardResult

TIMEOUT_SECONDS = 30
LAUREATES_ENDPOINT = 'https://api.nobelprize.org/2.1/laureates'
PAGE_LIMIT = 200
MAX_PAGES = 10
LAUREATES_URL = (
    f'{LAUREATES_ENDPOINT}?nobelPrizeCategory=lit'
    f'&limit={PAGE_LIMIT}&offset=0'
)
SOURCE_NAME = 'NobelPrize.org'
SOURCE_HOME_URL = 'https://www.nobelprize.org/'
AWARD_NAME = 'Nobel Prize'
CATEGORY_LITERATURE = 'Literature'
LAUREATE_FALLBACK_URL = 'https://www.nobelprize.org/laureate/{id}'

SOURCE_KEY = 'nobel'
CACHE_VERSION = 2
# 7-day base plus an explicit stagger. Do not derive from AWARD_SOURCES order.
CACHE_BASE_TTL_SECONDS = 7 * 24 * 60 * 60
CACHE_REFRESH_OFFSET_SECONDS = 4 * 60 * 60
CACHE_TTL_SECONDS = CACHE_BASE_TTL_SECONDS + CACHE_REFRESH_OFFSET_SECONDS

_BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json,text/plain;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'identity',
}

_INITIALS_SPACE_RE = re.compile(r'\b([A-Za-z])\.\s+')
_CALIBRE_AMP_PLACEHOLDER = '\uffff'
_SAFE_LAUREATE_ID_RE = re.compile(r'^[0-9A-Za-z_-]+$')
_OFFICIAL_HTML_HOSTS = frozenset({'nobelprize.org', 'www.nobelprize.org'})
_FACTS_CLASS = 'laureate facts'
_MOTIVATION_TAG_RE = re.compile(r'</?[A-Za-z][A-Za-z0-9]*\b[^>]*>')
_RESIDUAL_TAG_RE = re.compile(r'</?[A-Za-z]')


class NobelSourceError(RuntimeError):
    """Raised when the official Nobel API cannot be retrieved or validated."""


@dataclass(frozen=True, slots=True)
class _CitedWorkMapping:
    laureate_id: str
    award_year: int
    canonical_title: str
    title_aliases: tuple[str, ...]


# Finite reviewed specifically-cited works. No live title extraction.
# Sholokhov 1965 is omitted: "his epic of the Don" is not an explicit title.
_CITED_WORKS: tuple[_CitedWorkMapping, ...] = (
    _CitedWorkMapping(
        '571',
        1902,
        'A History of Rome',
        ('A History of Rome', 'A history of Rome', 'Römische Geschichte'),
    ),
    _CitedWorkMapping(
        '588',
        1919,
        'Olympian Spring',
        ('Olympian Spring',),
    ),
    _CitedWorkMapping(
        '589',
        1920,
        'Growth of the Soil',
        ('Growth of the Soil', 'Markens Grøde'),
    ),
    _CitedWorkMapping(
        '594',
        1924,
        'The Peasants',
        ('The Peasants',),
    ),
    _CitedWorkMapping(
        '602',
        1929,
        'Buddenbrooks',
        ('Buddenbrooks',),
    ),
    _CitedWorkMapping(
        '605',
        1932,
        'The Forsyte Saga',
        ('The Forsyte Saga',),
    ),
    _CitedWorkMapping(
        '609',
        1937,
        'Les Thibault',
        ('Les Thibault',),
    ),
    _CitedWorkMapping(
        '625',
        1954,
        'The Old Man and the Sea',
        ('The Old Man and the Sea', 'Old Man and the Sea'),
    ),
)
_CITED_WORKS_BY_ID = {
    item.laureate_id: item for item in _CITED_WORKS
}


@dataclass(frozen=True, slots=True)
class _LiteraturePrize:
    award_year: int
    prize_status: str
    source_url: str
    notes: str | None
    motivation: str


@dataclass(frozen=True, slots=True)
class _Laureate:
    laureate_id: str
    known_name: str
    match_names: tuple[str, ...]
    prize: _LiteraturePrize


_LAUREATE_CACHE_FIELDS = (
    'known_name',
    'laureate_id',
    'match_names',
    'prize',
)
_PRIZE_CACHE_FIELDS = (
    'award_year',
    'motivation',
    'notes',
    'prize_status',
    'source_url',
)


_cache_lock = threading.Lock()
_laureates_cache: tuple[_Laureate, ...] | None = None


def _reset_runtime_state() -> None:
    """Clear in-process caches. Used by tests. Does not delete disk cache."""
    global _laureates_cache
    with _cache_lock:
        _laureates_cache = None


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


def _laureates_page_url(offset: int) -> str:
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise NobelSourceError('Nobel pagination offset is invalid')
    return (
        f'{LAUREATES_ENDPOINT}?nobelPrizeCategory=lit'
        f'&limit={PAGE_LIMIT}&offset={offset}'
    )


def _request_json(url: str = LAUREATES_URL) -> tuple[int, str]:
    request = urllib.request.Request(url, headers=dict(_BROWSER_HEADERS))
    opener = _build_opener()
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, 'status', None) or response.getcode()
            body = _read_response_body(response)
    except urllib.error.HTTPError as exc:
        try:
            body = _read_response_body(exc)
            raise NobelSourceError(
                f'Nobel request failed with HTTP {exc.code} for {url}'
                + (f': {body[:200].strip()}' if body.strip() else '')
            ) from exc
        finally:
            exc.close()
    except urllib.error.URLError as exc:
        raise NobelSourceError(
            f'Nobel request failed for {url}: {exc.reason}'
        ) from exc
    except TimeoutError as exc:
        raise NobelSourceError(
            f'Nobel request timed out for {url}'
        ) from exc
    return int(status), body


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


def _author_match_forms(name: str) -> frozenset[str]:
    forms: list[str] = []
    for candidate in (name, _ascii_fold(name)):
        normalized = _normalize_text(candidate)
        if normalized and normalized not in forms:
            forms.append(normalized)
    return frozenset(forms)


def _split_calibre_author_query(query_author: str) -> tuple[str, ...]:
    """Invert Calibre authors_to_string: split on ' & ', restore '&&' to '&'."""
    protected = query_author.replace('&&', _CALIBRE_AMP_PLACEHOLDER)
    people: list[str] = []
    for piece in protected.split(' & '):
        restored = piece.replace(_CALIBRE_AMP_PLACEHOLDER, '&').strip()
        if restored:
            people.append(restored)
    return tuple(people)


def _localized_en(value: object) -> str | None:
    if isinstance(value, str):
        text = _collapse_ws(value)
        return text or None
    if isinstance(value, dict):
        english = value.get('en')
        if isinstance(english, str):
            text = _collapse_ws(english)
            return text or None
    return None


def _pen_name_of_full(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    return _localized_en(value.get('fullName'))


def _link_classes(link: dict) -> tuple[str, ...]:
    raw = link.get('class')
    if isinstance(raw, str):
        text = _collapse_ws(raw)
        return (text,) if text else ()
    if isinstance(raw, list):
        classes: list[str] = []
        for item in raw:
            if isinstance(item, str):
                text = _collapse_ws(item)
                if text:
                    classes.append(text)
        return tuple(classes)
    return ()


def _is_official_nobel_html_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {'http', 'https'}:
        return False
    host = (parsed.hostname or '').casefold().rstrip('.')
    return host in _OFFICIAL_HTML_HOSTS


def _is_laureate_facts_url(url: str) -> bool:
    if not _is_official_nobel_html_url(url):
        return False
    path = urlparse(url.strip()).path.casefold()
    return '/prizes/literature/' in path and path.rstrip('/').endswith('/facts')


def _facts_href_from_links(links: object) -> str | None:
    if not isinstance(links, list):
        return None
    for item in links:
        if not isinstance(item, dict):
            continue
        rel = item.get('rel')
        if not isinstance(rel, str) or rel.strip().casefold() != 'external':
            continue
        if _FACTS_CLASS not in _link_classes(item):
            continue
        href = item.get('href')
        if not isinstance(href, str):
            continue
        url = href.strip()
        if _is_laureate_facts_url(url):
            return url
    return None


def _fallback_laureate_url(laureate_id: str) -> str | None:
    if not _SAFE_LAUREATE_ID_RE.fullmatch(laureate_id):
        return None
    url = LAUREATE_FALLBACK_URL.format(id=laureate_id)
    if not _is_official_nobel_html_url(url):
        return None
    return url


def _select_source_url(
    prize_links: object,
    laureate_links: object,
    laureate_id: str,
) -> str | None:
    # Official facts/laureate URL shapes only; off-host hrefs are ignored.
    for links in (prize_links, laureate_links):
        facts = _facts_href_from_links(links)
        if facts is not None:
            return facts
    return _fallback_laureate_url(laureate_id)


def _notes_for_status(status: str) -> str | None:
    # Factual prize-status notes. These are not cited-work control state.
    key = status.casefold()
    if key == 'received':
        return None
    if key == 'declined':
        return 'Nobel Prize status: declined.'
    if key == 'restricted':
        return 'Nobel Prize status: restricted.'
    return f'Nobel Prize status: {status}.'


def _plain_english_motivation(value: object) -> str | None:
    """Return official English motivation as plain text, or None if unusable.

    Missing, non-object, or non-English motivation fails closed. Simple
    Nobel HTML title markup is stripped after entity decoding.
    """
    if not isinstance(value, dict):
        return None
    english = value.get('en')
    if not isinstance(english, str) or not english.strip():
        return None
    text = html.unescape(english)
    text = _MOTIVATION_TAG_RE.sub('', text)
    if _RESIDUAL_TAG_RE.search(text):
        return None
    text = _collapse_ws(text)
    return text or None


def _motivation_detail(motivation: str) -> str:
    return f'Official motivation: "{motivation}"'


def _source_details_for(prize: _LiteraturePrize) -> tuple[str, ...]:
    details = [_motivation_detail(prize.motivation)]
    if prize.notes is not None:
        details.append(prize.notes)
    return tuple(details)


def _parse_award_year(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            year = int(text)
            return year if year > 0 else None
    return None


def _parse_literature_prize(
    prize: object,
    laureate_id: str,
    laureate_links: object,
) -> _LiteraturePrize | None:
    if not isinstance(prize, dict):
        return None
    category = _localized_en(prize.get('category'))
    if category is None or category.casefold() != CATEGORY_LITERATURE.casefold():
        return None
    year = _parse_award_year(prize.get('awardYear'))
    if year is None:
        return None
    status = prize.get('prizeStatus')
    if not isinstance(status, str) or not status.strip():
        return None
    prize_status = _collapse_ws(status)
    motivation = _plain_english_motivation(prize.get('motivation'))
    if motivation is None:
        # A missing motivation fails the refresh. Do not store a partial
        # laureate archive that silently omits official prize text.
        raise NobelSourceError(
            f'Nobel laureate {laureate_id} is missing a usable English '
            'prize motivation'
        )
    source_url = _select_source_url(
        prize.get('links'),
        laureate_links,
        laureate_id,
    )
    if source_url is None:
        return None
    return _LiteraturePrize(
        award_year=year,
        prize_status=prize_status,
        source_url=source_url,
        notes=_notes_for_status(prize_status),
        motivation=motivation,
    )


def _unique_names(*names: str | None) -> tuple[str, ...]:
    unique: list[str] = []
    for name in names:
        if name and name not in unique:
            unique.append(name)
    return tuple(unique)


def _parse_laureate(item: object) -> _Laureate:
    if not isinstance(item, dict):
        raise NobelSourceError(
            'Nobel laureates payload contained a non-object laureate record'
        )
    raw_id = item.get('id')
    if isinstance(raw_id, bool) or raw_id is None:
        raise NobelSourceError('Nobel laureate is missing a usable id')
    laureate_id = _collapse_ws(str(raw_id))
    if not laureate_id:
        raise NobelSourceError('Nobel laureate is missing a usable id')
    known_name = _localized_en(item.get('knownName'))
    if known_name is None:
        raise NobelSourceError(
            f'Nobel laureate {laureate_id} is missing knownName.en'
        )
    prizes = item.get('nobelPrizes')
    if not isinstance(prizes, list) or not prizes:
        raise NobelSourceError(
            f'Nobel laureate {laureate_id} is missing nobelPrizes'
        )
    literature = [
        parsed
        for parsed in (
            _parse_literature_prize(prize, laureate_id, item.get('links'))
            for prize in prizes
        )
        if parsed is not None
    ]
    if not literature:
        raise NobelSourceError(
            f'Nobel laureate {laureate_id} has no usable Literature prize'
        )
    # Bounded official aliases only; no surname-only or fuzzy guessing.
    match_names = _unique_names(
        known_name,
        _localized_en(item.get('fullName')),
        _pen_name_of_full(item.get('penNameOf')),
    )
    return _Laureate(
        laureate_id=laureate_id,
        known_name=known_name,
        match_names=match_names,
        prize=literature[0],
    )


def _decode_laureates_payload(status: int, body: str, url: str) -> dict:
    if status != 200:
        raise NobelSourceError(
            f'Nobel laureates request failed with HTTP {status} for {url}'
        )
    if not body.strip():
        raise NobelSourceError('Nobel laureates response was empty')
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise NobelSourceError(
            f'Nobel laureates response was not valid JSON: {exc}'
        ) from exc
    if not isinstance(payload, dict):
        raise NobelSourceError('Nobel laureates response JSON was not an object')
    return payload


def _page_meta(payload: dict, requested_offset: int) -> tuple[list, int, int]:
    laureates = payload.get('laureates')
    if not isinstance(laureates, list):
        raise NobelSourceError(
            'Nobel laureates response is missing a laureates list'
        )
    meta = payload.get('meta')
    if not isinstance(meta, dict):
        raise NobelSourceError('Nobel laureates response is missing meta')
    count = meta.get('count')
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise NobelSourceError(
            'Nobel laureates meta.count is not a positive integer'
        )
    offset = meta.get('offset')
    if offset is None:
        offset = 0
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise NobelSourceError(
            'Nobel laureates meta.offset is not a non-negative integer'
        )
    if offset != requested_offset:
        raise NobelSourceError(
            'Nobel laureates meta.offset did not match the requested page: '
            f'{offset} != {requested_offset}'
        )
    if len(laureates) > count:
        raise NobelSourceError(
            'Nobel laureates page is longer than meta.count: '
            f'{len(laureates)} > {count}'
        )
    return laureates, count, offset


def _parse_laureates_payload(status: int, body: str) -> tuple[_Laureate, ...]:
    payload = _decode_laureates_payload(status, body, LAUREATES_URL)
    laureates, count, offset = _page_meta(payload, 0)
    if offset != 0:
        raise NobelSourceError(
            'Nobel laureates complete payload did not start at offset 0'
        )
    if len(laureates) != count:
        raise NobelSourceError(
            'Nobel laureates response length did not match meta.count: '
            f'{len(laureates)} != {count}'
        )
    parsed = tuple(_parse_laureate(item) for item in laureates)
    if not parsed:
        raise NobelSourceError('Nobel laureates response contained no laureates')
    return parsed


def _load_live_archive() -> tuple[_Laureate, ...]:
    combined: list[_Laureate] = []
    seen_ids: set[str] = set()
    seen_offsets: set[int] = set()
    expected_count: int | None = None
    offset = 0
    for _page in range(MAX_PAGES):
        if offset in seen_offsets:
            raise NobelSourceError(
                f'Nobel pagination repeated offset {offset}'
            )
        seen_offsets.add(offset)
        url = _laureates_page_url(offset)
        status, body = _request_json(url)
        payload = _decode_laureates_payload(status, body, url)
        raw_page, count, _meta_offset = _page_meta(payload, offset)
        if expected_count is None:
            expected_count = count
        elif count != expected_count:
            raise NobelSourceError(
                'Nobel pagination meta.count changed between pages: '
                f'{expected_count} != {count}'
            )
        remaining = expected_count - len(combined)
        if len(raw_page) > remaining:
            raise NobelSourceError(
                'Nobel pagination returned more laureates than meta.count'
            )
        if not raw_page and remaining > 0:
            raise NobelSourceError(
                'Nobel pagination returned an empty page before meta.count'
            )
        for item in raw_page:
            parsed = _parse_laureate(item)
            if parsed.laureate_id in seen_ids:
                raise NobelSourceError(
                    'Nobel pagination returned duplicate laureate id: '
                    f'{parsed.laureate_id!r}'
                )
            seen_ids.add(parsed.laureate_id)
            combined.append(parsed)
        if len(combined) == expected_count:
            return tuple(combined)
        if not raw_page:
            raise NobelSourceError(
                'Nobel pagination stopped short of meta.count'
            )
        offset = offset + len(raw_page)
        if offset <= max(seen_offsets):
            raise NobelSourceError('Nobel pagination offset did not advance')
    raise NobelSourceError(
        'Nobel pagination exceeded the maximum number of pages before '
        'reaching meta.count'
    )


# ---------------------------------------------------------------------------
# Persistent laureate archive cache
# ---------------------------------------------------------------------------

def _record_to_cache_dict(record: _Laureate) -> dict:
    prize = record.prize
    return {
        'known_name': record.known_name,
        'laureate_id': record.laureate_id,
        'match_names': list(record.match_names),
        'prize': {
            'award_year': prize.award_year,
            'motivation': prize.motivation,
            'notes': prize.notes,
            'prize_status': prize.prize_status,
            'source_url': prize.source_url,
        },
    }


def _match_names_from_cache(value) -> tuple[str, ...] | None:
    if isinstance(value, (str, bytes, bytearray)):
        return None
    if not isinstance(value, (list, tuple)) or not value:
        return None
    names: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or item != item.strip():
            return None
        names.append(item)
    return tuple(names)


def _prize_from_cache_dict(data) -> _LiteraturePrize | None:
    if not isinstance(data, dict) or set(data) != set(_PRIZE_CACHE_FIELDS):
        return None
    award_year = data.get('award_year')
    if isinstance(award_year, bool) or not isinstance(award_year, int) or award_year <= 0:
        return None
    prize_status = data.get('prize_status')
    source_url = data.get('source_url')
    notes = data.get('notes')
    motivation = data.get('motivation')
    if (
        not isinstance(prize_status, str)
        or not prize_status.strip()
        or prize_status != prize_status.strip()
    ):
        return None
    if (
        not isinstance(source_url, str)
        or not source_url.strip()
        or source_url != source_url.strip()
        or not _is_official_nobel_html_url(source_url)
    ):
        return None
    if notes is not None:
        if not isinstance(notes, str) or not notes.strip() or notes != notes.strip():
            return None
    if (
        not isinstance(motivation, str)
        or not motivation.strip()
        or motivation != motivation.strip()
    ):
        return None
    return _LiteraturePrize(
        award_year=award_year,
        prize_status=prize_status,
        source_url=source_url,
        notes=notes,
        motivation=motivation,
    )


def _record_from_cache_dict(data) -> _Laureate | None:
    if not isinstance(data, dict) or set(data) != set(_LAUREATE_CACHE_FIELDS):
        return None
    laureate_id = data.get('laureate_id')
    known_name = data.get('known_name')
    if (
        not isinstance(laureate_id, str)
        or not laureate_id.strip()
        or laureate_id != laureate_id.strip()
    ):
        return None
    if (
        not isinstance(known_name, str)
        or not known_name.strip()
        or known_name != known_name.strip()
    ):
        return None
    match_names = _match_names_from_cache(data.get('match_names'))
    if match_names is None or known_name not in match_names:
        return None
    prize = _prize_from_cache_dict(data.get('prize'))
    if prize is None:
        return None
    return _Laureate(
        laureate_id=laureate_id,
        known_name=known_name,
        match_names=match_names,
        prize=prize,
    )


def _archive_source_urls() -> tuple[str, ...]:
    return (LAUREATES_URL,)


def _coverage_from_records(records: tuple[_Laureate, ...]) -> dict:
    years = [item.prize.award_year for item in records]
    cited_ids = {item.laureate_id for item in _CITED_WORKS}
    status_counts: dict[str, int] = {}
    for item in records:
        key = item.prize.prize_status
        status_counts[key] = status_counts.get(key, 0) + 1
    return {
        'category': CATEGORY_LITERATURE,
        'cited_work_laureate_count': sum(
            1 for item in records if item.laureate_id in cited_ids
        ),
        'laureate_count': len(records),
        'max_year': max(years) if years else None,
        'min_year': min(years) if years else None,
        'prize_status_counts': dict(sorted(status_counts.items())),
    }


def _validate_cached_archive(records: tuple[_Laureate, ...]) -> None:
    """Fail closed if reconstructed laureates are not a usable archive."""
    if not records:
        raise NobelSourceError(
            'Nobel persistent cache contained no laureate records'
        )
    seen_ids: set[str] = set()
    by_id: dict[str, _Laureate] = {}
    for record in records:
        if record.laureate_id in seen_ids:
            raise NobelSourceError(
                'Nobel persistent cache contained duplicate laureate id: '
                f'{record.laureate_id!r}'
            )
        seen_ids.add(record.laureate_id)
        by_id[record.laureate_id] = record
        if record.known_name not in record.match_names:
            raise NobelSourceError(
                f'Nobel laureate {record.laureate_id} known_name is missing '
                'from match_names'
            )
        if not record.match_names:
            raise NobelSourceError(
                f'Nobel laureate {record.laureate_id} is missing match_names'
            )
        prize = record.prize
        if prize.award_year <= 0:
            raise NobelSourceError(
                f'Nobel laureate {record.laureate_id} has an invalid award year'
            )
        if not _is_official_nobel_html_url(prize.source_url):
            raise NobelSourceError(
                'Nobel archive produced an unexpected source URL: '
                f'{prize.source_url!r}'
            )
        expected_notes = _notes_for_status(prize.prize_status)
        if prize.notes != expected_notes:
            raise NobelSourceError(
                f'Nobel laureate {record.laureate_id} notes do not match '
                f'prize status {prize.prize_status!r}'
            )
        if not prize.motivation or prize.motivation != prize.motivation.strip():
            raise NobelSourceError(
                f'Nobel laureate {record.laureate_id} is missing a usable '
                'English prize motivation'
            )
    missing_cited: list[str] = []
    for mapping in _CITED_WORKS:
        laureate = by_id.get(mapping.laureate_id)
        if laureate is None or laureate.prize.award_year != mapping.award_year:
            missing_cited.append(mapping.laureate_id)
    if missing_cited:
        extra = f' (+{len(missing_cited) - 1} more)' if len(missing_cited) > 1 else ''
        raise NobelSourceError(
            'Nobel persistent cache is missing required cited-work '
            f'laureate(s): {missing_cited[0]}{extra}'
        )


def _records_from_cache_payload(
    payload: dict,
) -> tuple[_Laureate, ...] | None:
    expected_urls = list(_archive_source_urls())
    if payload.get('source_urls') != expected_urls:
        return None
    raw_records = payload.get('records')
    if not isinstance(raw_records, list):
        return None
    records: list[_Laureate] = []
    for item in raw_records:
        record = _record_from_cache_dict(item)
        if record is None:
            return None
        records.append(record)
    restored = tuple(records)
    try:
        _validate_cached_archive(restored)
    except NobelSourceError:
        return None
    return restored


def _load_persistent_archive() -> (
    tuple[tuple[_Laureate, ...], dict] | None
):
    payload = cache.load_source_cache(SOURCE_KEY, CACHE_VERSION)
    if payload is None:
        return None
    records = _records_from_cache_payload(payload)
    if records is None:
        return None
    return records, payload


def _save_persistent_archive(records: tuple[_Laureate, ...]) -> None:
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


def _get_laureates() -> tuple[_Laureate, ...]:
    """Return laureates: RAM, then disk, then live fetch/parse/validate.

    A fresh disk cache is used immediately. A stale-but-valid disk cache
    live-refreshes only if this lookup still has a stale-refresh slot;
    otherwise the stale archive is used with no network. A missing or
    invalid cache still live-fetches.
    """
    global _laureates_cache
    with _cache_lock:
        if _laureates_cache is not None:
            return _laureates_cache
        disk = _load_persistent_archive()
        if disk is not None:
            records, payload = disk
            if cache.cache_is_fresh(payload):
                _laureates_cache = records
                return records
            if not cache.try_claim_stale_refresh():
                _laureates_cache = records
                return records
        else:
            records = None
        try:
            live = _load_live_archive()
        except Exception:
            if records is not None:
                _laureates_cache = records
                return records
            raise
        _save_persistent_archive(live)
        _laureates_cache = live
        return live


def _normalize_title_text(value: str) -> str:
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
    return _collapse_ws(text).casefold()


def _title_match_forms(title: str) -> frozenset[str]:
    forms: list[str] = []
    for candidate in (title, _ascii_fold(title)):
        normalized = _normalize_title_text(candidate)
        if normalized and normalized not in forms:
            forms.append(normalized)
    return frozenset(forms)


def _title_matches_aliases(query_title: str, aliases: tuple[str, ...]) -> bool:
    query_forms = _title_match_forms(query_title)
    if not query_forms:
        return False
    return any(
        bool(query_forms & _title_match_forms(alias)) for alias in aliases
    )


def _cited_work_for(
    laureate: _Laureate, query_title: str
) -> _CitedWorkMapping | None:
    mapping = _CITED_WORKS_BY_ID.get(laureate.laureate_id)
    if mapping is None:
        return None
    if mapping.award_year != laureate.prize.award_year:
        return None
    if not _title_matches_aliases(query_title, mapping.title_aliases):
        return None
    return mapping


def _person_matches_laureate(person: str, laureate: _Laureate) -> bool:
    query_forms = _author_match_forms(person)
    if not query_forms:
        return False
    return any(
        bool(query_forms & _author_match_forms(name))
        for name in laureate.match_names
    )


def _to_award_result(
    laureate: _Laureate, *, cited: bool = False
) -> AwardResult:
    # The laureate received the prize. cited marks an explicitly named work.
    prize = laureate.prize
    return AwardResult(
        work_title=laureate.known_name,
        work_author=laureate.known_name,
        award_name=AWARD_NAME,
        award_year=prize.award_year,
        category=CATEGORY_LITERATURE,
        status='Winner',
        rank=None,
        source_name=SOURCE_NAME,
        source_url=prize.source_url,
        notes=prize.notes,
        identity_kind='author',
        is_specifically_cited_work=cited,
        source_details=_source_details_for(prize),
    )


def lookup(
    title: str,
    author: str,
    series: str | None = None,
) -> list[AwardResult]:
    """Look up Nobel Prize in Literature results.

    Every result is author-level. A mapped cited title sets
    is_specifically_cited_work without replacing the laureate award.
    """
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')

    people = _split_calibre_author_query(cleaned_author)
    if not people:
        return []

    matches: list[AwardResult] = []
    seen: set[str] = set()
    for person in people:
        for laureate in _get_laureates():
            if laureate.laureate_id in seen:
                continue
            if not _person_matches_laureate(person, laureate):
                continue
            seen.add(laureate.laureate_id)
            cited = _cited_work_for(laureate, cleaned_title) is not None
            matches.append(_to_award_result(laureate, cited=cited))
    matches.sort(
        key=lambda result: (
            result.award_year or 0,
            (result.work_author or '').casefold(),
        )
    )
    return matches
