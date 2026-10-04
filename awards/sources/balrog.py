"""Balrog literary awards from the public ISFDB copy at stoecker.eu.

The original award ran from 1979 through 1985. Only title-bearing literary
categories are included; person, film, publication and achievement awards
are excluded. ISFDB data is licensed CC BY 4.0; every result retains the
retrieved year-page URL and database attribution.
"""

from __future__ import annotations

import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import asdict
from html.parser import HTMLParser
from urllib.parse import urlparse

from .. import cache
from ..matching import normalize_title_conjunctions
from ..model import AwardResult

SOURCE_KEY = 'balrog'
SOURCE_NAME = 'Internet Speculative Fiction Database (stoecker.eu copy)'
AWARD_NAME = 'Balrog Award'
SOURCE_HOME_URL = 'https://isfdb.stoecker.eu/cgi-bin/awardtype.cgi?8'
SOURCE_PAGE_URLS = tuple(
    f'https://isfdb.stoecker.eu/cgi-bin/ay.cgi?8+{year}'
    for year in range(1979, 1986)
)
CATEGORIES = ('Novel', 'Short Fiction', 'Short Story', 'Collection', 'Collection/Anthology')
TIMEOUT_SECONDS = 15
CACHE_VERSION = 1
CACHE_TTL_SECONDS = 180 * 24 * 60 * 60
_MIN_YEAR_RECORDS = {1979: 12, 1980: 39, 1981: 38, 1982: 20, 1983: 18, 1984: 3, 1985: 3}
_records = None
_lock = threading.Lock()


class BalrogSourceError(RuntimeError):
    """The archive could not be retrieved or validated."""


def _text(value):
    return re.sub(r'\s+', ' ', value).strip()


def _key(value):
    value = unicodedata.normalize('NFKC', value).casefold()
    value = value.replace('’', "'").replace('–', '-').replace('—', '-')
    value = re.sub(r'\b([a-z])\.\s+', r'\1.', value)
    return normalize_title_conjunctions(_text(value))


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.cells = None
        self.cell = None
        self.links = []
        self.heading = []
        self.in_heading = False

    def handle_starttag(self, tag, attrs):
        if tag == 'h2':
            self.in_heading = True
        if tag == 'tr':
            self.cells = []
        elif tag in ('td', 'th') and self.cells is not None:
            self.cell = []
            self.links = []
        elif tag == 'a' and self.cell is not None:
            self.links.append(dict(attrs).get('href', ''))

    def handle_data(self, data):
        if self.in_heading:
            self.heading.append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == 'h2':
            self.in_heading = False
        if tag in ('td', 'th') and self.cell is not None:
            self.cells.append((_text(''.join(self.cell)), tuple(self.links)))
            self.cell = None
        elif tag == 'tr' and self.cells is not None:
            self.rows.append(self.cells)
            self.cells = None


def _parse_year(html, year):
    parser = _Rows()
    parser.feed(html)
    parser.close()
    if _text(''.join(parser.heading)) != f'{year} Balrog Award':
        raise BalrogSourceError(f'ISFDB did not return the {year} Balrog Award page')
    category = None
    results = {}
    for cells in parser.rows:
        if len(cells) == 1 and any('/award_category.cgi?' in link for link in cells[0][1]):
            category = cells[0][0]
            continue
        if category not in CATEGORIES or not cells:
            continue
        if not any('/award_details.cgi?' in link for link in cells[0][1]):
            continue
        if len(cells) != 3 or cells[0][0] not in ('Win', 'Nomination'):
            raise BalrogSourceError(f'Unreadable Balrog {year} {category} award row')
        status, title, author = (cell[0] for cell in cells)
        if (
            not title or not author
            or not any('/title.cgi?' in link for link in cells[1][1])
            or not any('/ea.cgi?' in link for link in cells[2][1])
        ):
            raise BalrogSourceError(f'Missing Balrog {year} work identity')
        result = AwardResult(
            work_title=title, work_author=author, award_name=AWARD_NAME,
            award_year=year, category=category,
            status='Winner' if status == 'Win' else 'Nomination', rank=None,
            source_name=SOURCE_NAME, source_url=SOURCE_PAGE_URLS[year - 1979],
        )
        identity = (category, _key(title), _key(author))
        if identity not in results or result.status == 'Winner':
            results[identity] = result
    records = tuple(results.values())
    _validate_year(records, year)
    return records


