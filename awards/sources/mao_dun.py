"""Official Mao Dun winners, honorary awards and reviewed nomination editions."""
from __future__ import annotations
import json
import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from .. import cache
from ..model import AwardResult

SOURCE_KEY = 'mao_dun'
AWARD_NAME = 'Mao Dun Literature Prize'
SOURCE_NAME = 'Chinese Writers Association / China Writer'
SOURCE_HOME_URL = 'https://www.chinawriter.com.cn/403973/403974/index.html'
WINNERS_URL = 'https://www.chinawriter.com.cn/n1/2019/0816/c405645-31300293.html'
NOMINEES_URL = 'https://www.chinawriter.com.cn/404087/404988/457894/index.html'
SOURCE_URLS = [WINNERS_URL, NOMINEES_URL]
CATEGORIES = ('Novel',)
CACHE_VERSION = 1
CACHE_TTL_SECONDS = 7 * 86400 + 23 * 3600
TIMEOUT_SECONDS = 20
_VOID = frozenset('area base br col embed hr img input link meta param source track wbr'.split())
_records = None
_reference = None
_lock = threading.RLock()
_NUMBERS = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,'十一':11}

class MaoDunSourceError(RuntimeError):
    """Official records are unavailable, incomplete or outside reviewed coverage."""

def _text(value):
    return re.sub(r'\s+', ' ', value).strip()

def _key(value):
    return _text(unicodedata.normalize('NFKC',value).casefold().replace('’', "'"))

def _author_key(value):
    key=_key(value)
    # Official tables insert typographic spaces into Chinese names. English names retain spaces.
    return re.sub(r'\s+', '', key) if re.fullmatch(r'[\u3400-\u9fff\s、]+',key) else key

def _title(value):
    match=re.fullmatch(r'《([^》]+)》(.*)',_text(value))
    if not match:
        raise MaoDunSourceError('Unreadable Mao Dun work title')
    return _text(match[1]+match[2])

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


@dataclass(frozen=True)
class _Row:
    edition: int
    year: int
    period: str
    title: str
    source_title: str
    author: str
    publisher: str
    status: str
    source_url: str


def _reference_data():
    global _reference
    if _reference is None:
        path='awards/data/mao_dun_mappings.json'
        resource=globals().get('get_resources')
        try:
            raw=resource(path) if resource else (Path(__file__).resolve().parents[2]/path).read_bytes()
            _reference=json.loads(raw.decode('utf-8'))
        except (OSError, ValueError, AttributeError) as exc:
            raise MaoDunSourceError('Reviewed Mao Dun reference data could not be read') from exc
    return _reference


def _parse_winners(html):
    root=_tree(html)
    if not any(n.tag=='em' and n.attrs.get('id')=='newstit' and n.text()=='历届茅盾文学奖获奖作品一览' for n in root.walk()):
        raise MaoDunSourceError('Wrong Mao Dun winner archive')
    articles=[n for n in root.walk() if n.has('end_article')]
    if len(articles)!=1:
        raise MaoDunSourceError('Missing Mao Dun archive content')
    rows=[]; edition=None; period=None
    for node in articles[0].children:
        if not isinstance(node,_Node): continue
        if node.tag=='p':
            match=re.search(r'第([一二三四五六七八九十]+)届茅盾文学奖获奖篇目[（(](\d{4})[—–-](\d{4})[）)]',node.text())
            if match:
                edition=_NUMBERS.get(match[1]); period=f'{match[2]}–{match[3]}'
                if edition is None or str(edition) not in _reference_data()['editions']:
                    raise MaoDunSourceError('New Mao Dun edition requires reviewed award-date metadata')
        elif node.tag=='table':
            if edition is None: raise MaoDunSourceError('Mao Dun table has no edition')
            honor=False
            for tr in (n for n in node.walk() if n.tag=='tr'):
                if re.sub(r'\s+','',tr.text())=='荣誉奖': honor=True; continue
                cells=[n for n in tr.children if isinstance(n,_Node) and n.tag=='td']
                if not cells: continue
                if len(cells)!=3: raise MaoDunSourceError('Changed Mao Dun table columns')
                label,author,publisher=(_text(n.text()) for n in cells)
                rows.append(_Row(edition,_reference_data()['editions'][str(edition)]['year'],period,
                    _title(label),label,author,publisher,'Honorary award' if honor else 'Winner',WINNERS_URL))
    _validate_winners(rows)
    return tuple(rows)


