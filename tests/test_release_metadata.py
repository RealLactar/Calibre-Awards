"""Release-gate checks for version text and the user-facing source catalog."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from awards.source_info import SOURCE_INFOS
from awards.source_registry import AWARD_SOURCES

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PHASE_WORD = re.compile(r'\bphase\b', re.IGNORECASE)
_VERSION_TUPLE = re.compile(
    r'version\s*=\s*\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\)'
)
_CHANGELOG_VERSION = re.compile(r'(?m)^## (\d+\.\d+\.\d+)\b')


def _readme_award_table_names(readme: str) -> list[str]:
    section = readme.split('## Supported awards', 1)[1]
    section = section.split('\n## ', 1)[0]
    names = []
    for line in section.splitlines():
        if not line.startswith('|'):
            continue
        label = line.strip().strip('|').split('|', 1)[0].strip()
        if not label or label == 'Award source' or set(label) <= set('-: '):
            continue
        names.append(label)
    return names


class ReleaseMetadataTests(unittest.TestCase):
    def test_readme_executable_catalog_matches_registry(self):
        readme = (_REPO_ROOT / 'README.md').read_text(encoding='utf-8')
        stated = re.search(
            r'\*\*(\d+) executable award sources\*\*',
            readme,
        )
        self.assertIsNotNone(stated)
        names = _readme_award_table_names(readme)
        registered = [source.display_name for source in AWARD_SOURCES]
        self.assertEqual(int(stated.group(1)), len(AWARD_SOURCES))
        self.assertEqual(names, registered)
        self.assertNotIn('National Book Awards', names)

    def test_source_info_user_text_has_no_roadmap_phase_wording(self):
        for info in SOURCE_INFOS:
            texts = [info.display_name, info.description, *info.categories]
            if info.limitation:
                texts.append(info.limitation)
            for text in texts:
                self.assertIsNone(
                    _PHASE_WORD.search(text),
                    f'{info.key}: {text}',
                )

    def test_plugin_version_matches_newest_changelog_heading(self):
        init_text = (_REPO_ROOT / '__init__.py').read_text(encoding='utf-8')
        match = _VERSION_TUPLE.search(init_text)
        self.assertIsNotNone(match)
        version = '.'.join(match.groups())
        changelog = (_REPO_ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
        headings = _CHANGELOG_VERSION.findall(changelog)
        self.assertTrue(headings)
        self.assertEqual(headings[0], version)
        readme = (_REPO_ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn(f'**{version} beta**', readme)
        self.assertIn(f'Calibre-Awards-{version}.zip', readme)
