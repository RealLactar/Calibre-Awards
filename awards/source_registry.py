"""Explicit static registry of award lookup sources."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .model import AwardResult
from .sources.hugo import lookup as hugo_lookup
from .sources.locus import lookup as locus_lookup
from .sources.nebula import lookup as nebula_lookup
from .sources.pulitzer import lookup as pulitzer_lookup


@dataclass(frozen=True, slots=True)
class AwardSource:
    """One award lookup source. Source-neutral; no qualification or GUI logic."""

    key: str
    display_name: str
    lookup: Callable[[str, str], list[AwardResult]]


AWARD_SOURCES: tuple[AwardSource, ...] = (
    AwardSource(
        key='pulitzer',
        display_name='Pulitzer Prizes',
        lookup=pulitzer_lookup,
    ),
    AwardSource(
        key='nebula',
        display_name='Nebula Awards',
        lookup=nebula_lookup,
    ),
    AwardSource(
        key='hugo',
        display_name='Hugo Awards',
        lookup=hugo_lookup,
    ),
    AwardSource(
        key='locus',
        display_name='Locus Awards',
        lookup=locus_lookup,
    ),
)
