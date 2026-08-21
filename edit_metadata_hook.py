# Isolated runtime hook for Calibre's undocumented single-book Edit Metadata UI.
# Do not call Calibre DB APIs from this module. Award write-back may update
# Edit Metadata custom-column widgets via setter() only after the user accepts
# the award-selection dialog.

from functools import wraps
import time

from calibre.ebooks.metadata import authors_to_string
from calibre.gui2 import error_dialog, info_dialog
from calibre.gui2.metadata.single import MetadataSingleDialogBase
from calibre_plugins.calibre_awards.award_selection_dialog import (
    AwardSelectionDialog,
)
from calibre_plugins.calibre_awards.awards.engine import lookup_awards
from calibre_plugins.calibre_awards.awards.formatter import (
    DEFAULT_AWARD_OUTPUT_TEMPLATE,
    format_award_result,
)
from calibre_plugins.calibre_awards.awards.writeback import (
    prepare_append_award_values,
    prepare_replace_award_values,
)
from calibre_plugins.calibre_awards.config import prefs
from qt.core import (
    QDialog,
    QFont,
    QLabel,
    QObject,
    QProgressBar,
    QPushButton,
    Qt,
    QThread,
    QTimer,
    QVBoxLayout,
    pyqtSignal,
)

BUTTON_OBJECT_NAME = 'calibre_awards_check_awards_button'
_PATCH_ATTR = '_calibre_awards_setupui_patch'
_RUNNING_ATTR = '_calibre_awards_lookup_running'
_LATER_SEARCH_PROGRESS_DELAY_MS = 500

# Keep strong references to active workers so closing Edit Metadata cannot
# garbage-collect a still-running QThread.
_ACTIVE_THREADS = set()
_THREAD_CLEANUP_RECEIVER = None
_FIRST_SEARCH_STARTED = False


class _AwardLookupThread(QThread):
    """Run awards.engine.lookup_awards() off the GUI thread."""

    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)

    def __init__(self, title, author, series=''):
        # Intentionally unparented: must outlive the Edit Metadata dialog.
        super().__init__(None)
        self._title = title
        self._author = author
        self._series = series

    def run(self):
        try:
            report = lookup_awards(
                self._title,
                self._author,
                series=self._series,
                on_progress=self._emit_progress,
            )
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')
            return
        self.succeeded.emit(report)

    def _emit_progress(self, update):
        name = update.source_name or ''
        self.progress.emit(
            update.completed_sources,
            update.total_sources,
            name,
        )


class _LookupProgressDialog(QDialog):
    """Determinate lookup progress owned by the open Edit Metadata dialog."""

    def __init__(self, parent, show_first_search_warning):
        super().__init__(parent)
        self.setWindowTitle('Calibre Awards')
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self._lookup_running = True
        self._started = time.monotonic()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        if show_first_search_warning:
            heading = QLabel('FIRST AWARD SEARCH THIS SESSION', self)
            heading_font = QFont(heading.font())
            heading_font.setBold(True)
            heading.setFont(heading_font)
            heading.setStyleSheet('color: #cc0000; font-weight: bold;')
            heading.setWordWrap(True)
            layout.addWidget(heading)

            intro = QLabel(
                'Award data must be loaded from several websites.', self
            )
            intro.setWordWrap(True)
            layout.addWidget(intro)

            warning = QLabel(
                'This first search may take 10-20 seconds, and longer if an '
                'award website is responding slowly.',
                self,
            )
            warning_font = QFont(warning.font())
            warning_font.setBold(True)
            warning.setFont(warning_font)
            warning.setStyleSheet('color: #cc0000; font-weight: bold;')
            warning.setWordWrap(True)
            layout.addWidget(warning)

            later = QLabel(
                'Progress is shown below. Later searches this session '
                'should be much faster.',
                self,
            )
            later.setWordWrap(True)
            layout.addWidget(later)

        self._status = QLabel('0 of 0 award sources complete', self)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._last_completed = QLabel('', self)
        self._last_completed.setWordWrap(True)
        layout.addWidget(self._last_completed)

        self._bar = QProgressBar(self)
        self._bar.setMinimum(0)
        self._bar.setMaximum(1)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        layout.addWidget(self._bar)

        self._elapsed = QLabel('Elapsed: 0.0 seconds', self)
        layout.addWidget(self._elapsed)

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick_elapsed)
        self._timer.start()

        self._show_timer = QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.timeout.connect(self._show_if_running)

    def schedule_show(self, delay_ms):
        if delay_ms <= 0:
            self.show()
            return
        self._show_timer.start(delay_ms)

    def _show_if_running(self):
        if self._lookup_running:
            self.show()

    def _tick_elapsed(self):
        elapsed = time.monotonic() - self._started
        self._elapsed.setText(f'Elapsed: {elapsed:.1f} seconds')

    def handle_progress(self, completed, total, source_name):
        if not self._lookup_running:
            return
        try:
            maximum = total if total > 0 else 1
            self._bar.setMaximum(maximum)
            self._bar.setValue(completed)
            self._status.setText(
                f'{completed} of {total} award sources complete'
            )
            if source_name:
                self._last_completed.setText(
                    f'Last completed: {source_name}'
                )
        except RuntimeError:
            pass

    def mark_finished(self):
        self._lookup_running = False
        self._timer.stop()
        self._show_timer.stop()
        self.hide()
        self.close()

    def closeEvent(self, event):
        if self._lookup_running:
            event.ignore()
            return
        event.accept()


