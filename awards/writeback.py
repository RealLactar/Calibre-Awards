"""Calibre-free helpers for later award write-back into a multiple-text field."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .formatter import DEFAULT_AWARD_OUTPUT_TEMPLATE, format_award_result
from .qualifier import QualificationDecision


def formatted_qualifying_awards(
    report,
    template: str = DEFAULT_AWARD_OUTPUT_TEMPLATE,
) -> list[str]:
    """Return formatted strings for QUALIFIES assessments only."""
    return [
        format_award_result(item.result, template)
        for item in report.assessments
        if item.qualification.decision is QualificationDecision.QUALIFIES
    ]


def _duplicate_key(value: str) -> str:
    return value.strip().casefold()


def unique_award_values(values: Iterable[str]) -> list[str]:
    """Keep first spelling/order; skip blanks and later duplicates."""
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value)
        key = _duplicate_key(text)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(text)
    return unique


def append_award_values(existing: Iterable[str], new: Iterable[str]) -> list[str]:
    """Preserve existing entries; append new values that are not duplicates."""
    merged = [str(value) for value in existing]
    seen = {_duplicate_key(value) for value in merged if _duplicate_key(value)}
    for value in new:
        text = str(value)
        key = _duplicate_key(text)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(text)
    return merged


def replace_award_values(new: Iterable[str]) -> list[str]:
    """Return new values only, with duplicates removed."""
    return unique_award_values(new)


@dataclass(frozen=True, slots=True)
class AwardWritebackPartition:
    """Split formatted awards into values safe for a comma-separated field."""

    safe: list[str]
    rejected_for_comma: list[str]


def partition_comma_unsafe_award_values(
    values: Iterable[str],
) -> AwardWritebackPartition:
    """Keep values with a literal comma intact, but mark them as rejected."""
    safe: list[str] = []
    rejected: list[str] = []
    for value in values:
        text = str(value)
        if ',' in text:
            rejected.append(text)
        else:
            safe.append(text)
    return AwardWritebackPartition(safe=safe, rejected_for_comma=rejected)


@dataclass(frozen=True, slots=True)
class PreparedAwardWriteback:
    """Values ready for a multiple-text field, plus new values rejected for commas."""

    values: list[str]
    rejected_for_comma: list[str]


def prepare_append_award_values(
    existing: Iterable[str],
    new: Iterable[str],
) -> PreparedAwardWriteback:
    """Append only safe new values; never filter or alter existing entries."""
    new_values = [str(value) for value in new]
    partition = partition_comma_unsafe_award_values(new_values)
    return PreparedAwardWriteback(
        values=append_award_values(existing, partition.safe),
        rejected_for_comma=partition.rejected_for_comma,
    )


def prepare_replace_award_values(new: Iterable[str]) -> PreparedAwardWriteback:
    """Replace with unique safe new values; reject comma-containing new values."""
    partition = partition_comma_unsafe_award_values(new)
    return PreparedAwardWriteback(
        values=replace_award_values(partition.safe),
        rejected_for_comma=partition.rejected_for_comma,
    )