def _validate_year(records, year):
    if len(records) < _MIN_YEAR_RECORDS[year]:
        raise BalrogSourceError(f'Balrog {year} is missing reviewed literary award records')
    for record in records:
        if (
            record.award_year != year or record.category not in CATEGORIES
            or record.status not in ('Winner', 'Nomination') or record.rank is not None
            or record.award_name != AWARD_NAME or record.source_name != SOURCE_NAME
            or record.source_url != SOURCE_PAGE_URLS[year - 1979]
            or record.identity_kind != 'work'
            or record.identity_confirmation_required or record.is_specifically_cited_work
            or record.notes is not None or record.source_identity_note is not None
            or record.source_details
        ):
            raise BalrogSourceError(f'Invalid Balrog {year} record')
    for categories in (('Novel',), ('Short Fiction', 'Short Story'), ('Collection', 'Collection/Anthology')):
        winners = [r for r in records if r.category in categories and r.status == 'Winner']
        if len(winners) != 1:
            raise BalrogSourceError(f'Balrog {year} is missing a reviewed literary winner')


def _fetch_html(url):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'Calibre-Awards/0.3.0 (historical award lookup)',
        'Accept': 'text/html', 'Accept-Encoding': 'identity',
    })
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200 or urlparse(response.geturl()).hostname != 'isfdb.stoecker.eu':
                raise BalrogSourceError(f'Unexpected ISFDB response for {url}')
            return response.read().decode(response.headers.get_content_charset() or 'utf-8')
    except urllib.error.HTTPError as exc:
        try:
            raise BalrogSourceError(f'ISFDB Balrog request failed with HTTP {exc.code}: {url}') from exc
        finally:
            exc.close()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BalrogSourceError(f'ISFDB Balrog request failed for {url}: {exc}') from exc


def _load_disk():
    payload = cache.load_source_cache(SOURCE_KEY, CACHE_VERSION)
    if payload is None or payload.get('source_urls') != list(SOURCE_PAGE_URLS):
        return None
    try:
        records = tuple(AwardResult(**dict(row, source_details=tuple(row.get('source_details', ())))) for row in payload['records'])
        if any(type(r.award_year) is not int or r.award_year not in range(1979, 1986) for r in records):
            return None
        for year in range(1979, 1986):
            _validate_year(tuple(r for r in records if r.award_year == year), year)
        identities = [(r.award_year, r.category, _key(r.work_title), _key(r.work_author)) for r in records]
        if len(identities) != len(set(identities)):
            return None
    except (KeyError, TypeError, ValueError, BalrogSourceError):
        return None
    return records, payload


def _get_records():
    global _records
    with _lock:
        if _records is not None:
            return _records
        disk = _load_disk()
        if disk and (cache.cache_is_fresh(disk[1]) or not cache.try_claim_stale_refresh(SOURCE_KEY)):
            _records = disk[0]
            return _records
        try:
            records = tuple(
                record for year, url in zip(range(1979, 1986), SOURCE_PAGE_URLS)
                for record in _parse_year(_fetch_html(url), year)
            )
        except Exception:
            if disk:
                _records = disk[0]
                return _records
            raise
        cache.save_source_cache(
            SOURCE_KEY, CACHE_VERSION, records=[asdict(r) for r in records],
            source_urls=SOURCE_PAGE_URLS, coverage={'min_year': 1979, 'max_year': 1985},
            ttl_seconds=CACHE_TTL_SECONDS,
        )
        _records = records
        return records


def _reset_runtime_state():
    global _records
    with _lock:
        _records = None


def lookup(title, author, series=None):
    if not title.strip() or not author.strip():
        raise ValueError('title and author must be non-empty')
    return [r for r in _get_records() if _key(r.work_title) == _key(title) and _key(r.work_author) == _key(author)]