class _LookupUiReceiver(QObject):
    """GUI-thread receiver for lookup results; parented to the Edit Metadata dialog."""

    def __init__(
        self,
        button,
        lookup_title,
        lookup_author,
        lookup_series='',
        parent=None,
        progress_dialog=None,
    ):
        super().__init__(parent)
        self._button = button
        self._lookup_title = lookup_title
        self._lookup_author = lookup_author
        self._lookup_series = lookup_series
        self._progress = progress_dialog

    def _close_progress(self):
        progress = self._progress
        if progress is None:
            return
        try:
            progress.mark_finished()
        except RuntimeError:
            pass

    def handle_succeeded(self, report):
        self._close_progress()
        dialog = self.parent()
        if dialog is None:
            return
        try:
            template = _award_output_template()
            write_enabled = (
                _writeback_can_write(dialog) and bool(report.assessments)
            )
            status_text = _writeback_status_text(
                dialog, can_write=write_enabled
            )
            selection = AwardSelectionDialog(
                dialog,
                report,
                template,
                status_text,
                self._lookup_title,
                self._lookup_author,
                write_enabled=write_enabled,
                lookup_series=self._lookup_series,
            )
            if selection.exec() != QDialog.DialogCode.Accepted:
                return
            try:
                writeback_status = _apply_selected_award_writeback(
                    dialog,
                    selection.selected_assessments(),
                    template,
                )
            except RuntimeError:
                raise
            except Exception as exc:
                writeback_status = (
                    f'Write-back failed: {type(exc).__name__}: {exc}'
                )
            if writeback_status:
                info_dialog(
                    dialog,
                    'Calibre Awards',
                    writeback_status,
                    show=True,
                )
        except RuntimeError:
            # Dialog was destroyed after the signal was queued.
            pass

    def handle_failed(self, message):
        self._close_progress()
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


def _award_output_template():
    stored = prefs['award_output_template']
    text = '' if stored is None else str(stored).strip()
    return text or DEFAULT_AWARD_OUTPUT_TEMPLATE


def _writeback_enabled():
    return bool(prefs['writeback_enabled'])


def _writeback_field():
    stored = prefs['writeback_field']
    return '' if stored is None else str(stored).strip()


def _writeback_mode():
    stored = prefs['writeback_mode']
    text = '' if stored is None else str(stored).strip().casefold()
    if text == 'replace':
        return 'replace'
    return 'append'


def _widget_lookup_name(widget):
    try:
        field_name = getattr(widget, 'field_name', None)
        if field_name:
            return str(field_name)
    except Exception:
        pass
    meta = getattr(widget, 'col_metadata', None) or {}
    label = meta.get('label')
    if label:
        return f'#{label}'
    key = getattr(widget, 'key', None)
    if key:
        return str(key)
    return ''


def _find_custom_widget(dialog, lookup_name):
    if not lookup_name:
        return None
    for widget in getattr(dialog, 'custom_metadata_widgets', None) or ():
        if _widget_lookup_name(widget) == lookup_name:
            return widget
    return None


def _widget_is_eligible_writeback_target(widget, lookup_name):
    if widget is None or _widget_lookup_name(widget) != lookup_name:
        return False
    if not callable(getattr(widget, 'getter', None)):
        return False
    if not callable(getattr(widget, 'setter', None)):
        return False
    meta = getattr(widget, 'col_metadata', None) or {}
    if meta.get('datatype') != 'text':
        return False
    if not meta.get('is_multiple'):
        return False
    display = meta.get('display') or {}
    if display.get('is_names', False):
        return False
    return True


