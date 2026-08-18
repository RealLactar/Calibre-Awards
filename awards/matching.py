"""Shared title-matching helpers used by award sources.

Calibre-free. Keep this module small: do not collect source-specific
normalization here.
"""

from __future__ import annotations

import re

_STANDALONE_AMPERSAND_RE = re.compile(r'\s+&\s+')


def normalize_title_conjunctions(value: str) -> str:
    """Treat a whitespace-bounded '&' token as the word 'and'.

    Embedded ampersands such as R&B or AT&T are left unchanged.
    """
    return _STANDALONE_AMPERSAND_RE.sub(' and ', value)
