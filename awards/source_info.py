"""User-facing award-source capability metadata. Calibre-free and Qt-free."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from .sources import hugo, locus, nebula, nobel, pulitzer, world_fantasy

_IDENTITY_SCOPES = frozenset({'work', 'series', 'author'})
_SCOPE_LABELS = {
    'work': 'Work awards',
    'series': 'Series awards',
    'author': 'Author awards',
}


@dataclass(frozen=True, slots=True)
class SourceInfo:
    """Static help metadata for one award source.

    Categories and identity scopes describe current lookup capabilities.
    They do not change lookup, matching, or qualification.
    """

    key: str
    display_name: str
    categories: tuple[str, ...]
    identity_scopes: tuple[str, ...]
    homepage_url: str
    description: str
    limitation: str | None = None

    def __post_init__(self) -> None:
        if not self.key or not self.key.strip() or self.key != self.key.strip():
            raise ValueError('key must be a non-empty string')
        if (
            not self.display_name
            or not self.display_name.strip()
            or self.display_name != self.display_name.strip()
        ):
            raise ValueError('display_name must be a non-empty string')
        if not self.categories:
            raise ValueError('categories must contain at least one label')
        if any(not label or not str(label).strip() for label in self.categories):
            raise ValueError('categories must contain non-empty labels')
        if not self.identity_scopes:
            raise ValueError('identity_scopes must contain at least one scope')
        if any(scope not in _IDENTITY_SCOPES for scope in self.identity_scopes):
            raise ValueError(
                "identity_scopes values must be 'work', 'series', or 'author'"
            )
        if not self.homepage_url or not self.homepage_url.strip():
            raise ValueError('homepage_url must be a non-empty string')
        parsed = urlparse(self.homepage_url.strip())
        if parsed.scheme != 'https' or not parsed.netloc:
            raise ValueError('homepage_url must be an https URL')
        if not self.description or not self.description.strip():
            raise ValueError('description must be a non-empty string')
        if self.limitation is not None and not self.limitation.strip():
            raise ValueError('limitation must be None or a non-empty string')


def _pulitzer_categories() -> tuple[str, ...]:
    return tuple(category for category, _url in pulitzer._CATEGORY_URLS)


def _nebula_categories() -> tuple[str, ...]:
    labels: list[str] = []
    for config in nebula._AWARD_CONFIGS:
        if config.award_name == nebula.AWARD_NAME_NEBULA:
            labels.append(config.category)
        else:
            labels.append(f'{config.award_name} — {config.category}')
    return tuple(labels)


def _hugo_categories() -> tuple[str, ...]:
    return hugo._PARSED_CATEGORIES


def _locus_categories() -> tuple[str, ...]:
    return tuple(locus._SUPPORTED_CATEGORY_LABELS)


def _world_fantasy_categories() -> tuple[str, ...]:
    return world_fantasy._CANONICAL_CATEGORIES


def _nobel_categories() -> tuple[str, ...]:
    return (nobel.CATEGORY_LITERATURE,)


def format_identity_scopes(scopes: tuple[str, ...]) -> str:
    """Return comma-separated user-facing labels for identity scopes."""
    return ', '.join(_SCOPE_LABELS[scope] for scope in scopes)


def format_source_info(info: SourceInfo) -> str:
    """Return a plain-text help block for one source."""
    lines = [
        info.display_name,
        f'Categories: {", ".join(info.categories)}',
        f'Scope: {format_identity_scopes(info.identity_scopes)}',
        info.description.strip(),
    ]
    if info.limitation is not None:
        lines.append(f'Note: {info.limitation.strip()}')
    return '\n'.join(lines)


SOURCE_INFOS: tuple[SourceInfo, ...] = (
    SourceInfo(
        key='pulitzer',
        display_name='Pulitzer Prizes',
        categories=_pulitzer_categories(),
        identity_scopes=('work',),
        homepage_url=pulitzer.SOURCE_HOME_URL,
        description='Fiction and Novel awards from Pulitzer.org.',
        limitation=(
            'Pulitzer.org sometimes blocks automated checks, so this source '
            'may be unavailable. Other award sources still run.'
        ),
    ),
    SourceInfo(
        key='nebula',
        display_name='Nebula Awards',
        categories=_nebula_categories(),
        identity_scopes=('work',),
        homepage_url=nebula.SOURCE_HOME_URL,
        description='Nebula and Andre Norton literary award results.',
    ),
    SourceInfo(
        key='hugo',
        display_name='Hugo Awards',
        categories=_hugo_categories(),
        identity_scopes=('work', 'series'),
        homepage_url=hugo.SOURCE_HOME_URL,
        description=(
            'Hugo work awards and supported series awards, including '
            'historical category names where applicable.'
        ),
    ),
    SourceInfo(
        key='locus',
        display_name='Locus Awards',
        categories=_locus_categories(),
        identity_scopes=('work',),
        homepage_url=locus.SFADB_ORIGIN,
        description=(
            'Ranked Locus literary awards from the Science Fiction Awards '
            'Database.'
        ),
    ),
    SourceInfo(
        key='world_fantasy',
        display_name='World Fantasy Awards',
        categories=_world_fantasy_categories(),
        identity_scopes=('work',),
        homepage_url=world_fantasy.SOURCE_HOME_URL,
        description=(
            'World Fantasy work awards in the supported literary categories.'
        ),
    ),
    SourceInfo(
        key='nobel',
        display_name='NobelPrize.org',
        categories=_nobel_categories(),
        identity_scopes=('author', 'work'),
        homepage_url=nobel.SOURCE_HOME_URL,
        description=(
            'Nobel Prize in Literature results, normally awarded to the '
            'author and shown as [Author: Name]; a small set of specifically '
            'cited works is recognized separately as work awards.'
        ),
    ),
)
