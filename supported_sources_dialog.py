from html import escape

from calibre_plugins.calibre_awards.awards.source_info import (
    SOURCE_INFOS,
    format_identity_scopes,
)
from qt.core import (
    QDialog,
    QDialogButtonBox,
    QFont,
    QFrame,
    QGroupBox,
    QLabel,
    QScrollArea,
    Qt,
    QVBoxLayout,
    QWidget,
)

_INTRO_TEXT = (
    'Calibre Awards currently checks the following award sources. '
    'Supported categories and important source limitations are shown below.'
)


def _set_normal_weight(widget):
    font = QFont(widget.font())
    font.setBold(False)
    widget.setFont(font)


def _plain_label(text, parent):
    label = QLabel(text, parent)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
    )
    _set_normal_weight(label)
    return label


def _field_label(caption, value, parent):
    label = QLabel(
        f'<b>{escape(caption)}</b> {escape(value)}',
        parent,
    )
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
    )
    _set_normal_weight(label)
    return label


def _source_group(info, parent):
    group = QGroupBox(info.display_name, parent)
    title_font = QFont(group.font())
    if not title_font.bold():
        title_font.setBold(True)
        group.setFont(title_font)
    layout = QVBoxLayout(group)

    layout.addWidget(
        _field_label('Categories:', ', '.join(info.categories), group)
    )
    layout.addWidget(
        _field_label(
            'Scope:',
            format_identity_scopes(info.identity_scopes),
            group,
        )
    )
    layout.addWidget(_plain_label(info.description.strip(), group))
    if info.limitation is not None:
        layout.addWidget(
            _field_label('Note:', info.limitation.strip(), group)
        )

    url = info.homepage_url
    link = QLabel(
        f'<a href="{escape(url, quote=True)}">Official site</a>',
        group,
    )
    link.setTextFormat(Qt.TextFormat.RichText)
    link.setOpenExternalLinks(True)
    link.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextBrowserInteraction
    )
    link.setToolTip(url)
    _set_normal_weight(link)
    layout.addWidget(link)
    return group


class SupportedSourcesDialog(QDialog):
    """Static help listing currently supported award sources."""

    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle('Supported Award Sources')
        self.setSizeGripEnabled(True)

        layout = QVBoxLayout()
        self.setLayout(layout)

        intro = _plain_label(_INTRO_TEXT, self)
        layout.addWidget(intro)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(scroll)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)

        for info in SOURCE_INFOS:
            body_layout.addWidget(_source_group(info, body))

        body_layout.addStretch(1)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close,
            self,
        )
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.resize(760, 580)
