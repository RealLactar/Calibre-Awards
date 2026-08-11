"""Orchestrate award-source lookup, policy selection, and qualification."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .model import AwardResult
from .qualifier import QualificationResult, qualify_award_result
from .registry import find_award_policy
from .sources.pulitzer import lookup as pulitzer_lookup

_SOURCE_LOOKUPS: tuple[Callable[[str, str], list[AwardResult]], ...] = (
    pulitzer_lookup,
)


@dataclass(frozen=True, slots=True)
class AwardAssessment:
    result: AwardResult
    qualification: QualificationResult


def assess_award_result(result: AwardResult) -> AwardAssessment:
    """Qualify one factual AwardResult using any matching registry policy."""
    policy = find_award_policy(result)
    qualification = qualify_award_result(result, policy)
    return AwardAssessment(result=result, qualification=qualification)


def lookup_awards(title: str, author: str) -> list[AwardAssessment]:
    """Search configured award sources and return assessed results."""
    cleaned_title = title.strip()
    cleaned_author = author.strip()
    if not cleaned_title:
        raise ValueError('title must be a non-empty string')
    if not cleaned_author:
        raise ValueError('author must be a non-empty string')

    assessments: list[AwardAssessment] = []
    for source_lookup in _SOURCE_LOOKUPS:
        for result in source_lookup(cleaned_title, cleaned_author):
            assessments.append(assess_award_result(result))
    return assessments
