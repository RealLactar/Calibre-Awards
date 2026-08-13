from calibre.utils.config import JSONConfig
from calibre_plugins.calibre_awards.awards.formatter import (
    DEFAULT_AWARD_OUTPUT_TEMPLATE,
)
from qt.core import QLabel, QLineEdit, Qt, QVBoxLayout, QWidget

# Stored under Calibre's config directory as plugins/calibre_awards.json.
prefs = JSONConfig('plugins/calibre_awards')
prefs.defaults['award_output_template'] = DEFAULT_AWARD_OUTPUT_TEMPLATE


def _award_output_template_from_value(value) -> str:
    text = '' if value is None else str(value).strip()
    return text or DEFAULT_AWARD_OUTPUT_TEMPLATE


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

    def save_settings(self):
        template = _award_output_template_from_value(self.template_edit.text())
        self.template_edit.setText(template)
        prefs['award_output_template'] = template
