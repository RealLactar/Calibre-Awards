from dataclasses import dataclass

_IDENTITY_KINDS = frozenset({'work', 'series', 'author'})


@dataclass(frozen=True, slots=True)
class AwardResult:
    """One award-related result for a looked-up Calibre book.

    Source-neutral; no qualification logic.

    identity_kind names the awarded entity. work_title holds that entity's
    official source name:

    - work: official work title
    - series: official series name
    - author: official author/laureate name

    For identity_kind='author', work_title and work_author may both contain
    the official author name.
    """

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
    identity_kind: str = 'work'

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
        kind = self.identity_kind.strip() if self.identity_kind else ''
        if kind not in _IDENTITY_KINDS:
            raise ValueError(
                "identity_kind must be 'work', 'series', or 'author'"
            )
        if kind != self.identity_kind:
            raise ValueError(
                "identity_kind must be 'work', 'series', or 'author'"
            )
