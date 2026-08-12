# Isolated runtime hook for Calibre's undocumented single-book Edit Metadata UI.
# Do not call Calibre DB APIs or write metadata from this module.

from functools import wraps

from calibre.ebooks.metadata import authors_to_string
from calibre.gui2 import error_dialog, info_dialog
from calibre.gui2.metadata.single import MetadataSingleDialogBase
from calibre_plugins.calibre_awards.awards.engine import lookup_awards
from qt.core import QObject, QPushButton, QThread, pyqtSignal

BUTTON_OBJECT_NAME = 'calibre_awards_check_awards_button'
_PATCH_ATTR = '_calibre_awards_setupui_patch'
_RUNNING_ATTR = '_calibre_awards_lookup_running'

# Keep strong references to active workers so closing Edit Metadata cannot
# garbage-collect a still-running QThread.
_ACTIVE_THREADS = set()
_THREAD_CLEANUP_RECEIVER = None


def _format_year_category(result):
    year_text = '' if result.award_year is None else str(result.award_year)
    category_text = result.category or ''
    if year_text and category_text:
        return f'{year_text} — {category_text}'
    return year_text or category_text


def _format_assessment(assessment):
    result = assessment.result
    lines = [
        f'{result.work_title} — {result.work_author}',
        '',
        result.award_name,
    ]
    year_category = _format_year_category(result)
    if year_category:
        lines.append(year_category)
    lines.extend([
        result.status,
        assessment.qualification.decision.name,
        '',
        f'Source: {result.source_name}',
    ])
    if result.source_url:
        lines.append(f'URL: {result.source_url}')
    return '\n'.join(lines)


def _format_lookup_report(report):
    """Temporary plain-text report; replaceable by a configurable template later."""
    if not report.assessments and not report.failures:
        return 'No award results found.'

    sections = [_format_assessment(item) for item in report.assessments]
    body = '\n\n'.join(sections)

    if report.failures:
        failure_lines = ['Source problems:', '']
        for failure in report.failures:
            failure_lines.append(
                f'{failure.source_name} — {failure.error_type} — {failure.message}'
            )
        failure_block = '\n'.join(failure_lines).strip()
        if body:
            return f'{body}\n\n{failure_block}'
        return failure_block

    return body


class _AwardLookupThread(QThread):
    """Run awards.engine.lookup_awards() off the GUI thread."""

    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, title, author):
        # Intentionally unparented: must outlive the Edit Metadata dialog.
        super().__init__(None)
        self._title = title
        self._author = author

    def run(self):
        try:
            report = lookup_awards(self._title, self._author)
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')
            return
        self.succeeded.emit(report)


class _LookupUiReceiver(QObject):
    """GUI-thread receiver for lookup results; parented to the Edit Metadata dialog."""

    def __init__(self, button, parent=None):
        super().__init__(parent)
        self._button = button

    def handle_succeeded(self, report):
        dialog = self.parent()
        if dialog is None:
            return
        try:
            info_dialog(
                dialog,
                'Calibre Awards',
                _format_lookup_report(report),
                show=True,
            )
        except RuntimeError:
            # Dialog was destroyed after the signal was queued.
            pass

    def handle_failed(self, message):
        dialog = self.parent()
        if dialog is None:
            return
        try:
            error_dialog(
                dialog,
                'Calibre Awards',
                message,
                show=True,
            )
        except RuntimeError:
            # Dialog was destroyed after the signal was queued.
            pass

    def handle_finished(self):
        dialog = self.parent()
        if dialog is None:
            return
        try:
            setattr(dialog, _RUNNING_ATTR, False)
            self._button.setEnabled(True)
        except RuntimeError:
            # Dialog/button were destroyed after the signal was queued.
            pass


class _ThreadCleanupReceiver(QObject):
    """Persistent GUI-thread receiver for worker lifetime cleanup."""

    def handle_finished(self):
        thread = self.sender()
        if thread is None:
            return
        _ACTIVE_THREADS.discard(thread)
        thread.deleteLater()


def _thread_cleanup_receiver():
    global _THREAD_CLEANUP_RECEIVER
    if _THREAD_CLEANUP_RECEIVER is None:
        # Created on the GUI thread during a Check Awards click.
        _THREAD_CLEANUP_RECEIVER = _ThreadCleanupReceiver()
    return _THREAD_CLEANUP_RECEIVER


def _start_award_lookup(dialog, button):
    if getattr(dialog, _RUNNING_ATTR, False):
        return

    title = dialog.title.current_val
    author = authors_to_string(dialog.authors.current_val)

    setattr(dialog, _RUNNING_ATTR, True)
    button.setEnabled(False)

    thread = _AwardLookupThread(title, author)
    receiver = _LookupUiReceiver(button, dialog)
    cleanup = _thread_cleanup_receiver()

    thread.succeeded.connect(receiver.handle_succeeded)
    thread.failed.connect(receiver.handle_failed)
    thread.finished.connect(receiver.handle_finished)
    thread.finished.connect(cleanup.handle_finished)

    _ACTIVE_THREADS.add(thread)
    thread.start()


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
    button.clicked.connect(lambda: _start_award_lookup(dialog, button))
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
