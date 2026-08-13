from calibre.gui2 import error_dialog
from calibre.gui2.ui import get_gui
from calibre.utils.config import JSONConfig
from calibre_plugins.calibre_awards.awards.formatter import (
    DEFAULT_AWARD_OUTPUT_TEMPLATE,
)
from qt.core import (
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QRadioButton,
    Qt,
    QVBoxLayout,
    QWidget,
)

WRITEBACK_MODE_APPEND = 'append'
WRITEBACK_MODE_REPLACE = 'replace'
_UNAVAILABLE_ITEM_ROLE = Qt.ItemDataRole.UserRole + 1

# Stored under Calibre's config directory as plugins/calibre_awards.json.
prefs = JSONConfig('plugins/calibre_awards')
prefs.defaults['award_output_template'] = DEFAULT_AWARD_OUTPUT_TEMPLATE
prefs.defaults['writeback_enabled'] = False
prefs.defaults['writeback_field'] = ''
prefs.defaults['writeback_mode'] = WRITEBACK_MODE_APPEND


def _award_output_template_from_value(value) -> str:
    text = '' if value is None else str(value).strip()
    return text or DEFAULT_AWARD_OUTPUT_TEMPLATE


def _writeback_enabled_from_value(value) -> bool:
    return bool(value)


def _writeback_field_from_value(value) -> str:
    return '' if value is None else str(value).strip()


def _writeback_mode_from_value(value) -> str:
    text = '' if value is None else str(value).strip().casefold()
    if text == WRITEBACK_MODE_REPLACE:
        return WRITEBACK_MODE_REPLACE
    return WRITEBACK_MODE_APPEND


def _is_eligible_writeback_column(meta) -> bool:
    if not meta or meta.get('datatype') != 'text':
        return False
    if not meta.get('is_multiple'):
        return False
    display = meta.get('display') or {}
    if display.get('is_names', False):
        return False
    return True


def _library_field_metadata():
    gui = get_gui()
    if gui is None:
        return None
    db = getattr(gui, 'current_db', None)
    if db is None:
        return None
    return db.field_metadata


def _eligible_writeback_fields(field_metadata) -> list[tuple[str, str]]:
    if field_metadata is None:
        return []
    custom = field_metadata.custom_field_metadata(include_composites=False)
    items = []
    for lookup_name, meta in custom.items():
        if not _is_eligible_writeback_column(meta):
            continue
        display_name = meta.get('name') or lookup_name
        items.append((lookup_name, display_name))
    items.sort(key=lambda item: str(item[1]).casefold())
    return items


