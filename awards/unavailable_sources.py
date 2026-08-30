"""Informational award sources that are not executable.

These entries appear in Preferences so users can see a considered award that
cannot currently run. They are not lookup sources: they have no checkbox,
Refresh action, engine registration, or enablement preference.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UnavailableAwardSourceInfo:
    """User-facing status for one deferred or blocked award source."""

    display_name: str
    status: str
    tooltip: str

    def __post_init__(self) -> None:
        if (
            not self.display_name
            or not self.display_name.strip()
            or self.display_name != self.display_name.strip()
        ):
            raise ValueError('display_name must be a non-empty string')
        if (
            not self.status
            or not self.status.strip()
            or self.status != self.status.strip()
        ):
            raise ValueError('status must be a non-empty string')
        if (
            not self.tooltip
            or not self.tooltip.strip()
            or self.tooltip != self.tooltip.strip()
        ):
            raise ValueError('tooltip must be a non-empty string')


UNAVAILABLE_AWARD_SOURCES: tuple[UnavailableAwardSourceInfo, ...] = (
    UnavailableAwardSourceInfo(
        display_name='National Book Awards',
        status='Transport blocked',
        tooltip=(
            'The National Book Foundation website currently requires a '
            'JavaScript robot challenge that Calibre cannot complete. This '
            'award will be revisited if ordinary automated access becomes '
            'available.'
        ),
    ),
)


def unavailable_award_sources() -> tuple[UnavailableAwardSourceInfo, ...]:
    """Return informational unavailable-source rows in UI order."""
    return UNAVAILABLE_AWARD_SOURCES
