"""Orchestrate award-source lookup, policy selection, and qualification."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .model import AwardResult
from .qualifier import QualificationResult, qualify_award_result
from .registry import find_award_policy
from .sources.nebula import lookup as nebula_lookup
from .sources.pulitzer import lookup as pulitzer_lookup


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
class _SourceLookup:
    name: str
    lookup: Callable[[str, str], list[AwardResult]]


_SOURCE_LOOKUPS: tuple[_SourceLookup, ...] = (
    _SourceLookup(name='Pulitzer Prizes', lookup=pulitzer_lookup),
    _SourceLookup(name='Nebula Awards', lookup=nebula_lookup),
)


def assess_award_result(result: AwardResult) -> AwardAssessment:
    """Qualify one factual AwardResult using any matching registry policy."""
    policy = find_award_policy(result)
    qualification = qualify_award_result(result, policy)
    return AwardAssessment(result=result, qualification=qualification)


def lookup_awards(title: str, author: str) -> AwardLookupReport:
    """Search configured award sources and return assessments plus failures."""
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')

    assessments: list[AwardAssessment] = []
    failures: list[SourceFailure] = []
    for source in _SOURCE_LOOKUPS:
        try:
            results = source.lookup(cleaned_title, cleaned_author)
        except Exception as exc:
            failures.append(
                SourceFailure(
                    source_name=source.name,
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
            )
            continue
        for result in results:
            assessments.append(assess_award_result(result))
    return AwardLookupReport(
        assessments=tuple(assessments),
        failures=tuple(failures),
    )
