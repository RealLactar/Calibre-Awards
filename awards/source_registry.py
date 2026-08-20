"""Explicit static registry of award lookup sources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .model import AwardResult
from .sources.hugo import lookup as hugo_lookup
from .sources.locus import lookup as locus_lookup
from .sources.nebula import lookup as nebula_lookup
from .sources.pulitzer import lookup as pulitzer_lookup
from .sources.world_fantasy import lookup as world_fantasy_lookup


class AwardSourceLookup(Protocol):
    """Lookup callable: title and author required; series optional."""

    def __call__(
        self,
        title: str,
        author: str,
        series: str | None = None,
    ) -> list[AwardResult]: ...


@dataclass(frozen=True, slots=True)
class AwardSource:
    """One award lookup source. Source-neutral; no qualification or GUI logic."""

    key: str
    display_name: str
    lookup: AwardSourceLookup


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
    AwardSource(
        key='world_fantasy',
        display_name='World Fantasy Awards',
        lookup=world_fantasy_lookup,
    ),
)
