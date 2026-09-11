"""Calibre-free layout checks for the Check Awards progress dialog.

These tests inspect edit_metadata_hook.py text. They do not import Qt or
construct widgets, matching other GUI-boundary tests in this suite.
"""

from __future__ import annotations

import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HOOK_PATH = _REPO_ROOT / 'edit_metadata_hook.py'


def _hook_text() -> str:
    return _HOOK_PATH.read_text(encoding='utf-8')


def _progress_dialog_block() -> str:
    text = _hook_text()
    start = text.index('class _LookupProgressDialog')
    end = text.index('class _LookupUiReceiver')
    return text[start:end]


class LookupProgressDialogLayoutTests(unittest.TestCase):
    def test_wrapping_helper_uses_preferred_minimum_policy(self):
        text = _hook_text()
        self.assertIn('def _prepare_wrapping_label(label):', text)
        helper = text.split('def _prepare_wrapping_label(label):', 1)[1]
        helper = helper.split('class _LookupProgressDialog', 1)[0]
        self.assertIn('label.setWordWrap(True)', helper)
        self.assertIn('QSizePolicy.Policy.Preferred', helper)
        self.assertIn('QSizePolicy.Policy.Minimum', helper)

    def test_progress_layout_uses_minimum_size_constraint(self):
        block = _progress_dialog_block()
        self.assertIn(
            'layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)',
            block,
        )

    def test_first_search_and_later_search_wrapping_labels_use_helper(self):
        block = _progress_dialog_block()
        init = block.split('def __init__', 1)[1].split('def schedule_show', 1)[0]
        self.assertIn("if show_first_search_warning:", init)
        self.assertIn('_prepare_wrapping_label(heading)', init)
        self.assertIn('_prepare_wrapping_label(intro)', init)
        self.assertIn('_prepare_wrapping_label(warning)', init)
        self.assertIn('_prepare_wrapping_label(later)', init)
        self.assertIn('self._status = _prepare_wrapping_label(', init)
        self.assertIn('self._last_completed = _prepare_wrapping_label(', init)
        self.assertIn('self._cancel_note', init)
        self.assertIn('_prepare_wrapping_label(self._cancel_note)', init)
        self.assertEqual(init.count('_prepare_wrapping_label('), 7)

    def test_elapsed_label_is_not_word_wrapped(self):
        init = _progress_dialog_block().split('def __init__', 1)[1]
        init = init.split('def schedule_show', 1)[0]
        elapsed_index = init.index('self._elapsed = QLabel(')
        next_label = init.find('self._cancel_note', elapsed_index)
        elapsed_block = init[elapsed_index:next_label]
        self.assertNotIn('setWordWrap', elapsed_block)
        self.assertNotIn('_prepare_wrapping_label', elapsed_block)

    def test_progress_updates_do_not_reset_label_policy(self):
        block = _progress_dialog_block()
        progress = block.split('def handle_progress', 1)[1]
        progress = progress.split('def cancel_waiting', 1)[0]
        self.assertIn('self._last_completed.setText(', progress)
        self.assertIn('self._status.setText(', progress)
        self.assertNotIn('setSizePolicy', progress)
        self.assertNotIn('setWordWrap', progress)

    def test_cancel_button_box_remains(self):
        block = _progress_dialog_block()
        self.assertIn(
            'QDialogButtonBox.StandardButton.Cancel',
            block,
        )
        self.assertIn('buttons.rejected.connect(self.cancel_waiting)', block)

    def test_no_fixed_geometry_or_layout_timers_were_added(self):
        block = _progress_dialog_block()
        for forbidden in (
            'setFixedHeight',
            'setFixedSize',
            'setMinimumHeight',
            'setMinimumWidth',
            'setMaximumHeight',
            'setMaximumWidth',
            'adjustSize(',
            'resize(',
            'QScrollArea',
            'QTextEdit',
            'QTextBrowser',
        ):
            self.assertNotIn(forbidden, block)


if __name__ == '__main__':
    unittest.main()
