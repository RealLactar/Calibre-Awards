"""Winners, shortlists, longlists and nominations from the official Dublin Literary Award year pages."""

from __future__ import annotations

import re
import threading
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urlencode, parse_qs

from .. import cache
from ..matching import normalize_title_conjunctions
from ..model import AwardResult

SOURCE_KEY = 'dublin'
AWARD_NAME = 'Dublin Literary Award'
SOURCE_NAME = 'Dublin Literary Award (official archive)'
SOURCE_HOME_URL = 'https://dublinliteraryaward.ie/the-library/prize-years/'
SITEMAP_URL = 'https://dublinliteraryaward.ie/prize_years_type-sitemap.xml'
CATEGORIES = ('Novel',)
CACHE_VERSION = 2
CACHE_TTL_SECONDS = 7 * 86400 + 21 * 3600
TIMEOUT_SECONDS = 20
# Reviewed distinct work counts, including the separate 2017/2018 winners.
_MIN_YEAR_RECORDS = dict(zip(range(1996, 2027), (
    7, 8, 10, 8, 6, 6, 7, 8, 10, 10, 10, 8, 8, 8, 8, 10,
    10, 10, 10, 10, 10, 10, 10, 10, 10, 6, 6, 6, 6, 6, 6,
)))
# Reviewed complete-archive minimums guard against silently accepting previews.
# The official 2013 longlist is empty: only its ten finalists are available.
_MIN_YEAR_CANDIDATES = dict(zip(range(1996, 2027), (
    126, 113, 83, 100, 100, 98, 123, 123, 117, 146, 132, 138, 137, 146, 155, 162,
    144, 10, 152, 141, 159, 147, 150, 141, 157, 49, 79, 70, 70, 71, 69,
)))
_STATUS_PRIORITY = {'Winner': 4, 'Shortlisted': 3, 'Longlisted': 2, 'Nominated': 1}
REVIEWED_MIN_YEAR = 2026
_records = None
_lock = threading.RLock()
_VOID = frozenset('area base br col embed hr img input link meta param source track wbr'.split())


class DublinSourceError(RuntimeError):
    """The official archive is unavailable, incomplete, or changed structure."""


def _text(value):
    return re.sub(r'\s+', ' ', value).strip()


def _key(value):
    value = unicodedata.normalize('NFKC', value).casefold()
    value = value.replace('’', "'").replace('–', '-').replace('—', '-')
    value = re.sub(r'\b([a-z])\.\s+', r'\1.', value)
    return normalize_title_conjunctions(_text(value))


@dataclass
class _Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, _Node):
                yield from child.walk()

    def text(self):
        def chunks(node):
            for child in node.children:
                if isinstance(child, _Node):
                    yield from chunks(child)
                else:
                    yield child
        return _text(''.join(chunks(self)))

    def has(self, name):
        return name in self.attrs.get('class', '').split()


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node('root')
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _tree(html):
    parser = _Tree()
    parser.feed(html)
    parser.close()
    return parser.root


def _year_url(year):
    return f'{SOURCE_HOME_URL}{year}/'


def _official_url(url, prefix):
    parsed = urlparse(url)
    return (parsed.scheme == 'https' and parsed.netloc == 'dublinliteraryaward.ie'
            and parsed.path.startswith(prefix) and not parsed.query and not parsed.fragment)


def _author_url(url):
    if _official_url(url, '/the-library/authors/'):
        return True
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    # The archive also links a named author through WordPress's public post URL.
    return (parsed.scheme == 'https' and parsed.netloc == 'dublinliteraryaward.ie'
            and parsed.path == '/' and not parsed.fragment
            and set(params) == {'post_type', 'p'}
            and params['post_type'] == ['authors_type'] and len(params['p']) == 1
            and re.fullmatch(r'[1-9]\d*', params['p'][0]) is not None)


def _one(nodes, description):
    nodes = list(nodes)
    if len(nodes) != 1:
        raise DublinSourceError(f'Missing or ambiguous Dublin {description}')
    return nodes[0]


def _record(card, year, status, source_url, single=False):
    prefix = 'books-single-cover-item' if single else 'books-list-item'
    title = _one((n for n in card.walk() if n.has(prefix + '-title-link')), 'title')
    authors = [n for n in card.walk() if n.has(prefix + '-author-link')]
    if (not title.text() or not authors or any(not n.text() for n in authors)
            or not _official_url(urljoin(_year_url(year), title.attrs.get('href', '')), '/the-library/books/')
            or any(not _author_url(urljoin(_year_url(year), n.attrs.get('href', ''))) for n in authors)):
        raise DublinSourceError(f'Missing Dublin {year} work identity')
    if not single:
        reported = _one((n for n in card.walk() if n.has('books-list-item-year')), 'award year')
        if reported.text() != str(year):
            raise DublinSourceError(f'Wrong year on Dublin {year} card')
    return AwardResult(work_title=title.text(), work_author=' & '.join(n.text() for n in authors),
                       award_name=AWARD_NAME, award_year=year, category=None, status=status,
                       rank=None, source_name=SOURCE_NAME, source_url=source_url)


