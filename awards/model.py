"""Factual award records. Qualification, formatting, and GUI live elsewhere."""

from dataclasses import dataclass

_IDENTITY_KINDS = frozenset({'work', 'series', 'author'})


@dataclass(frozen=True, slots=True)
class AwardResult:
    """One source-reported award fact for a looked-up Calibre book.

    This object is not a qualification decision. Parsers fill it; the
    qualifier and GUI consume it later.

    identity_kind is the entity that received the award:

    - work: a specific title
    - series: a series as a whole
    - author: a person, typically a laureate

    work_title always holds that entity's official source name, even when
    the entity is a series or an author. For identity_kind='author',
    work_title and work_author may both contain the official author name.

    is_specifically_cited_work is semantic state, independent of notes and
    of any user-facing caption. It may be True only when identity_kind is
    'work'. notes is human/source commentary, not hidden control state.

    identity_confirmation_required is independent of qualification. When True,
    the GUI must not auto-select the row even if the result QUALIFIES.
    source_identity_note is factual mismatch text, not a behavior switch.
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
    is_specifically_cited_work: bool = False
    identity_confirmation_required: bool = False
    source_identity_note: str | None = None

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
        if not isinstance(self.is_specifically_cited_work, bool):
            raise ValueError('is_specifically_cited_work must be a bool')
        if self.is_specifically_cited_work and kind != 'work':
            raise ValueError(
                "is_specifically_cited_work requires identity_kind to be 'work'"
            )
        if not isinstance(self.identity_confirmation_required, bool):
            raise ValueError('identity_confirmation_required must be a bool')
        if self.identity_confirmation_required:
            note = self.source_identity_note
            if not isinstance(note, str) or not note.strip():
                raise ValueError(
                    'source_identity_note is required when '
                    'identity_confirmation_required is True'
                )
        elif self.source_identity_note is not None:
            raise ValueError(
                'source_identity_note requires identity_confirmation_required'
            )
