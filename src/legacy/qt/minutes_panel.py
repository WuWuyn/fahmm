"""Minutes review controls embedded in the Meetings screen."""

from __future__ import annotations

import copy
import json
import threading
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from fahmm.cloud_minutes import DEFAULT_PROMPT, CloudMinutesService
from fahmm.library import MeetingLibrary
from fahmm.meeting_export import MeetingExportService, iter_citations, render_minutes
from fahmm.minutes_store import MinutesStore
from fahmm.offline_minutes import OfflineMinutesService
from fahmm.providers import ProviderProfiles
from fahmm.storage import MeetingStore
from legacy.qt.export_dialog import choose_export_target


class MinutesPanel(QWidget):
    offline_finished = Signal(str, str)
    offline_failed = Signal(str)
    cloud_finished = Signal(str, str)
    cloud_failed = Signal(str)

    def __init__(
        self, store: MeetingStore, open_source: Callable[[dict, bool], None],
        selected_segments: Callable[[], set[int]], transcript_dirty: Callable[[], bool],
        profiles: ProviderProfiles, cloud_service: CloudMinutesService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.library = MeetingLibrary(store)
        self.minutes = MinutesStore(store)
        self.exporter = MeetingExportService(store)
        self.offline = OfflineMinutesService(store)
        self.open_source = open_source
        self.selected_segments = selected_segments
        self.transcript_dirty = transcript_dirty
        self.profiles = profiles
        self.cloud = cloud_service or CloudMinutesService(store, profiles)
        self.meeting_id: str | None = None
        self._loaded_version: dict | None = None
        self._loaded_text = ""
        self._busy = False
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Meeting minutes"))
        mode_row = QHBoxLayout()
        self.mode_box = QComboBox()
        self.mode_box.addItem("Internal/Restricted", "restricted")
        self.mode_box.addItem("Cloud permitted", "cloud_permitted")
        self.mode_box.currentIndexChanged.connect(self._mode_changed)
        mode_row.addWidget(QLabel("Data sharing:"))
        mode_row.addWidget(self.mode_box)
        layout.addLayout(mode_row)

        actions = QHBoxLayout()
        self.offline_button = QPushButton("Create offline draft")
        self.template_button = QPushButton("Edit offline template")
        self.offline_button.clicked.connect(self.generate_offline)
        self.template_button.clicked.connect(self.edit_template)
        actions.addWidget(self.offline_button)
        actions.addWidget(self.template_button)
        layout.addLayout(actions)
        self.version_box = QComboBox()
        self.version_box.currentIndexChanged.connect(self._version_changed)
        layout.addWidget(self.version_box)
        self.review_label = QLabel("No minutes version")
        layout.addWidget(self.review_label)
        self.content_edit = QPlainTextEdit()
        self.content_edit.setPlaceholderText("Generate a draft to review and edit")
        self.content_edit.textChanged.connect(self._update_buttons)
        layout.addWidget(self.content_edit)
        edit_actions = QHBoxLayout()
        self.save_button = QPushButton("Save minutes edits as new version")
        self.approve_button = QPushButton("Approve this version")
        self.export_minutes_button = QPushButton("Export minutes.md")
        self.copy_markdown_button = QPushButton("Copy Markdown")
        self.save_button.clicked.connect(self.save_edits)
        self.approve_button.clicked.connect(self.approve)
        self.export_minutes_button.clicked.connect(self.export_minutes)
        self.copy_markdown_button.clicked.connect(self.copy_markdown)
        edit_actions.addWidget(self.save_button)
        edit_actions.addWidget(self.approve_button)
        edit_actions.addWidget(self.export_minutes_button)
        edit_actions.addWidget(self.copy_markdown_button)
        layout.addLayout(edit_actions)
        layout.addWidget(QLabel("Source citations"))
        self.citation_list = QListWidget()
        self.citation_list.currentItemChanged.connect(lambda *_: self._update_buttons())
        layout.addWidget(self.citation_list)
        citations = QHBoxLayout()
        self.open_button = QPushButton("Open cited transcript")
        self.play_button = QPushButton("Play cited audio")
        self.open_button.clicked.connect(lambda: self._open_citation(False))
        self.play_button.clicked.connect(lambda: self._open_citation(True))
        citations.addWidget(self.open_button)
        citations.addWidget(self.play_button)
        layout.addLayout(citations)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addWidget(QLabel("Optional provider minutes"))
        self.provider_box = QComboBox()
        layout.addWidget(self.provider_box)
        self.prompt_box = QComboBox()
        self.prompt_box.addItem("Structured Vietnamese minutes", DEFAULT_PROMPT)
        self.prompt_box.addItem(
            "Action-focused Vietnamese minutes",
            DEFAULT_PROMPT + " Ưu tiên ghi rõ việc cần làm và câu hỏi còn mở.",
        )
        self.prompt_box.currentIndexChanged.connect(
            lambda: self.prompt_edit.setPlainText(self.prompt_box.currentData())
        )
        layout.addWidget(self.prompt_box)
        self.prompt_edit = QPlainTextEdit(DEFAULT_PROMPT)
        self.prompt_edit.setPlaceholderText("Minutes generation prompt")
        layout.addWidget(self.prompt_edit)
        token_row = QHBoxLayout()
        token_row.addWidget(QLabel("Token limit:"))
        self.token_spin = QSpinBox()
        self.token_spin.setRange(100, 8000)
        self.token_spin.setValue(2000)
        token_row.addWidget(self.token_spin)
        layout.addLayout(token_row)
        self.review_checkbox = QCheckBox("I reviewed the selected transcript segments")
        layout.addWidget(self.review_checkbox)
        cloud_actions = QHBoxLayout()
        self.cloud_button = QPushButton("Preview and create provider draft")
        self.retry_button = QPushButton("Retry provider request")
        self.cloud_button.clicked.connect(self.start_cloud)
        self.retry_button.clicked.connect(self.start_cloud)
        cloud_actions.addWidget(self.cloud_button)
        cloud_actions.addWidget(self.retry_button)
        layout.addLayout(cloud_actions)
        self.review_checkbox.toggled.connect(self._update_buttons)
        self.provider_box.currentIndexChanged.connect(self._update_buttons)
        self.offline_finished.connect(self._offline_done)
        self.offline_failed.connect(self._offline_error)
        self.cloud_finished.connect(self._cloud_done)
        self.cloud_failed.connect(self._cloud_error)
        self.refresh_providers()
        self.set_meeting(None)

    def refresh_providers(self) -> None:
        selected = self.provider_box.currentData()
        self.provider_box.blockSignals(True)
        self.provider_box.clear()
        for profile in self.profiles.list_profiles():
            self.provider_box.addItem(f"{profile.name} · {profile.base_url}", profile.id)
            if profile.id == selected:
                self.provider_box.setCurrentIndex(self.provider_box.count() - 1)
        self.provider_box.blockSignals(False)
        self._update_buttons()

    def clear_review(self) -> None:
        self.review_checkbox.setChecked(False)
        self._update_buttons()

    def set_meeting(self, meeting_id: str | None) -> None:
        self.meeting_id = meeting_id
        self.clear_review()
        self.mode_box.blockSignals(True)
        mode = self.store.privacy_mode(meeting_id) if meeting_id else "restricted"
        self.mode_box.setCurrentIndex(self.mode_box.findData(mode))
        self.mode_box.blockSignals(False)
        self.refresh_versions()

    def _mode_changed(self) -> None:
        if not self.meeting_id:
            return
        try:
            self.library.set_privacy_mode(self.meeting_id, self.mode_box.currentData())
            self.status_label.setText(
                "Meeting classification saved. Every provider send still needs confirmation."
            )
        except Exception as exc:
            self.status_label.setText(f"Could not change classification: {exc}")
        self._update_buttons()

    def refresh_versions(self, selected_id: str | None = None) -> None:
        self.version_box.blockSignals(True)
        self.version_box.clear()
        if self.meeting_id:
            active = selected_id or self.store.metadata(self.meeting_id).get("active_minutes_version")
            for version in self.minutes.list_versions(self.meeting_id):
                label = (f"{version['created_at'][:19]} · {version['origin']} · "
                         f"{version['review_state']}")
                self.version_box.addItem(label, version["version_id"])
                if version["version_id"] == active:
                    self.version_box.setCurrentIndex(self.version_box.count() - 1)
        self.version_box.blockSignals(False)
        self._load_version()

    def _version_changed(self) -> None:
        if not self.meeting_id:
            return
        version_id = self.version_box.currentData()
        if version_id:
            self.minutes.select_version(self.meeting_id, version_id)
        self._load_version()

    def _load_version(self) -> None:
        self._loaded_version = None
        self.citation_list.clear()
        version_id = self.version_box.currentData()
        if self.meeting_id and version_id:
            self._loaded_version = self.minutes.read_version(self.meeting_id, version_id)
            content = self._loaded_version["content"]
            self._loaded_text = render_minutes(content)
            self.content_edit.setPlainText(self._loaded_text)
            manifest = self._loaded_version["manifest"]
            self.review_label.setText(
                f"{manifest['review_state'].title()} · {content.get('label', 'Minutes draft')}"
            )
            seen = set()
            for source in iter_citations(content):
                identity = (source["run_id"], source["segment_id"])
                if identity in seen:
                    continue
                seen.add(identity)
                item = QListWidgetItem(f"{source['start']:.1f}s · segment {source['segment_id']}")
                item.setData(Qt.UserRole, source)
                self.citation_list.addItem(item)
        else:
            self._loaded_text = ""
            self.content_edit.clear()
            self.review_label.setText("No minutes version")
        self._update_buttons()

    def _update_buttons(self) -> None:
        has_meeting = bool(self.meeting_id)
        has_version = self._loaded_version is not None
        self.mode_box.setEnabled(has_meeting and not self._busy)
        self.offline_button.setEnabled(has_meeting and not self._busy)
        self.template_button.setEnabled(has_meeting and not self._busy)
        self.save_button.setEnabled(has_version and self.content_edit.toPlainText() != self._loaded_text)
        self.approve_button.setEnabled(has_version and not self.save_button.isEnabled()
                                       and self._loaded_version["manifest"]["review_state"] != "approved")
        self.export_minutes_button.setEnabled(has_version and not self._busy)
        self.copy_markdown_button.setEnabled(has_version and not self._busy)
        selected = self.citation_list.currentItem() is not None
        self.open_button.setEnabled(selected)
        self.play_button.setEnabled(selected)
        can_send = (
            has_meeting and not self._busy and self.mode_box.currentData() == "cloud_permitted"
            and self.provider_box.count() > 0 and bool(self.selected_segments())
            and self.review_checkbox.isChecked() and not self.transcript_dirty()
        )
        self.cloud_button.setEnabled(can_send)
        self.retry_button.setEnabled(can_send)

    def start_cloud(self) -> None:
        if not self.meeting_id or not self.cloud_button.isEnabled():
            return
        try:
            selected = self.selected_segments()
            snapshot = self.cloud.prepare(
                self.meeting_id, self.provider_box.currentData(), selected,
                selected if self.review_checkbox.isChecked() else set(),
                prompt=self.prompt_edit.toPlainText(), max_tokens=self.token_spin.value(),
            )
        except Exception as exc:
            self.status_label.setText(f"Cannot prepare provider request: {exc}")
            return
        preview = snapshot.preview
        dialog = QDialog(self)
        dialog.setWindowTitle("Confirm meeting content disclosure")
        dialog.resize(740, 560)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"Destination: {preview['destination_hostname']}"))
        layout.addWidget(QLabel(f"Data types: {', '.join(preview['data_types'])}"))
        warning = QLabel(preview["warning"])
        warning.setWordWrap(True)
        layout.addWidget(warning)
        layout.addWidget(QLabel("Exact request body (prompt, selected transcript, model, token limit):"))
        payload = QPlainTextEdit(json.dumps(preview["request_body"], ensure_ascii=False,
                                         indent=2))
        payload.setReadOnly(True)
        layout.addWidget(payload)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        try:
            authorization = self.cloud.confirm(snapshot, accepted)
        except Exception as exc:
            self.status_label.setText(f"Request changed before sending: {exc}")
            return
        if authorization is None:
            self.status_label.setText("Provider request canceled; nothing was sent")
            return
        self._busy = True
        self.status_label.setText("Waiting for provider response…")
        self._update_buttons()

        def run() -> None:
            try:
                self.cloud_finished.emit(snapshot.meeting_id,
                                         self.cloud.generate(snapshot, authorization))
            except Exception as exc:
                self.cloud_failed.emit(str(exc))

        threading.Thread(target=run, daemon=True).start()

    def _cloud_done(self, meeting_id: str, version_id: str) -> None:
        self._busy = False
        if self.meeting_id == meeting_id:
            self.refresh_versions(version_id)
        self.status_label.setText("Provider draft saved locally; review sources before approval")
        self._update_buttons()

    def _cloud_error(self, message: str) -> None:
        self._busy = False
        self.status_label.setText(f"Provider request failed: {message}")
        self._update_buttons()

    def generate_offline(self) -> None:
        if not self.meeting_id or self._busy:
            return
        meeting_id = self.meeting_id
        self._busy = True
        self.status_label.setText("Creating a local extractive draft…")
        self._update_buttons()

        def run() -> None:
            try:
                self.offline_finished.emit(meeting_id, self.offline.generate(meeting_id))
            except Exception as exc:
                self.offline_failed.emit(str(exc))

        threading.Thread(target=run, daemon=True).start()

    def _offline_done(self, meeting_id: str, version_id: str) -> None:
        self._busy = False
        if self.meeting_id == meeting_id:
            self.refresh_versions(version_id)
        self.status_label.setText("Offline extractive draft saved locally; review its sources")
        self._update_buttons()

    def _offline_error(self, message: str) -> None:
        self._busy = False
        self.status_label.setText(f"Offline draft failed: {message}")
        self._update_buttons()

    def save_edits(self) -> None:
        if not self.meeting_id or not self._loaded_version:
            return
        content = copy.deepcopy(self._loaded_version["content"])
        content["user_text"] = self.content_edit.toPlainText()
        content["label"] = "Unverified · Edited minutes"
        content["user_edited"] = True
        try:
            version_id = self.minutes.edit_version(
                self.meeting_id, self._loaded_version["manifest"]["version_id"], content
            )
            self.refresh_versions(version_id)
            self.status_label.setText("Minutes edits saved as a new unverified version")
        except Exception as exc:
            self.status_label.setText(f"Could not save minutes: {exc}")

    def approve(self) -> None:
        if not self.meeting_id or not self._loaded_version:
            return
        version_id = self._loaded_version["manifest"]["version_id"]
        try:
            self.minutes.approve_version(self.meeting_id, version_id)
            self.refresh_versions(version_id)
            self.status_label.setText("Minutes version approved locally")
        except Exception as exc:
            self.status_label.setText(f"Could not approve minutes: {exc}")

    def export_minutes(self) -> None:
        if not self.meeting_id or not self._loaded_version:
            QMessageBox.information(self, "No minutes to export", "Save a minutes version first.")
            return
        if self.content_edit.toPlainText() != self._loaded_text:
            QMessageBox.information(
                self, "Unsaved minutes edits",
                "Save minutes edits as a new version or discard them before exporting.",
            )
            return
        selected = choose_export_target(self, "minutes.md", "Markdown files (*.md)")
        if selected is None:
            return
        destination, overwrite = selected
        try:
            version_id = self._loaded_version["manifest"]["version_id"]
            self.exporter.export_minutes(
                self.meeting_id, version_id, destination, overwrite=overwrite
            )
            self.status_label.setText(f"Minutes exported to {destination}")
        except Exception as exc:
            QMessageBox.warning(self, "Could not export minutes", str(exc))

    def copy_markdown(self) -> None:
        if not self.meeting_id or not self._loaded_version:
            QMessageBox.information(self, "No minutes to copy", "Save a minutes version first.")
            return
        if self.content_edit.toPlainText() != self._loaded_text:
            QMessageBox.information(
                self, "Unsaved minutes edits",
                "Save minutes edits as a new version or discard them before copying.",
            )
            return
        try:
            version_id = self._loaded_version["manifest"]["version_id"]
            QApplication.clipboard().setText(
                self.exporter.minutes_markdown(self.meeting_id, version_id)
            )
            self.status_label.setText("Selected saved minutes copied as Markdown")
        except Exception as exc:
            QMessageBox.warning(self, "Could not copy minutes", str(exc))

    def _open_citation(self, play: bool) -> None:
        item = self.citation_list.currentItem()
        if item:
            self.open_source(item.data(Qt.UserRole), play)

    def edit_template(self) -> None:
        if not self.meeting_id:
            return
        template = self.minutes.read_template(self.meeting_id)
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit offline minutes template")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        heading_edits = {}
        for key, label in template["headings"].items():
            edit = QLineEdit(label)
            form.addRow(f"{key.replace('_', ' ').title()} heading:", edit)
            heading_edits[key] = edit
        guidance = QPlainTextEdit(template["guidance"])
        limit = QSpinBox()
        limit.setRange(1, 10)
        limit.setValue(template["topic_limit"])
        form.addRow("Review guidance:", guidance)
        form.addRow("Topic count:", limit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        template["headings"] = {key: edit.text() for key, edit in heading_edits.items()}
        template["guidance"] = guidance.toPlainText()
        template["topic_limit"] = limit.value()
        try:
            self.minutes.save_template(self.meeting_id, template)
            self.status_label.setText("Template saved for future drafts")
        except Exception as exc:
            QMessageBox.warning(self, "Could not save template", str(exc))