def _validate_winners(rows):
    reference=_reference_data()['editions']
    if {r.edition for r in rows} != {int(k) for k in reference}:
        raise MaoDunSourceError('Incomplete Mao Dun winner editions')
    seen=set()
    for r in rows:
        expected=reference.get(str(r.edition))
        if (type(r.edition) is not int or type(r.year) is not int or not expected
            or r.year!=expected['year'] or r.period!=expected['period']
            or r.status not in ('Winner','Honorary award') or r.source_url!=WINNERS_URL
            or any(not isinstance(x,str) or not x.strip() for x in (r.title,r.source_title,r.author,r.publisher))
            or r.title!=_title(r.source_title)):
            raise MaoDunSourceError('Invalid Mao Dun winner record')
        identity=(r.edition,_key(r.title),_author_key(r.author))
        if identity in seen: raise MaoDunSourceError('Duplicate Mao Dun winner record')
        seen.add(identity)
    for edition,expected in reference.items():
        group=[r for r in rows if r.edition==int(edition)]
        if sum(r.status=='Winner' for r in group)!=expected['winners'] or sum(r.status=='Honorary award' for r in group)!=expected['honorary']:
            raise MaoDunSourceError('Incomplete Mao Dun award categories')


def _parse_nominees(html):
    root=_tree(html)
    if not any(n.tag=='title' and n.text().startswith('第十一届茅盾文学奖--') for n in root.walk()):
        raise MaoDunSourceError('Wrong Mao Dun nomination edition')
    # Locate the exact heading and following candidate container, never biography/entry lists.
    sequence=list(root.walk()); blocks=[]
    for index,node in enumerate(sequence):
        if node.tag=='h1' and node.text()=='提名作品':
            for following in sequence[index+1:]:
                if following.tag=='h1': break
                if following.tag=='div' and following.has('p3_con'):
                    blocks.append(following); break
    if len(blocks)!=1: raise MaoDunSourceError('Missing Mao Dun nominated-work section')
    rows=[]
    for li in (n for n in blocks[0].walk() if n.tag=='li'):
        paragraphs=[n for n in li.walk() if n.tag=='p']
        if len(paragraphs)!=1: raise MaoDunSourceError('Unreadable Mao Dun nominee')
        match=re.fullmatch(r'作品：\s*(《[^》]+》.*?)\s*作者：\s*(.+)',paragraphs[0].text())
        if not match: raise MaoDunSourceError('Missing Mao Dun nominee identity')
        label,author=match.groups()
        rows.append(_Row(11,2023,'2019–2022',_title(label),_text(label),_text(author),'','Nominated',NOMINEES_URL))
    _validate_nominees(rows)
    return tuple(rows)


def _validate_nominees(rows):
    if len(rows)!=10 or len({(_key(r.title),_author_key(r.author)) for r in rows})!=10:
        raise MaoDunSourceError('Incomplete Mao Dun edition 11 nominations')
    for r in rows:
        if (type(r.edition) is not int or type(r.year) is not int or r.edition!=11 or r.year!=2023 or r.period!='2019–2022'
            or r.status!='Nominated' or r.source_url!=NOMINEES_URL or r.publisher!=''
            or any(not isinstance(v,str) or not v.strip() for v in (r.title,r.source_title,r.author))
            or r.title!=_title(r.source_title)):
            raise MaoDunSourceError('Invalid Mao Dun nominee record')


def _merge(winners,nominees):
    keys={(r.edition,_key(r.title),_author_key(r.author)) for r in winners}
    return tuple(winners)+tuple(r for r in nominees if (r.edition,_key(r.title),_author_key(r.author)) not in keys)