def _url_year(url):
    if not _official_url(url, '/the-library/prize-years/'):
        return None
    match = re.fullmatch(r'/the-library/prize-years/(\d{4})(?:-[a-z0-9-]+)?/', urlparse(url).path)
    return int(match[1]) if match else None


def _cards(root):
    return [n for n in root.walk() if n.has('books-list-item')
            and not n.has('fxb-mod-list-footer-button-wrap')]


def _list_request_url(grid):
    # Public GET parameters used by the site's own fz0_loadTheLibraryMod.
    cats = grid.attrs.get('data-book-cats-ids', '')
    if grid.attrs.get('data-list-type') != 'by_book_category' or not re.fullmatch(r'\d+,\d+', cats):
        raise DublinSourceError('Unexpected Dublin full-list filter')
    fields = ('order_by', 'order', 'custom_classes', 'list_type', 'style_preset',
              'list_pattern', 'books_ids', 'authors_ids', 'translators_ids',
              'libraries_ids', 'book_cats_ids', 'library_cats_ids', 'search_by_text')
    params = {k: grid.attrs.get('data-' + k.replace('_', '-'), '') for k in fields}
    params.update(action='fz0_ajax_load_books_list_item_block', load_mode='ajax-load',
                  current_page='1', display_limit='-1', footer_type='none',
                  prize_year_ids=grid.attrs.get('data-prize-years-ids', ''))
    return 'https://dublinliteraryaward.ie/wp-admin/admin-ajax.php?' + urlencode(params)


def _parse_year(html, year, source_url=None, fetch_list=None):
    root = _tree(html)
    canonical = _one((n for n in root.walk() if n.tag == 'link' and n.attrs.get('rel') == 'canonical'), 'canonical URL')
    actual_url = canonical.attrs.get('href', '')
    if _url_year(actual_url) != year or (source_url is not None and actual_url != source_url):
        raise DublinSourceError(f'Dublin returned the wrong archive page for {year}')
    winners = [n for n in root.walk() if n.has('fxb-books-single-cover-block')]
    if len(winners) > 1:
        raise DublinSourceError(f'Ambiguous Dublin {year} winner')
    records = []
    for winner in winners:
        if re.search(rf'\b{year}\s+Winner\b', winner.text(), re.I):
            records.append(_record(winner, year, 'Winner', actual_url, single=True))
    sections = {}
    statuses = {'SHORTLIST': 'Shortlisted', 'LONGLIST': 'Longlisted', 'NOMINATED': 'Nominated'}
    for block in root.walk():
        if not block.has('fxb-books-list-block'):
            continue
        headings = [n.text().upper() for n in block.walk() if n.has('block-heading')]
        if len(headings) != 1 or headings[0] not in statuses:
            continue
        heading = headings[0]
        if heading in sections:
            raise DublinSourceError(f'Ambiguous Dublin {year} {heading} section')
        grid = _one((n for n in block.walk() if 'data-display-limit' in n.attrs), 'list grid')
        status = statuses[heading]
        preview = [_record(n, year, status, actual_url) for n in _cards(grid)]
        group = preview
        full = grid
        if grid.attrs['data-display-limit'] != '-1':
            if fetch_list is None:
                raise DublinSourceError(f'Dublin {year} {heading} may be truncated')
            full = _tree(fetch_list(_list_request_url(grid)))
            if any(n.has('pagination-mod') and any(a.tag == 'a' and a.attrs.get('href')
                                                      for a in n.walk()) for n in full.walk()):
                raise DublinSourceError(f'Dublin {year} full list is still paginated')
            group = [_record(n, year, status, actual_url) for n in _cards(full)]
        identities = {(_key(r.work_title), _key(r.work_author)) for r in group}
        explicitly_empty = (not preview and not group
                            and any(n.has('not-found') for n in grid.walk())
                            and any(n.has('not-found') for n in full.walk()))
        if ((not group and not explicitly_empty) or len(group) != len(identities)
                or not {(_key(r.work_title), _key(r.work_author)) for r in preview} <= identities):
            raise DublinSourceError(f'Empty, duplicate or incomplete Dublin {year} {heading}')
        sections[heading] = group
        records.extend(group)
    if not sections or (year < datetime.now(timezone.utc).year and 'SHORTLIST' not in sections):
        raise DublinSourceError(f'Missing Dublin {year} award sections')
    if not ({'NOMINATED', 'LONGLIST'} & sections.keys()):
        raise DublinSourceError(f'Missing Dublin {year} nominations')
    dedup = {}
    for record in records:
        identity = (_key(record.work_title), _key(record.work_author))
        previous = dedup.get(identity)
        if previous is None or _STATUS_PRIORITY[record.status] > _STATUS_PRIORITY[previous.status]:
            dedup[identity] = record
    _validate_year(tuple(dedup.values()), year)
    return tuple(dedup.values())


def _validate_year(group, year):
    winners = sum(r.status == 'Winner' for r in group)
    finalists = sum(r.status in ('Winner', 'Shortlisted') for r in group)
    historical = year < datetime.now(timezone.utc).year
    if (len(group) < _MIN_YEAR_CANDIDATES.get(year, 1) or winners > 1 or (historical and winners != 1)
            or ((historical or winners) and finalists < _MIN_YEAR_RECORDS.get(year, 2))):
        raise DublinSourceError(f'Incomplete Dublin {year} results')