def _existing_widget_values(widget):
    current = widget.getter()
    if not current:
        return []
    return [str(value) for value in current]


def _writeback_destination_widget(dialog):
    lookup_name = _writeback_field()
    widget = _find_custom_widget(dialog, lookup_name)
    if widget is None or not _widget_is_eligible_writeback_target(
        widget, lookup_name
    ):
        return lookup_name, None
    return lookup_name, widget


def _writeback_can_write(dialog):
    if not _writeback_enabled():
        return False
    _lookup_name, widget = _writeback_destination_widget(dialog)
    return widget is not None


def _writeback_status_text(dialog, can_write=False):
    if can_write:
        lookup_name, _widget = _writeback_destination_widget(dialog)
        if _writeback_mode() == 'replace':
            return (
                'Replace mode: Write Selected will replace the existing '
                f'values in {lookup_name} with the selected awards. '
                'Cancel makes no change.'
            )
        return (
            f'Write Selected will append selected awards to {lookup_name}. '
            'Cancel makes no change.'
        )
    if not _writeback_enabled():
        return (
            'Metadata write-back is disabled. Close dismisses this dialog '
            'without changing metadata.'
        )
    lookup_name, widget = _writeback_destination_widget(dialog)
    if not lookup_name:
        return (
            'Write-back unavailable: no destination column is configured. '
            'Close dismisses this dialog without changing metadata.'
        )
    if widget is None:
        return (
            'Write-back unavailable: configured column '
            f'{lookup_name} is not available. Close dismisses this dialog '
            'without changing metadata.'
        )
    return (
        'No matching award records were found. Close dismisses this dialog '
        'without changing metadata.'
    )


def _comma_rejection_lines(rejected):
    lines = []
    for value in rejected:
        lines.append(
            'Selected value not written because it contains a comma: '
            f'{value}'
        )
    return lines


def _apply_selected_award_writeback(dialog, selected_assessments, template):
    if not _writeback_enabled():
        return ''

    lookup_name, widget = _writeback_destination_widget(dialog)
    if widget is None:
        name = lookup_name or '(none)'
        return (
            'Write-back unavailable: configured column '
            f'{name} is not available.'
        )

    if not selected_assessments:
        return 'No new award values were added.'

    new_values = [
        format_award_result(item.result, template)
        for item in selected_assessments
    ]
    existing = _existing_widget_values(widget)
    mode = _writeback_mode()
    if mode == 'replace':
        prepared = prepare_replace_award_values(new_values)
        if not prepared.values:
            lines = ['Existing field values were left unchanged.']
            lines.extend(_comma_rejection_lines(prepared.rejected_for_comma))
            return '\n'.join(lines)
    else:
        prepared = prepare_append_award_values(existing, new_values)

    if prepared.values != existing:
        widget.setter(prepared.values)
        if mode == 'replace':
            count = len(prepared.values)
            status = (
                f'Awards field replaced with {count} selected value'
                f'{"s" if count != 1 else ""}.'
            )
        else:
            added = len(prepared.values) - len(existing)
            status = f'{added} award value'
            status += 's appended.' if added != 1 else ' appended.'
    else:
        status = 'No new award values were added.'

    lines = [status]
    lines.extend(_comma_rejection_lines(prepared.rejected_for_comma))
    return '\n'.join(lines)


def _start_award_lookup(dialog, button):
    global _FIRST_SEARCH_STARTED
    if getattr(dialog, _RUNNING_ATTR, False):
        return

    title = dialog.title.current_val
    author = authors_to_string(dialog.authors.current_val)
    series = dialog.series.current_val
    lookup_title = ('' if title is None else str(title)).strip()
    lookup_author = ('' if author is None else str(author)).strip()
    lookup_series = ('' if series is None else str(series)).strip()

    is_first_search = not _FIRST_SEARCH_STARTED
    _FIRST_SEARCH_STARTED = True

    setattr(dialog, _RUNNING_ATTR, True)
    button.setEnabled(False)

    progress = _LookupProgressDialog(dialog, is_first_search)
    if is_first_search:
        progress.schedule_show(0)
    else:
        progress.schedule_show(_LATER_SEARCH_PROGRESS_DELAY_MS)

    thread = _AwardLookupThread(lookup_title, lookup_author, lookup_series)
    receiver = _LookupUiReceiver(
        button,
        lookup_title,
        lookup_author,
        lookup_series,
        dialog,
        progress_dialog=progress,
    )
    cleanup = _thread_cleanup_receiver()

    thread.progress.connect(progress.handle_progress)
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
