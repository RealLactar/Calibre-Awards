"""Orchestrate award-source lookup, policy selection, and qualification."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .model import AwardResult
from .qualifier import QualificationResult, qualify_award_result
from .registry import find_award_policy
from .source_registry import AWARD_SOURCES, AwardSource


@dataclass(frozen=True, slots=True)
class AwardAssessment:
    result: AwardResult
    qualification: QualificationResult


@dataclass(frozen=True, slots=True)
class SourceFailure:
    source_name: str
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class AwardLookupReport:
    assessments: tuple[AwardAssessment, ...]
    failures: tuple[SourceFailure, ...]


@dataclass(frozen=True, slots=True)
class LookupProgress:
    completed_sources: int
    total_sources: int
    source_name: str | None


ProgressCallback = Callable[[LookupProgress], None]


def assess_award_result(result: AwardResult) -> AwardAssessment:
    """Qualify one factual AwardResult using any matching registry policy."""
    policy = find_award_policy(result)
    qualification = qualify_award_result(result, policy)
    return AwardAssessment(result=result, qualification=qualification)


def _award_sources_for_keys(enabled_source_keys) -> tuple[AwardSource, ...]:
    """Select registered sources by key, preserving AWARD_SOURCES order."""
    if enabled_source_keys is None:
        return AWARD_SOURCES
    allowed = frozenset(enabled_source_keys)
    return tuple(source for source in AWARD_SOURCES if source.key in allowed)


def lookup_awards(
    title: str,
    author: str,
    series: str | None = None,
    on_progress: ProgressCallback | None = None,
    *,
    enabled_source_keys=None,
) -> AwardLookupReport:
    """Search configured award sources and return assessments plus failures.

    enabled_source_keys=None uses every registered source. An empty collection
    uses none. Unknown keys are ignored. Order follows AWARD_SOURCES.
    """
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')
    cleaned_series = None if series is None else str(series).strip() or None
    return _lookup_awards_from_sources(
        cleaned_title,
        cleaned_author,
        _award_sources_for_keys(enabled_source_keys),
        series=cleaned_series,
        on_progress=on_progress,
    )


def _lookup_one_source(
    source: AwardSource,
    title: str,
    author: str,
    series: str | None,
) -> list[AwardResult] | SourceFailure:
    try:
        return source.lookup(title, author, series=series)
    except Exception as exc:
        return SourceFailure(
            source_name=source.display_name,
            error_type=type(exc).__name__,
            message=str(exc),
        )


def _lookup_awards_from_sources(
    title: str,
    author: str,
    sources: Iterable[AwardSource],
    series: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> AwardLookupReport:
    """Run lookups against an explicit source iterable; used by tests."""
    source_list = tuple(sources)
    total = len(source_list)
    if on_progress is not None:
        on_progress(
            LookupProgress(
                completed_sources=0,
                total_sources=total,
                source_name=None,
            )
        )

    slots: list[list[AwardResult] | SourceFailure | None] = [None] * total
    if total:
        max_workers = total
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_map = {
                pool.submit(
                    _lookup_one_source, source, title, author, series
                ): index
                for index, source in enumerate(source_list)
            }
            completed = 0
            for future in as_completed(future_map):
                index = future_map[future]
                source = source_list[index]
                slots[index] = future.result()
                completed += 1
                if on_progress is not None:
                    on_progress(
                        LookupProgress(
                            completed_sources=completed,
                            total_sources=total,
                            source_name=source.display_name,
                        )
                    )

    assessments: list[AwardAssessment] = []
    failures: list[SourceFailure] = []
    for slot in slots:
        if isinstance(slot, SourceFailure):
            failures.append(slot)
            continue
        if not slot:
            continue
        for result in slot:
            assessments.append(assess_award_result(result))
    return AwardLookupReport(
        assessments=tuple(assessments),
        failures=tuple(failures),
    )
