from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AwardResult:
    """One award-related result for one work. Source-neutral; no qualification logic."""

    work_title: str
    work_author: str
    award_name: str
    award_year: int | None
    category: str | None
    status: str
    rank: int | None
    source_name: str
    source_url: str | None
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.work_title or not self.work_title.strip():
            raise ValueError('work_title must be a non-empty string')
        if not self.work_author or not self.work_author.strip():
            raise ValueError('work_author must be a non-empty string')
        if not self.award_name or not self.award_name.strip():
            raise ValueError('award_name must be a non-empty string')
        if not self.status or not self.status.strip():
            raise ValueError('status must be a non-empty string')
        if not self.source_name or not self.source_name.strip():
            raise ValueError('source_name must be a non-empty string')
        if self.rank is not None and self.rank <= 0:
            raise ValueError('rank must be greater than zero when set')
        if self.award_year is not None and self.award_year <= 0:
            raise ValueError('award_year must be greater than zero when set')