def _parse_years(xml):
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise DublinSourceError('Unreadable Dublin prize-year sitemap') from exc
    ns = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
    if root.tag != ns + 'urlset':
        raise DublinSourceError('Unexpected Dublin sitemap structure')
    years = {}
    for node in root.findall(ns + 'url/' + ns + 'loc'):
        url = node.text or ''
        year = _url_year(url)
        if year and 1996 <= year <= datetime.now(timezone.utc).year:
            if year in years and years[year] != url:
                raise DublinSourceError(f'Conflicting Dublin {year} sitemap URLs')
            years[year] = url
    if not years or max(years) < REVIEWED_MIN_YEAR or set(years) != set(range(1996, max(years) + 1)):
        raise DublinSourceError('Incomplete Dublin prize-year sitemap')
    return dict(sorted(years.items()))


def _discover_years():
    return _parse_years(_fetch_html(SITEMAP_URL))


def _fetch_html(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Calibre-Awards/0.3.0 (award lookup)',
                                                  'Accept-Encoding': 'identity'})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200 or response.geturl() != url:
                raise DublinSourceError(f'Unexpected Dublin response for {url}')
            return response.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        exc.close()
        raise DublinSourceError(f'Dublin request failed with HTTP {exc.code}: {url}') from exc
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError) as exc:
        raise DublinSourceError(f'Dublin archive unavailable: {url}: {exc}') from exc


def _validate(records, years):
    if (not years or max(years) < REVIEWED_MIN_YEAR or list(years) != list(range(1996, max(years) + 1))
            or max(years) > datetime.now(timezone.utc).year):
        raise DublinSourceError('Invalid Dublin cache coverage')
    identities = set()
    for r in records:
        if (not isinstance(r.work_title, str) or not r.work_title.strip()
                or not isinstance(r.work_author, str) or not r.work_author.strip()
                or type(r.award_year) is not int or r.award_year not in years or r.award_name != AWARD_NAME
                or r.source_name != SOURCE_NAME or _url_year(r.source_url or '') != r.award_year
                or r.category is not None or r.rank is not None or r.status not in _STATUS_PRIORITY
                or r.identity_kind != 'work' or r.is_specifically_cited_work
                or r.identity_confirmation_required or r.source_identity_note is not None
                or r.notes is not None or r.source_details):
            raise DublinSourceError('Invalid Dublin cached record')
        identity = (r.award_year, _key(r.work_title), _key(r.work_author))
        if identity in identities:
            raise DublinSourceError('Duplicate Dublin cached record')
        identities.add(identity)
    for year in years:
        _validate_year([r for r in records if r.award_year == year], year)


def _load_disk():
    payload = cache.load_source_cache(SOURCE_KEY, CACHE_VERSION)
    if payload is None:
        return None
    try:
        years = tuple(payload['coverage']['years'])
        records = tuple(AwardResult(**dict(row, source_details=tuple(row.get('source_details', ())))) for row in payload['records'])
        _validate(records, years)
        urls = [SITEMAP_URL] + [next(r.source_url for r in records if r.award_year == y) for y in years]
        if payload['source_urls'] != urls or any(r.source_url != urls[years.index(r.award_year) + 1] for r in records):
            return None
        return records, payload
    except (KeyError, TypeError, ValueError, AttributeError, DublinSourceError):
        return None


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
            year_urls = _discover_years()
            years = tuple(year_urls)
            if disk and max(years) < max(disk[1]['coverage']['years']):
                raise DublinSourceError('Dublin discovered coverage regressed below saved archive')
            def load_year(year):
                return _parse_year(_fetch_html(year_urls[year]), year, year_urls[year], fetch_list=_fetch_html)
            with ThreadPoolExecutor(max_workers=3) as pool:
                records = tuple(r for group in pool.map(load_year, years) for r in group)
            _validate(records, years)
        except Exception:
            if disk:
                _records = disk[0]
                return _records
            raise
        cache.save_source_cache(SOURCE_KEY, CACHE_VERSION, records=[asdict(r) for r in records],
                                source_urls=[SITEMAP_URL] + list(year_urls.values()),
                                coverage={'years': list(years)}, ttl_seconds=CACHE_TTL_SECONDS)
        _records = records
        return records


def _reset_runtime_state():
    global _records
    with _lock:
        _records = None


def lookup(title, author, series=None):
    if not title.strip() or not author.strip():
        raise ValueError('title and author must be non-empty')
    return [r for r in _get_records() if _key(title) == _key(r.work_title) and _key(author) == _key(r.work_author)]


# Coordinate RAM freshness and explicit refresh on retrieval workers.
import sys as _runtime_sys
from ..cache import source_runtime_guard as _runtime_guard
lookup = _runtime_guard(_runtime_sys.modules[__name__], lookup)
_get_records = _runtime_guard(_runtime_sys.modules[__name__], _get_records)
