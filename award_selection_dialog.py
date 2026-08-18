from calibre_plugins.calibre_awards.awards.formatter import format_award_result
from calibre_plugins.calibre_awards.awards.presentation import (
    format_work_identity,
    source_identity_if_different,
)
from calibre_plugins.calibre_awards.awards.qualifier import QualificationDecision
from qt.core import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QScrollArea,
    Qt,
    QVBoxLayout,
    QWidget,
)


class AwardSelectionDialog(QDialog):
    """Show matched award records for review; write-back happens only after accept."""

    def __init__(
        self,
        parent,
        report,
        template,
        status_text,
        lookup_title,
        lookup_author,
        write_enabled=False,
    ):
        QDialog.__init__(self, parent)
        self.setWindowTitle('Calibre Awards')
        self._lookup_title = lookup_title
        self._lookup_author = lookup_author
        self._rows = []

        layout = QVBoxLayout()
        self.setLayout(layout)

        book = QLabel(
            f'Book: {format_work_identity(lookup_title, lookup_author)}',
            self,
        )
        book.setWordWrap(True)
        book.setTextFormat(Qt.PlainText)
        layout.addWidget(book)

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
    ):
        QWidget.__init__(self, parent)
        self.assessment = assessment
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 8)
        self.setLayout(layout)

        formatted = format_award_result(assessment.result, template)
        self.checkbox = QCheckBox(formatted, self)
        self.checkbox.setChecked(
            assessment.qualification.decision is QualificationDecision.QUALIFIES
        )
        self.checkbox.setEnabled(selectable)
        result = assessment.result
        tooltip = f'Source: {result.source_name}'
        if result.source_url:
            tooltip += f'\n{result.source_url}'
        self.checkbox.setToolTip(tooltip)
        layout.addWidget(self.checkbox)

        source_identity = source_identity_if_different(
            lookup_title,
            lookup_author,
            result.work_title,
            result.work_author,
        )
        if source_identity is not None:
            source = QLabel(f'Source: {source_identity}', self)
            source.setWordWrap(True)
            source.setTextFormat(Qt.PlainText)
            layout.addWidget(source)

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
