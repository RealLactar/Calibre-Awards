"""Offline coverage for informational unavailable award sources."""

from __future__ import annotations

import unittest
from pathlib import Path

from awards.source_info import SOURCE_INFOS
from awards.source_registry import AWARD_SOURCES
from awards.source_settings import compute_enabled_source_keys
from awards.unavailable_sources import (
    UNAVAILABLE_AWARD_SOURCES,
    UNAVAILABLE_SOURCE_INFO_INDICATOR,
    UnavailableAwardSourceInfo,
    unavailable_award_sources,
    unavailable_source_status_text,
    unavailable_source_tooltip_rich_text,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXPECTED_TOOLTIP = (
    'The National Book Foundation website currently requires\n'
    'a JavaScript robot challenge that Calibre cannot complete.\n'
    '\n'
    'This award will be revisited if ordinary automated\n'
    'access becomes available.'
)


class UnavailableAwardSourceInfoModelTests(unittest.TestCase):
    def test_rejects_empty_or_untrimmed_fields(self):
        valid = dict(
            display_name='National Book Awards',
            status='Transport blocked',
            tooltip=_EXPECTED_TOOLTIP,
        )
        with self.assertRaises(ValueError):
            UnavailableAwardSourceInfo(**{**valid, 'display_name': ''})
        with self.assertRaises(ValueError):
            UnavailableAwardSourceInfo(**{**valid, 'display_name': '  Name'})
        with self.assertRaises(ValueError):
            UnavailableAwardSourceInfo(**{**valid, 'status': ''})
        with self.assertRaises(ValueError):
            UnavailableAwardSourceInfo(**{**valid, 'status': ' blocked '})
        with self.assertRaises(ValueError):
            UnavailableAwardSourceInfo(**{**valid, 'tooltip': ''})
        with self.assertRaises(ValueError):
            UnavailableAwardSourceInfo(**{**valid, 'tooltip': '  hint'})


class UnavailableAwardSourceCollectionTests(unittest.TestCase):
    def test_collection_contains_exactly_national_book_awards(self):
        infos = unavailable_award_sources()
        self.assertIs(infos, UNAVAILABLE_AWARD_SOURCES)
        self.assertEqual(len(infos), 1)
        info = infos[0]
        self.assertEqual(info.display_name, 'National Book Awards')
        self.assertEqual(info.status, 'Transport blocked')
        self.assertNotIn(UNAVAILABLE_SOURCE_INFO_INDICATOR, info.status)
        self.assertEqual(info.tooltip, _EXPECTED_TOOLTIP)
        self.assertNotIn('<qt>', info.tooltip)
        self.assertNotIn('<br>', info.tooltip)
        self.assertIn('\n', info.tooltip)
        self.assertFalse(hasattr(info, 'key'))
        self.assertFalse(hasattr(info, 'lookup'))

    def test_is_separate_from_executable_registries(self):
        executable_keys = [source.key for source in AWARD_SOURCES]
        executable_info_keys = [info.key for info in SOURCE_INFOS]
        self.assertEqual(len(executable_keys), 12)
        self.assertEqual(len(executable_info_keys), 12)
        self.assertNotIn('national_book_awards', executable_keys)
        self.assertNotIn('national_book_awards', executable_info_keys)
        self.assertNotIn(
            'National Book Awards',
            [source.display_name for source in AWARD_SOURCES],
        )
        self.assertNotIn(
            'National Book Awards',
            [info.display_name for info in SOURCE_INFOS],
        )
        enabled = compute_enabled_source_keys(executable_info_keys, [])
        self.assertEqual(enabled, tuple(executable_info_keys))
        self.assertNotIn('national_book_awards', enabled)

    def test_no_production_source_file_or_engine_registration(self):
        self.assertFalse(
            (_REPO_ROOT / 'awards' / 'sources' / 'national_book_awards.py').exists()
        )
        engine_text = (_REPO_ROOT / 'awards' / 'engine.py').read_text(
            encoding='utf-8'
        )
        cache_text = (_REPO_ROOT / 'awards' / 'cache_control.py').read_text(
            encoding='utf-8'
        )
        registry_text = (_REPO_ROOT / 'awards' / 'source_registry.py').read_text(
            encoding='utf-8'
        )
        info_text = (_REPO_ROOT / 'awards' / 'source_info.py').read_text(
            encoding='utf-8'
        )
        self.assertNotIn('national_book', engine_text)
        self.assertNotIn('national_book', cache_text)
        self.assertNotIn('national_book', registry_text)
        self.assertNotIn('national_book', info_text)
        self.assertNotIn('unavailable_award_sources', engine_text)
        self.assertNotIn('unavailable_award_sources', cache_text)


class UnavailableSourcePresentationTests(unittest.TestCase):
    def test_status_helper_appends_info_indicator_generically(self):
        self.assertEqual(UNAVAILABLE_SOURCE_INFO_INDICATOR, 'ⓘ')
        self.assertEqual(
            unavailable_source_status_text('Transport blocked'),
            'Transport blocked  ⓘ',
        )
        self.assertEqual(
            unavailable_source_status_text('Deferred'),
            'Deferred  ⓘ',
        )

    def test_tooltip_helper_wraps_plain_text_as_multiline_rich_text(self):
        html = unavailable_source_tooltip_rich_text(_EXPECTED_TOOLTIP)
        self.assertTrue(html.startswith('<qt>'))
        self.assertTrue(html.endswith('</qt>'))
        self.assertIn('<br>', html)
        self.assertGreaterEqual(html.count('<br>'), 3)
        self.assertIn('National Book Foundation', html)
        self.assertIn('JavaScript robot challenge', html)
        self.assertIn('Calibre cannot complete', html)
        self.assertIn('revisited', html)
        self.assertNotIn('HTTP', html)
        self.assertNotIn('Cursor', html)
        self.assertNotIn('SG-Captcha', html)
        self.assertNotEqual(html, _EXPECTED_TOOLTIP.replace('\n', ' '))

    def test_tooltip_helper_is_source_neutral_and_escapes_html(self):
        html = unavailable_source_tooltip_rich_text(
            'First line of a hint.\n'
            'Second line of a hint.\n'
            '\n'
            'A later paragraph with <tag> & more.'
        )
        self.assertIn('<qt>', html)
        self.assertIn('<br>', html)
        self.assertIn('First line of a hint.', html)
        self.assertIn('A later paragraph with &lt;tag&gt; &amp; more.', html)
        self.assertNotIn('<tag>', html)


if __name__ == '__main__':
    unittest.main()