class ConfigWidget(QWidget):
    def __init__(self):
        QWidget.__init__(self)
        layout = QVBoxLayout()
        self.setLayout(layout)

        intro = QLabel(
            'This setting controls the format of each award result.'
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.template_label = QLabel('Award output &template:')
        self.template_edit = QLineEdit(self)
        self.template_label.setBuddy(self.template_edit)
        self.template_edit.setText(
            _award_output_template_from_value(prefs['award_output_template'])
        )
        self.template_edit.setPlaceholderText(DEFAULT_AWARD_OUTPUT_TEMPLATE)
        layout.addWidget(self.template_label)
        layout.addWidget(self.template_edit)

        placeholders = QLabel(
            'Supported placeholders:\n'
            '<placement>\n'
            '<year>\n'
            '<award>\n'
            '<category>'
        )
        placeholders.setTextFormat(Qt.PlainText)
        placeholders.setWordWrap(True)
        layout.addWidget(placeholders)

        default_label = QLabel(
            f'Default format: {DEFAULT_AWARD_OUTPUT_TEMPLATE}'
        )
        default_label.setTextFormat(Qt.PlainText)
        default_label.setWordWrap(True)
        layout.addWidget(default_label)

        self.enabled_checkbox = QCheckBox(
            'Write qualifying awards to a custom column',
            self,
        )
        self.enabled_checkbox.setChecked(
            _writeback_enabled_from_value(prefs['writeback_enabled'])
        )
        layout.addWidget(self.enabled_checkbox)

        self.field_label = QLabel('Destination custom &column:')
        self.field_combo = QComboBox(self)
        self.field_label.setBuddy(self.field_combo)
        layout.addWidget(self.field_label)
        layout.addWidget(self.field_combo)

        self.field_status = QLabel('')
        self.field_status.setWordWrap(True)
        self.field_status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.field_status)

        self.append_radio = QRadioButton(
            'Append to existing values (recommended)',
            self,
        )
        self.replace_radio = QRadioButton(
            'Replace existing values',
            self,
        )
        if _writeback_mode_from_value(prefs['writeback_mode']) == (
            WRITEBACK_MODE_REPLACE
        ):
            self.replace_radio.setChecked(True)
        else:
            self.append_radio.setChecked(True)
        layout.addWidget(self.append_radio)
        layout.addWidget(self.replace_radio)

        self._populate_field_combo()
        self.field_combo.currentIndexChanged.connect(self._update_field_status)
        self.enabled_checkbox.toggled.connect(self._update_writeback_enabled_state)
        self._update_writeback_enabled_state()

    def _populate_field_combo(self):
        stored_field = _writeback_field_from_value(prefs['writeback_field'])
        eligible = _eligible_writeback_fields(_library_field_metadata())
        eligible_keys = {lookup_name for lookup_name, _name in eligible}
        self._has_eligible_fields = bool(eligible)

        self.field_combo.clear()
        self.field_combo.addItem('Select a custom column', '')

        for lookup_name, display_name in eligible:
            self.field_combo.addItem(
                f'{display_name} ({lookup_name})',
                lookup_name,
            )

        if stored_field and stored_field not in eligible_keys:
            self.field_combo.insertItem(
                1,
                f'{stored_field} (unavailable in this library)',
                stored_field,
            )
            self.field_combo.setItemData(1, True, _UNAVAILABLE_ITEM_ROLE)
            self.field_combo.setCurrentIndex(1)
        elif stored_field:
            index = self.field_combo.findData(stored_field)
            self.field_combo.setCurrentIndex(index if index >= 0 else 0)
        else:
            self.field_combo.setCurrentIndex(0)
        self._update_field_status()

    def _update_field_status(self):
        if self.field_combo.currentData(_UNAVAILABLE_ITEM_ROLE):
            self.field_status.setText(
                'The previously configured destination column is not available '
                'in this library, or is not an eligible multiple-value text '
                'column. Write-back will not be saved as enabled until you '
                'select a valid column. The stored lookup name was not '
                'replaced with a different field.'
            )
            return
        if not getattr(self, '_has_eligible_fields', False):
            self.field_status.setText(
                'This library has no eligible custom columns. '
                'Write-back requires a text column that allows multiple '
                'values, and is not a names column.'
            )
            return
        self.field_status.setText('')

    def _selected_lookup_name(self) -> str:
        data = self.field_combo.currentData()
        return _writeback_field_from_value(data)

    def _selected_field_is_eligible(self) -> bool:
        lookup_name = self._selected_lookup_name()
        if not lookup_name:
            return False
        if self.field_combo.currentData(_UNAVAILABLE_ITEM_ROLE):
            return False
        eligible_keys = {
            key for key, _name in _eligible_writeback_fields(_library_field_metadata())
        }
        return lookup_name in eligible_keys

    def _update_writeback_enabled_state(self):
        enabled = self.enabled_checkbox.isChecked()
        self.field_label.setEnabled(enabled)
        self.field_combo.setEnabled(enabled)
        self.append_radio.setEnabled(enabled)
        self.replace_radio.setEnabled(enabled)

    def _selected_mode(self) -> str:
        if self.replace_radio.isChecked():
            return WRITEBACK_MODE_REPLACE
        return WRITEBACK_MODE_APPEND

    def validate(self):
        if (
            self.enabled_checkbox.isChecked()
            and not self._selected_field_is_eligible()
        ):
            error_dialog(
                self,
                'Calibre Awards',
                'Write-back is enabled, but no eligible custom column is '
                'selected. Choose a multiple-value text column, or turn '
                'write-back off.',
                show=True,
            )
            return False
        return True

    def save_settings(self):
        template = _award_output_template_from_value(self.template_edit.text())
        self.template_edit.setText(template)
        prefs['award_output_template'] = template

        lookup_name = self._selected_lookup_name()
        eligible = self._selected_field_is_eligible()
        enabled = self.enabled_checkbox.isChecked() and eligible
        self.enabled_checkbox.setChecked(enabled)

        prefs['writeback_enabled'] = enabled
        prefs['writeback_field'] = lookup_name
        prefs['writeback_mode'] = self._selected_mode()
