"""Calibre-free checks for Check Awards button visibility."""

from __future__ import annotations

import unittest
from pathlib import Path

from awards.source_registry import AWARD_SOURCES, AwardSource
from awards.source_settings import compute_enabled_source_keys
from awards.unavailable_sources import unavailable_award_sources

_HOOK_PATH = Path(__file__).resolve().parents[1] / 'edit_metadata_hook.py'
_EXECUTABLE_KEYS = tuple(source.key for source in AWARD_SOURCES)


def _hook_text() -> str:
    return _HOOK_PATH.read_text(encoding='utf-8')


def _function_block(name: str, next_name: str) -> str:
    text = _hook_text()
    start = text.index(f'def {name}(')
    end = text.index(f'def {next_name}(', start)
    return text[start:end]


def _enabled_keys(disabled_keys) -> tuple[str, ...]:
    return compute_enabled_source_keys(_EXECUTABLE_KEYS, disabled_keys)


class ExecutableSourceVisibilityTests(unittest.TestCase):
    def test_one_executable_source_enabled_allows_injection(self):
        enabled = _enabled_keys(_EXECUTABLE_KEYS[1:])
        self.assertEqual(enabled, (_EXECUTABLE_KEYS[0],))
        self.assertTrue(enabled)

    def test_multiple_executable_sources_enabled_allow_injection(self):
        enabled = _enabled_keys(_EXECUTABLE_KEYS[2:])
        self.assertEqual(enabled, _EXECUTABLE_KEYS[:2])
        self.assertTrue(enabled)

    def test_all_executable_sources_disabled_skips_injection(self):
        self.assertEqual(_enabled_keys(_EXECUTABLE_KEYS), ())

    def test_informational_sources_do_not_count_as_executable(self):
        informational = unavailable_award_sources()
        self.assertTrue(informational)
        self.assertTrue(all(not hasattr(info, 'lookup') for info in informational))
        self.assertTrue(all(not hasattr(info, 'key') for info in informational))
        self.assertEqual(_enabled_keys(_EXECUTABLE_KEYS), ())

    def test_visibility_does_not_call_a_failing_source(self):
        calls = []

        def failing_lookup(title, author, series=None):
            calls.append((title, author, series))
            raise RuntimeError('temporarily unreachable')

        source = AwardSource('failing', 'Failing source', failing_lookup)
        enabled = compute_enabled_source_keys((source.key,), ())
        self.assertEqual(enabled, ('failing',))
        self.assertEqual(calls, [])

    def test_new_dialog_rechecks_zero_to_one_transition(self):
        self.assertEqual(_enabled_keys(_EXECUTABLE_KEYS), ())
        self.assertEqual(
            _enabled_keys(_EXECUTABLE_KEYS[1:]),
            (_EXECUTABLE_KEYS[0],),
        )

    def test_new_dialog_rechecks_one_to_zero_transition(self):
        self.assertEqual(
            _enabled_keys(_EXECUTABLE_KEYS[1:]),
            (_EXECUTABLE_KEYS[0],),
        )
        self.assertEqual(_enabled_keys(_EXECUTABLE_KEYS), ())

    def test_unknown_disabled_key_does_not_hide_valid_sources(self):
        enabled = _enabled_keys(('removed_old_source',))
        self.assertEqual(enabled, _EXECUTABLE_KEYS)


class EditMetadataHookVisibilitySourceTests(unittest.TestCase):
    def test_enabled_helper_uses_executable_registry(self):
        text = _hook_text()
        self.assertIn(
            'from calibre_plugins.calibre_awards.awards.source_registry import '
            'AWARD_SOURCES',
            text,
        )
        block = _function_block(
            '_enabled_lookup_source_keys',
            '_start_award_lookup',
        )
        self.assertIn(
            'tuple(source.key for source in AWARD_SOURCES)',
            block,
        )
        self.assertIn("prefs['disabled_source_keys']", block)
        self.assertNotIn('SOURCE_INFOS', block)

    def test_zero_enabled_sources_return_before_button_creation(self):
        block = _function_block(
            '_inject_check_awards_button',
            'install_edit_metadata_hook',
        )
        guard = block.index('if not _enabled_lookup_source_keys():')
        creation = block.index("QPushButton('Check Awards', dialog)")
        insertion = block.index('layout.insertWidget(index, button)')
        self.assertLess(guard, creation)
        self.assertLess(guard, insertion)

    def test_nonempty_injection_path_remains_intact(self):
        block = _function_block(
            '_inject_check_awards_button',
            'install_edit_metadata_hook',
        )
        self.assertIn("QPushButton('Check Awards', dialog)", block)
        self.assertIn('button.setObjectName(BUTTON_OBJECT_NAME)', block)
        self.assertIn(
            'button.clicked.connect(lambda: _start_award_lookup(dialog, button))',
            block,
        )
        self.assertIn('layout.insertWidget(index, button)', block)
        self.assertNotIn('setVisible(', block)
        self.assertNotIn('setEnabled(False)', block)

    def test_click_time_zero_source_guard_remains(self):
        block = _function_block(
            '_start_award_lookup',
            '_inject_check_awards_button',
        )
        guard = block.index('if enabled_keys == ():')
        message = block.index("'No award sources are enabled.")
        worker = block.index('thread = _AwardLookupThread(')
        self.assertLess(guard, message)
        self.assertLess(message, worker)
        self.assertIn('return', block[guard:worker])


if __name__ == '__main__':
    unittest.main()
