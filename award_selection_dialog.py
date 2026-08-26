from calibre_plugins.calibre_awards.awards.formatter import format_award_result
from calibre_plugins.calibre_awards.awards.presentation import (
    default_award_row_checked,
    format_book_line,
    format_possible_author_match_warning,
    format_series_line,
    lookup_has_series_award,
    match_row_scope_lines,
)
from calibre_plugins.calibre_awards.awards.qualifier import QualificationDecision
from qt.core import (
    QCheckBox,
    QColor,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QPalette,
    QScrollArea,
    Qt,
    QVBoxLayout,
    QWidget,
)


class AwardSelectionDialog(QDialog):
    """Review matched assessments; write-back happens only after accept.

    Qualification supplies the default checkbox state. The user still chooses
    which rows to write. This dialog does not rewrite qualification decisions.
    """

    def __init__(
        self,
        parent,
        report,
        template,
        status_text,
        lookup_title,
        lookup_author,
        write_enabled=False,
        lookup_series='',
    ):
        QDialog.__init__(self, parent)
        self.setWindowTitle('Calibre Awards')
        self._lookup_title = lookup_title
        self._lookup_author = lookup_author
        self._lookup_series = lookup_series or ''
        self._rows = []

        layout = QVBoxLayout()
        self.setLayout(layout)

        book = QLabel(
            format_book_line(lookup_title, lookup_author),
            self,
        )
        book.setWordWrap(True)
        book.setTextFormat(Qt.PlainText)
        layout.addWidget(book)

        series_text = format_series_line(self._lookup_series)
        if series_text is not None and lookup_has_series_award(
            self._lookup_series, report.assessments
        ):
            series = QLabel(series_text, self)
            series.setWordWrap(True)
            series.setTextFormat(Qt.PlainText)
            layout.addWidget(series)

        if report.assessments:
            status_message = status_text
        else:
            status_message = (
                'No matching award records were found. Nothing will be changed.'
            )
        status = QLabel(status_message, self)
        status.setWordWrap(True)
        status.setTextFormat(Qt.PlainText)
        layout.addWidget(status)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(scroll)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)

        can_write = bool(write_enabled and report.assessments)

        if report.assessments:
            intro = QLabel('Matched award records:', self)
            intro.setTextFormat(Qt.PlainText)
            body_layout.addWidget(intro)
            for assessment in report.assessments:
                row = _AwardMatchRow(
                    assessment,
                    template,
                    lookup_title,
                    lookup_author,
                    body,
                    selectable=can_write,
                    lookup_series=self._lookup_series,
                )
                self._rows.append(row)
                body_layout.addWidget(row)

        if report.failures:
            failure_lines = ['Source problems:']
            for failure in report.failures:
                failure_lines.append(
                    f'{failure.source_name} — {failure.error_type} — '
                    f'{failure.message}'
                )
            failures = QLabel('\n'.join(failure_lines), body)
            failures.setWordWrap(True)
            failures.setTextFormat(Qt.PlainText)
            body_layout.addWidget(failures)

        body_layout.addStretch(1)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        if can_write:
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok
                | QDialogButtonBox.StandardButton.Cancel,
                self,
            )
            ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
            if ok_button is not None:
                ok_button.setText('Write Selected')
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
        else:
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Close,
                self,
            )
            buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.resize(560, 420)

    def selected_assessments(self):
        return [row.assessment for row in self._rows if row.is_checked()]


class _AwardMatchRow(QWidget):
    def __init__(
        self,
        assessment,
        template,
        lookup_title,
        lookup_author,
        parent=None,
        selectable=True,
        lookup_series='',
    ):
        QWidget.__init__(self, parent)
        # Keep the engine's qualification decision; the checkbox is only UI.
        self.assessment = assessment
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 8)
        self.setLayout(layout)

        result = assessment.result
        formatted = format_award_result(result, template)
        self.checkbox = QCheckBox(formatted, self)
        # QUALIFIES is the default checked recommendation unless identity
        # confirmation is required. When write-back selection is enabled,
        # REVIEW / DOES_NOT_QUALIFY rows are not forbidden; disabled
        # write-back disables the checkboxes.
        confirmation_required = (
            getattr(result, 'identity_confirmation_required', False) is True
        )
        self.checkbox.setChecked(
            default_award_row_checked(
                qualifies=(
                    assessment.qualification.decision
                    is QualificationDecision.QUALIFIES
                ),
                identity_confirmation_required=confirmation_required,
            )
        )
        self.checkbox.setEnabled(selectable)
        tooltip = f'Source: {result.source_name}'
        if result.source_url:
            tooltip += f'\n{result.source_url}'
        self.checkbox.setToolTip(tooltip)
        layout.addWidget(self.checkbox)

        warning = format_possible_author_match_warning(result, lookup_author)
        if confirmation_required:
            _apply_possible_author_match_style(self)
        if warning is not None:
            warn = QLabel(warning, self)
            warn.setWordWrap(True)
            warn.setTextFormat(Qt.PlainText)
            _apply_possible_author_match_style(warn)
            layout.addWidget(warn)

        for line in match_row_scope_lines(
            result,
            lookup_title,
            lookup_author,
            lookup_series,
        ):
            if warning is not None and line == warning:
                continue
            # Presentation helpers mark author- and series-level awards.
            scope = QLabel(line, self)
            scope.setWordWrap(True)
            scope.setTextFormat(Qt.PlainText)
            layout.addWidget(scope)

        decision_name = assessment.qualification.decision.name
        reason = (assessment.qualification.reason or '').strip()
        qualification_text = (
            f'{decision_name} - {reason}' if reason else decision_name
        )
        qualification = QLabel(qualification_text, self)
        qualification.setWordWrap(True)
        qualification.setTextFormat(Qt.PlainText)
        layout.addWidget(qualification)

    def is_checked(self):
        return self.checkbox.isChecked()


def _apply_possible_author_match_style(widget):
    """Amber treatment that stays readable on light and dark palettes."""
    window = widget.palette().color(QPalette.ColorRole.Window)
    if window.lightness() >= 128:
        foreground = QColor(122, 62, 0)
        background = QColor(255, 232, 186)
    else:
        foreground = QColor(255, 196, 110)
        background = QColor(74, 48, 12)
    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.WindowText, foreground)
    palette.setColor(QPalette.ColorRole.Window, background)
    palette.setColor(QPalette.ColorRole.Text, foreground)
    palette.setColor(QPalette.ColorRole.Base, background)
    widget.setAutoFillBackground(True)
    widget.setPalette(palette)