def _load_disk():
    payload=cache.load_source_cache(SOURCE_KEY,CACHE_VERSION)
    if payload is None: return None
    try:
        rows=tuple(_Row(**r) for r in payload['records'])
        winners=tuple(r for r in rows if r.source_url==WINNERS_URL)
        nominees=tuple(r for r in rows if r.source_url==NOMINEES_URL)
        _validate_winners(winners); _validate_nominees(nominees)
        if len(winners)+len(nominees)!=len(rows) or payload['source_urls']!=SOURCE_URLS or payload['coverage']!={'last_edition':11,'nomination_editions':[11]}:
            return None
        return rows,payload
    except (TypeError,KeyError,ValueError,AttributeError,MaoDunSourceError): return None


def _get_records():
    global _records
    with _lock:
        if _records is not None: return _records
        disk=_load_disk()
        if disk and (cache.cache_is_fresh(disk[1]) or not cache.try_claim_stale_refresh(SOURCE_KEY)):
            rows=disk[0]
        else:
            try:
                rows=_parse_winners(_fetch_html(WINNERS_URL))+_parse_nominees(_fetch_html(NOMINEES_URL))
            except Exception:
                if not disk: raise
                rows=disk[0]
            else:
                cache.save_source_cache(SOURCE_KEY,CACHE_VERSION,records=[asdict(r) for r in rows],source_urls=SOURCE_URLS,
                    coverage={'last_edition':11,'nomination_editions':[11]},ttl_seconds=CACHE_TTL_SECONDS)
        _records=_merge([r for r in rows if r.source_url==WINNERS_URL],[r for r in rows if r.source_url==NOMINEES_URL])
        return _records


def _reset_runtime_state():
    global _records,_reference
    with _lock: _records=None; _reference=None


def lookup(title,author,series=None):
    if not title.strip() or not author.strip(): raise ValueError('title and author must be non-empty')
    results=[]
    for row in _get_records():
        aliases=[m for m in _reference_data()['mappings'] if m['edition']==row.edition and m['title_zh']==row.title and _author_key(m['author_zh'])==_author_key(row.author)]
        titles=[row.title,row.source_title]+[t for m in aliases for t in m['titles']]
        authors=[row.author]+[a for m in aliases for a in m['authors']]
        if _key(title) not in {_key(t) for t in titles} or _author_key(author) not in {_author_key(a) for a in authors}: continue
        restricted=any(mark in row.title for mark in ('卷','(一','（一','(修订本)','（修订本）','三部曲'))
        details=[f'Edition {row.edition}; award year {row.year}; eligibility period {row.period}.',f'Original title: {row.source_title} | {row.author}']
        if row.publisher: details.append(f'Original publisher: {row.publisher}')
        if row.status=='Honorary award': details.append('Original status: 荣誉奖 (honorary award), distinct from regular winners.')
        details.extend(f"Verified title/name mapping: {m['titles'][0]} | {m['authors'][0]} ({m['evidence'][0]})" for m in aliases)
        results.append(AwardResult(work_title=row.title,work_author=row.author,award_name=AWARD_NAME,award_year=row.year,
            category=None,status=row.status,rank=None,source_name=SOURCE_NAME,source_url=row.source_url,source_details=tuple(details),
            identity_confirmation_required=restricted,source_identity_note=('Confirm that this book matches the awarded volumes or revised edition: '+row.source_title) if restricted else None))
    return results


def _fetch_html(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Calibre-Awards/0.3.0 (award lookup)', 'Accept-Encoding': 'identity'})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200 or response.url != url:
                raise MaoDunSourceError(f'Unexpected Mao Dun response: {url}')
            return response.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        exc.close()
        raise MaoDunSourceError(f'Mao Dun request failed with HTTP {exc.code}: {url}') from exc
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError) as exc:
        raise MaoDunSourceError(f'Mao Dun source unavailable: {url}: {exc}') from exc


# Coordinate RAM freshness and explicit refresh on retrieval workers.
import sys as _runtime_sys
from ..cache import source_runtime_guard as _runtime_guard
lookup = _runtime_guard(_runtime_sys.modules[__name__], lookup)
_get_records = _runtime_guard(_runtime_sys.modules[__name__], _get_records)
