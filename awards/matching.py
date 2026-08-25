"""Shared title-matching helpers used by award sources.

Calibre-free. Keep this module small: do not collect source-specific
normalization here. Prefer a miss over treating two different titles as
the same work.
"""

from __future__ import annotations

import re

_STANDALONE_AMPERSAND_RE = re.compile(r'\s+&\s+')


def normalize_title_conjunctions(value: str) -> str:
    """Treat a whitespace-bounded '&' token as the word 'and'.

    Embedded ampersands such as R&B or AT&T are left unchanged. Replacing
    every '&' would merge titles that only share a fragment of punctuation.
    """
    return _STANDALONE_AMPERSAND_RE.sub(' and ', value)
