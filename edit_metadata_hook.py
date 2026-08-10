# Isolated runtime hook for Calibre's undocumented single-book Edit Metadata UI.
# Do not call Calibre DB APIs or write metadata from this module.

from functools import wraps

from calibre.ebooks.metadata import authors_to_string
from calibre.gui2 import info_dialog
from calibre.gui2.metadata.single import MetadataSingleDialogBase
from qt.core import QPushButton

BUTTON_OBJECT_NAME = 'calibre_awards_check_awards_button'
_PATCH_ATTR = '_calibre_awards_setupui_patch'


def _show_displayed_title_author(dialog):
    title = dialog.title.current_val
    authors = authors_to_string(dialog.authors.current_val)
    info_dialog(
        dialog,
        'Calibre Awards',
        f'Title: {title}\nAuthor: {authors}',
        show=True,
    )


def _inject_check_awards_button(dialog):
    # Undocumented internals: button_box_layout / button_box on MetadataSingleDialogBase.
    if dialog.findChild(QPushButton, BUTTON_OBJECT_NAME) is not None:
        return

    layout = getattr(dialog, 'button_box_layout', None)
    button_box = getattr(dialog, 'button_box', None)
    if layout is None or button_box is None:
        return

    index = layout.indexOf(button_box)
    if index < 0:
        # Fail safely: do not break Edit Metadata if the button box moved.
        return

    button = QPushButton('Check Awards', dialog)
    button.setObjectName(BUTTON_OBJECT_NAME)
    button.clicked.connect(lambda: _show_displayed_title_author(dialog))
    layout.insertWidget(index, button)


def install_edit_metadata_hook():
    """Wrap MetadataSingleDialogBase.setupUi once; safe to call repeatedly."""
    original = MetadataSingleDialogBase.setupUi
    if getattr(original, _PATCH_ATTR, False):
        return

    @wraps(original)
    def patched_setupUi(self, *args, **kwargs):
        original(self, *args, **kwargs)
        _inject_check_awards_button(self)

    setattr(patched_setupUi, _PATCH_ATTR, True)
    MetadataSingleDialogBase.setupUi = patched_setupUi
