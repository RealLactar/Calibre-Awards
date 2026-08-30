"""Calibre-free coverage for Award sources cache Refresh controls.

These tests do not import config.py, which requires Calibre and Qt. They
exercise the source-neutral row/callback/confirmation helpers the widget
uses, and inspect config.py text for layout and save_settings boundaries.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from awards.cache_control import (
    CACHE_REFRESH_BUTTON_LABEL,
    SOURCES_GROUP_HINT,
    bind_refresh_enabled_to_checkbox,
    bind_source_refresh_callback,
    cache_refresh_source_rows,
    run_source_cache_refresh_if_confirmed,
    source_cache_refresh_confirm_body,
    source_cache_refresh_confirm_title,
    source_cache_refresh_failure_text,
    source_cache_refresh_status_text,
)
from awards.source_info import SOURCE_INFOS
from awards.source_registry import AWARD_SOURCES
from awards.source_settings import normalize_disabled_source_keys

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_PATH = _REPO_ROOT / 'config.py'


def _config_text() -> str:
    return _CONFIG_PATH.read_text(encoding='utf-8')


def _save_settings_body() -> str:
    text = _config_text()
    marker = 'def save_settings(self):'
    start = text.index(marker)
    rest = text[start:]
    lines = rest.splitlines()
    body = [lines[0]]
    for line in lines[1:]:
        if line.startswith('    def ') or line.startswith('def '):
            break
        body.append(line)
    return '\n'.join(body)


class FakeCheckbox:
    def __init__(self, text, *, checked):
        self.text = text
        self.checked = bool(checked)
        self._toggled = []

    def setChecked(self, checked):
        checked = bool(checked)
        if checked == self.checked:
            return
        self.checked = checked
        for handler in self._toggled:
            handler(checked)

    def isChecked(self):
        return self.checked


class FakeButton:
    def __init__(self, *, enabled):
        self.enabled = bool(enabled)
        self._clicked = []

    def setEnabled(self, enabled):
        self.enabled = bool(enabled)

    def click(self):
        if not self.enabled:
            return
        for handler in self._clicked:
            handler()


class FakeAwardSourcesPanel:
    """Mirrors ConfigWidget source-row Refresh wiring without Qt."""

    def __init__(self, disabled_keys=()):
        disabled = set(normalize_disabled_source_keys(disabled_keys))
        self.status = ''
        self.failure_text = None
        self.confirm_next = True
        self.source_checkboxes = {}
        self.source_refresh_buttons = {}
        for source_key, display_name in cache_refresh_source_rows():
            enabled = source_key not in disabled
            checkbox = FakeCheckbox(display_name, checked=enabled)
            button = FakeButton(enabled=enabled)
            button._clicked.append(
                bind_source_refresh_callback(
                    self._on_refresh_cached_source,
                    source_key,
                    display_name,
                )
            )
            checkbox._toggled.append(bind_refresh_enabled_to_checkbox(button))
            self.source_checkboxes[source_key] = checkbox
            self.source_refresh_buttons[source_key] = button

    def set_checked(self, source_key: str, checked: bool):
        self.source_checkboxes[source_key].setChecked(checked)

    def select_all_sources(self):
        for checkbox in self.source_checkboxes.values():
            checkbox.setChecked(True)

    def select_no_sources(self):
        for checkbox in self.source_checkboxes.values():
            checkbox.setChecked(False)

    def click_refresh(self, source_key: str, *, confirmed=True):
        self.confirm_next = confirmed
        self.source_refresh_buttons[source_key].click()

    def _on_refresh_cached_source(self, source_key: str, display_name: str):
        persistent_ok = run_source_cache_refresh_if_confirmed(
            source_key,
            display_name,
            confirmed=self.confirm_next,
        )
        if persistent_ok is None:
            return
        if persistent_ok:
            self.status = source_cache_refresh_status_text(display_name)
            self.failure_text = None
            return
        self.failure_text = source_cache_refresh_failure_text(display_name)


class AwardSourcesLayoutTests(unittest.TestCase):
    def test_no_separate_award_data_cache_group(self):
        text = _config_text()
        self.assertNotIn('Award data cache', text)
        self.assertNotIn('CACHE_GROUP_TITLE', text)
        self.assertNotIn('QGroupBox(CACHE_GROUP_TITLE', text)
        self.assertNotIn('Refresh All', text)
        self.assertNotIn('Clear Everything', text)
        self.assertIn("QGroupBox('Award sources'", text)
        self.assertIn('SOURCES_GROUP_HINT', text)
        self.assertIn('Refresh clears cached data for an enabled source', SOURCES_GROUP_HINT)

    def test_one_source_row_per_registered_source(self):
        rows = cache_refresh_source_rows()
        registered = tuple(source.key for source in AWARD_SOURCES)
        self.assertEqual(tuple(key for key, _name in rows), registered)
        self.assertEqual(len(rows), len(SOURCE_INFOS))
        self.assertEqual(
            [name for _key, name in rows],
            [info.display_name for info in SOURCE_INFOS],
        )

    def test_each_row_has_checkbox_and_refresh_button(self):
        text = _config_text()
        self.assertIn('self.source_checkboxes[info.key] = checkbox', text)
        self.assertIn('self.source_refresh_buttons[info.key] = refresh_btn', text)
        self.assertIn('QCheckBox(info.display_name', text)
        self.assertIn('CACHE_REFRESH_BUTTON_LABEL', text)
        self.assertEqual(CACHE_REFRESH_BUTTON_LABEL, 'Refresh')
        self.assertIn('row_layout.addWidget(checkbox)', text)
        self.assertIn('row_layout.addStretch(1)', text)
        self.assertIn('row_layout.addWidget(refresh_btn)', text)
        self.assertNotIn('hugo._reset_runtime_state', text)
        self.assertNotIn('nebula._reset_runtime_state', text)

    def test_display_names_match_source_infos(self):
        by_key = dict(cache_refresh_source_rows())
        self.assertEqual(by_key['pulitzer'], 'Pulitzer Prizes')
        self.assertEqual(by_key['nebula'], 'Nebula Awards')
        self.assertEqual(by_key['hugo'], 'Hugo Awards')
        self.assertEqual(by_key['locus'], 'Locus Awards')
        self.assertEqual(by_key['world_fantasy'], 'World Fantasy Awards')
        self.assertEqual(by_key['nobel'], 'NobelPrize.org')
        self.assertEqual(by_key['booker'], 'The Booker Prize')
        self.assertEqual(by_key['german_book_prize'], 'Deutscher Buchpreis')
        self.assertEqual(by_key['prix_goncourt'], 'Prix Goncourt')
        self.assertEqual(by_key['newbery'], 'John Newbery Medal')

    def test_one_refresh_button_per_registered_source(self):
        panel = FakeAwardSourcesPanel()
        self.assertEqual(
            tuple(panel.source_refresh_buttons),
            tuple(source.key for source in AWARD_SOURCES),
        )
        self.assertEqual(
            tuple(panel.source_checkboxes),
            tuple(source.key for source in AWARD_SOURCES),
        )


class RefreshButtonIdentityTests(unittest.TestCase):
    def test_each_button_retains_correct_source_key(self):
        seen = []

        def handler(source_key, display_name):
            seen.append((source_key, display_name))

        callbacks = [
            bind_source_refresh_callback(handler, key, name)
            for key, name in cache_refresh_source_rows()
        ]
        nebula_index = [key for key, _name in cache_refresh_source_rows()].index(
            'nebula'
        )
        callbacks[nebula_index]()
        self.assertEqual(seen, [('nebula', 'Nebula Awards')])

    def test_loop_late_binding_does_not_collapse_keys(self):
        seen = []

        def handler(source_key, display_name):
            seen.append(source_key)

        callbacks = [
            bind_source_refresh_callback(handler, key, name)
            for key, name in cache_refresh_source_rows()
        ]
        for callback in callbacks:
            callback()
        self.assertEqual(
            seen,
            [key for key, _name in cache_refresh_source_rows()],
        )

    def test_reenabled_refresh_invokes_only_its_own_source(self):
        panel = FakeAwardSourcesPanel(disabled_keys=['nebula'])
        self.assertFalse(panel.source_refresh_buttons['nebula'].enabled)
        panel.set_checked('nebula', True)
        self.assertTrue(panel.source_refresh_buttons['nebula'].enabled)
        with patch(
            'awards.cache_control.refresh_award_source_cache',
            return_value=True,
        ) as refresh:
            panel.click_refresh('nebula', confirmed=True)
        refresh.assert_called_once_with('nebula')


class CheckboxRefreshSyncTests(unittest.TestCase):
    def test_initially_enabled_source_has_refresh_enabled(self):
        panel = FakeAwardSourcesPanel(disabled_keys=['locus'])
        self.assertTrue(panel.source_checkboxes['nebula'].checked)
        self.assertTrue(panel.source_refresh_buttons['nebula'].enabled)

    def test_initially_disabled_source_has_refresh_disabled(self):
        panel = FakeAwardSourcesPanel(disabled_keys=['nebula'])
        self.assertFalse(panel.source_checkboxes['nebula'].checked)
        self.assertFalse(panel.source_refresh_buttons['nebula'].enabled)
        self.assertIn('nebula', panel.source_checkboxes)
        self.assertIn('nebula', panel.source_refresh_buttons)

    def test_uncheck_immediately_disables_refresh(self):
        panel = FakeAwardSourcesPanel()
        panel.set_checked('hugo', False)
        self.assertFalse(panel.source_checkboxes['hugo'].checked)
        self.assertFalse(panel.source_refresh_buttons['hugo'].enabled)
        self.assertTrue(panel.source_refresh_buttons['nebula'].enabled)

    def test_check_immediately_enables_refresh(self):
        panel = FakeAwardSourcesPanel(disabled_keys=['hugo'])
        panel.set_checked('hugo', True)
        self.assertTrue(panel.source_checkboxes['hugo'].checked)
        self.assertTrue(panel.source_refresh_buttons['hugo'].enabled)

    def test_select_none_disables_all_refresh_buttons(self):
        panel = FakeAwardSourcesPanel()
        panel.select_no_sources()
        for key, button in panel.source_refresh_buttons.items():
            self.assertFalse(panel.source_checkboxes[key].checked, key)
            self.assertFalse(button.enabled, key)

    def test_select_all_enables_all_refresh_buttons(self):
        panel = FakeAwardSourcesPanel(disabled_keys=['nebula', 'locus'])
        panel.select_all_sources()
        for key, button in panel.source_refresh_buttons.items():
            self.assertTrue(panel.source_checkboxes[key].checked, key)
            self.assertTrue(button.enabled, key)

    def test_config_syncs_refresh_from_checkbox_toggled(self):
        text = _config_text()
        self.assertIn('checkbox.toggled.connect(', text)
        self.assertIn('bind_refresh_enabled_to_checkbox(refresh_btn)', text)

    def test_disabled_refresh_cannot_invoke_cache_refresh(self):
        panel = FakeAwardSourcesPanel(disabled_keys=['nebula'])
        with patch(
            'awards.cache_control.refresh_award_source_cache'
        ) as refresh:
            panel.click_refresh('nebula', confirmed=True)
        refresh.assert_not_called()
        self.assertEqual(panel.status, '')


class ConfirmationAndStatusTests(unittest.TestCase):
    def test_cancel_does_not_call_cache_control(self):
        panel = FakeAwardSourcesPanel()
        with patch(
            'awards.cache_control.refresh_award_source_cache'
        ) as refresh:
            panel.click_refresh('nebula', confirmed=False)
        refresh.assert_not_called()
        self.assertEqual(panel.status, '')
        self.assertIsNone(panel.failure_text)

    def test_confirm_calls_cache_control_once_with_source_key(self):
        panel = FakeAwardSourcesPanel()
        with patch(
            'awards.cache_control.refresh_award_source_cache',
            return_value=True,
        ) as refresh:
            panel.click_refresh('hugo', confirmed=True)
        refresh.assert_called_once_with('hugo')
        self.assertEqual(
            panel.status,
            source_cache_refresh_status_text('Hugo Awards'),
        )
        self.assertIsNone(panel.failure_text)

    def test_status_uses_display_name_and_replaces_previous(self):
        panel = FakeAwardSourcesPanel()
        with patch(
            'awards.cache_control.refresh_award_source_cache',
            return_value=True,
        ):
            panel.click_refresh('nebula', confirmed=True)
            self.assertIn('Nebula Awards cached data cleared.', panel.status)
            panel.click_refresh('locus', confirmed=True)
        self.assertIn('Locus Awards cached data cleared.', panel.status)
        self.assertNotIn('Nebula Awards cached data cleared.', panel.status)

    def test_status_label_is_in_award_sources_group(self):
        text = _config_text()
        sources_block = text.split("QGroupBox('Award sources'")[1].split(
            "QGroupBox('Qualification and award output'"
        )[0]
        self.assertIn('self.cache_status = QLabel', sources_block)
        self.assertIn('sources_layout.addWidget(self.cache_status)', sources_block)

    def test_success_copy_appears_only_on_true_persistent_success(self):
        panel = FakeAwardSourcesPanel()
        with patch(
            'awards.cache_control.refresh_award_source_cache',
            return_value=True,
        ):
            panel.click_refresh('nebula', confirmed=True)
        self.assertEqual(
            panel.status,
            source_cache_refresh_status_text('Nebula Awards'),
        )
        with patch(
            'awards.cache_control.refresh_award_source_cache',
            return_value=False,
        ):
            panel.click_refresh('hugo', confirmed=True)
        self.assertEqual(
            panel.status,
            source_cache_refresh_status_text('Nebula Awards'),
        )
        self.assertEqual(
            panel.failure_text,
            source_cache_refresh_failure_text('Hugo Awards'),
        )
        self.assertNotIn('cached data cleared', panel.failure_text)
        self.assertIn('could not be removed', panel.failure_text)

    def test_confirmation_copy_mentions_books_and_immediate_action(self):
        title = source_cache_refresh_confirm_title('Nebula Awards')
        body = source_cache_refresh_confirm_body('Nebula Awards')
        self.assertEqual(title, 'Refresh cached Nebula Awards data?')
        self.assertIn('No award information already stored in your books', body)
        self.assertIn('not undone by Canceling Preferences', body)
        self.assertIn('in-memory cache', body)
        self.assertIn('may take longer', body)

    def test_config_uses_question_dialog_and_immediate_helper(self):
        text = _config_text()
        self.assertIn('question_dialog(', text)
        self.assertIn('run_source_cache_refresh_if_confirmed(', text)
        self.assertIn('source_cache_refresh_failure_text(', text)
        self.assertIn('error_dialog(', text)
        self.assertIn('skip_dialog_name=None', text)


class ApplyCancelInteractionTests(unittest.TestCase):
    def test_refresh_is_immediate_even_if_checkbox_change_is_canceled(self):
        panel = FakeAwardSourcesPanel(disabled_keys=['locus'])
        self.assertFalse(panel.source_refresh_buttons['locus'].enabled)
        panel.set_checked('locus', True)
        self.assertTrue(panel.source_refresh_buttons['locus'].enabled)
        with patch(
            'awards.cache_control.refresh_award_source_cache',
            return_value=True,
        ) as refresh:
            panel.click_refresh('locus', confirmed=True)
        refresh.assert_called_once_with('locus')
        self.assertIn('Locus Awards cached data cleared.', panel.status)
        body = _save_settings_body()
        self.assertIn("prefs['disabled_source_keys']", body)
        self.assertNotIn('cache_status', body)


class SaveSettingsIsolationTests(unittest.TestCase):
    def test_save_settings_does_not_persist_cache_refresh_state(self):
        body = _save_settings_body()
        self.assertIn("prefs['award_output_template']", body)
        self.assertIn("prefs['disabled_source_keys']", body)
        self.assertIn('self.source_checkboxes[info.key].isChecked()', body)
        self.assertNotIn('cache_status', body)
        self.assertNotIn('cache_refresh', body)
        self.assertNotIn("prefs['cache", body)
        defaults_block = _config_text().split('class ConfigWidget')[0]
        self.assertNotIn("prefs.defaults['cache", defaults_block)

    def test_config_does_not_enable_source_on_refresh(self):
        handler = _config_text().split('def _on_refresh_cached_source')[1]
        handler = handler.split('def validate')[0]
        self.assertNotIn('setChecked(True)', handler)
        self.assertNotIn('disabled_source_keys', handler)


class NoNetworkFromUiActionTests(unittest.TestCase):
    def test_confirmed_refresh_does_not_lookup_or_open_http(self):
        panel = FakeAwardSourcesPanel()
        with (
            patch('awards.engine.lookup_awards') as engine_lookup,
            patch('awards.sources.nebula.lookup') as nebula_lookup,
            patch('awards.sources.hugo.lookup') as hugo_lookup,
            patch('awards.sources.locus.lookup') as locus_lookup,
            patch('urllib.request.urlopen') as urlopen,
            patch(
                'awards.cache_control.refresh_award_source_cache',
                return_value=False,
            ) as refresh,
        ):
            panel.click_refresh('nebula', confirmed=True)
        refresh.assert_called_once_with('nebula')
        engine_lookup.assert_not_called()
        nebula_lookup.assert_not_called()
        hugo_lookup.assert_not_called()
        locus_lookup.assert_not_called()
        urlopen.assert_not_called()
        self.assertEqual(panel.status, '')
        self.assertIsNotNone(panel.failure_text)
