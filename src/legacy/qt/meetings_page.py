"""Local meeting list and post-recording ASR controls."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fahmm.asr_jobs import ASRJobController
from fahmm.cloud_minutes import CloudMinutesService
from fahmm.library import MeetingLibrary
from fahmm.media import import_audio
from fahmm.meeting_deletion import MeetingDeletionService
from fahmm.meeting_export import MeetingExportService
from fahmm.models import ModelManager
from fahmm.providers import ProviderProfiles
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore
from legacy.qt.export_dialog import choose_export_target
from legacy.qt.minutes_panel import MinutesPanel
from legacy.qt.playback import AudioPlayer


class MeetingsPage(QWidget):
    import_finished = Signal(str)
    import_failed = Signal(str)

    def __init__(
        self,
        store: MeetingStore,
        models: ModelManager,
        jobs: ASRJobController | None = None,
        parent: QWidget | None = None,
        *,
        profiles: ProviderProfiles | None = None,
        cloud_service: CloudMinutesService | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.library = MeetingLibrary(store)
        self.models = models
        self.jobs = jobs or ASRJobController(store, models)
        self.transcripts = TranscriptStore(store)
        self.exporter = MeetingExportService(store)
        self.deletion = MeetingDeletionService(store)
        self.profiles = profiles or ProviderProfiles()
        self.player = AudioPlayer(self)
        self._last_job_state = "idle"
        self._import_busy = False
        self._loaded_run_id: str | None = None
        self._dirty = False
        self._original_segments: dict[int, dict] = {}

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        outer = QVBoxLayout(self)
        outer.addWidget(scroll)
        scroll.setWidget(container)
        layout.addWidget(QLabel("Meetings"))
        layout.addWidget(QLabel("Audio and transcripts stay on this device."))
        self.import_button = QPushButton("Import audio…")
        self.import_button.clicked.connect(self._choose_import)
        layout.addWidget(self.import_button)
        self.meeting_list = QListWidget()
        self.meeting_list.currentItemChanged.connect(lambda *_: self._selection_changed())
        layout.addWidget(self.meeting_list)

        rename_row = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Meeting name")
        self.rename_button = QPushButton("Rename")
        self.delete_button = QPushButton("Delete meeting…")
        self.rename_button.clicked.connect(self._rename)
        self.delete_button.clicked.connect(self._delete_meeting)
        rename_row.addWidget(self.name_edit)
        rename_row.addWidget(self.rename_button)
        rename_row.addWidget(self.delete_button)
        layout.addLayout(rename_row)

        playback_row = QHBoxLayout()
        self.play_button = QPushButton("Play audio")
        self.stop_playback_button = QPushButton("Stop playback")
        self.play_button.clicked.connect(self._play)
        self.stop_playback_button.clicked.connect(self.player.stop)
        playback_row.addWidget(self.play_button)
        playback_row.addWidget(self.stop_playback_button)
        layout.addLayout(playback_row)

        options = QFormLayout()
        self.model_box = QComboBox()
        self.language_box = QComboBox()
        self.language_box.addItem("Vietnamese (default)", "vi")
        self.language_box.addItem("Auto Detect", "auto")
        self.language_box.addItem("English", "en")
        options.addRow("Whisper model:", self.model_box)
        options.addRow("Speech language:", self.language_box)
        layout.addLayout(options)
        actions = QHBoxLayout()
        self.transcribe_button = QPushButton("Transcribe")
        self.cancel_button = QPushButton("Cancel")
        self.retry_button = QPushButton("Retry")
        self.transcribe_button.clicked.connect(self._transcribe)
        self.cancel_button.clicked.connect(self.jobs.cancel)
        self.retry_button.clicked.connect(self._retry)
        for button in (self.transcribe_button, self.cancel_button, self.retry_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        self.status_label = QLabel("Select a meeting or import audio")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addWidget(QLabel("Transcript review"))
        self.run_box = QComboBox()
        self.run_box.currentIndexChanged.connect(self._run_changed)
        layout.addWidget(self.run_box)
        self.segment_table = QTableWidget(0, 2)
        self.segment_table.setHorizontalHeaderLabels(["Source time", "Transcript text"])
        self.segment_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.segment_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.segment_table.horizontalHeader().setStretchLastSection(True)
        self.segment_table.itemChanged.connect(self._mark_dirty)
        self.segment_table.currentCellChanged.connect(lambda *_: self._show_original())
        layout.addWidget(self.segment_table)
        self.original_label = QLabel("Original ASR text: Select a segment")
        self.original_label.setWordWrap(True)
        layout.addWidget(self.original_label)
        review_actions = QHBoxLayout()
        self.play_segment_button = QPushButton("Play selected segment")
        self.save_transcript_button = QPushButton("Save transcript edits")
        self.export_transcript_button = QPushButton("Export transcript.txt")
        self.play_segment_button.clicked.connect(self._play_segment)
        self.save_transcript_button.clicked.connect(self._save_transcript)
        self.export_transcript_button.clicked.connect(self._export_transcript)
        review_actions.addWidget(self.play_segment_button)
        review_actions.addWidget(self.save_transcript_button)
        review_actions.addWidget(self.export_transcript_button)
        layout.addLayout(review_actions)
        self.minutes_panel = MinutesPanel(
            store, self.open_minutes_source, self.selected_segment_ids,
            lambda: self._dirty, self.profiles, cloud_service,
        )
        self.segment_table.itemSelectionChanged.connect(self.minutes_panel.clear_review)
        layout.addWidget(self.minutes_panel)

        cleanup = QGroupBox("Storage cleanup")
        cleanup_layout = QVBoxLayout(cleanup)
        cleanup_layout.addWidget(QLabel("Incomplete meeting deletions"))
        self.pending_deletions = QListWidget()
        self.pending_deletions.currentItemChanged.connect(self._update_cleanup_buttons)
        cleanup_layout.addWidget(self.pending_deletions)
        self.retry_cleanup_button = QPushButton("Retry selected deletion cleanup")
        self.retry_cleanup_button.clicked.connect(self._retry_deletion_cleanup)
        cleanup_layout.addWidget(self.retry_cleanup_button)
        cleanup_layout.addWidget(QLabel("Abandoned audio imports"))
        self.orphan_imports = QListWidget()
        self.orphan_imports.currentItemChanged.connect(self._update_cleanup_buttons)
        cleanup_layout.addWidget(self.orphan_imports)
        self.clean_import_button = QPushButton("Clean selected abandoned import")
        self.clean_import_button.clicked.connect(self._clean_abandoned_import)
        cleanup_layout.addWidget(self.clean_import_button)
        layout.addWidget(cleanup)

        self.import_finished.connect(self._import_done)
        self.import_failed.connect(self._import_error)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(200)
        self.refresh_models()
        self.refresh()

    def _selected_id(self) -> str | None:
        item = self.meeting_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def refresh(self, selected_id: str | None = None) -> None:
        selected_id = selected_id or self._selected_id()
        self.meeting_list.clear()
        for meeting in self.library.list_meetings():
            label = (
                f"{meeting.created_at[:19]} · {meeting.name} · "
                f"{meeting.source_kind} · {meeting.status}"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, meeting.id)
            self.meeting_list.addItem(item)
            if meeting.id == selected_id:
                self.meeting_list.setCurrentItem(item)
        self._selection_changed()
        self._refresh_cleanup()

    def _refresh_cleanup(self) -> None:
        self.pending_deletions.clear()
        for meeting_id in self.deletion.incomplete_deletions():
            item = QListWidgetItem(f"Pending deletion · {meeting_id}")
            item.setData(Qt.UserRole, meeting_id)
            self.pending_deletions.addItem(item)
        self.orphan_imports.clear()
        for meeting_id in self.deletion.orphan_imports():
            item = QListWidgetItem(f"Abandoned import · {meeting_id}")
            item.setData(Qt.UserRole, meeting_id)
            self.orphan_imports.addItem(item)
        self._update_cleanup_buttons()

    def _update_cleanup_buttons(self, *_args) -> None:
        self.retry_cleanup_button.setEnabled(self.pending_deletions.currentItem() is not None)
        self.clean_import_button.setEnabled(self.orphan_imports.currentItem() is not None)

    def refresh_models(self) -> None:
        previous = self.model_box.currentData()
        self.model_box.clear()
        selected = self.models.selected()
        for model in self.models.installed():
            self.model_box.addItem(f"{model.repository} ({model.revision[:8]})", model.id)
            if model.id == (previous or (selected.id if selected else None)):
                self.model_box.setCurrentIndex(self.model_box.count() - 1)
        self._update_buttons()

    def _selection_changed(self) -> None:
        meeting_id = self._selected_id()
        if meeting_id:
            meeting = self.library.get(meeting_id)
            self.name_edit.setText(meeting.name)
            mode = "Cloud permitted" if meeting.privacy_mode == "cloud_permitted" else "Internal/Restricted"
            self.status_label.setText(f"{meeting.name} · {meeting.status} · {mode}")
        else:
            self.name_edit.clear()
        self._update_buttons()
        self._refresh_transcripts()
        self.minutes_panel.set_meeting(meeting_id)

    def _update_buttons(self) -> None:
        meeting_id = self._selected_id()
        snapshot = self.jobs.snapshot()
        active = snapshot.state in ("loading", "running", "cancelling")
        completed_audio = bool(meeting_id and self.library.get(meeting_id).recording_state == "completed")
        self.name_edit.setEnabled(bool(meeting_id))
        self.rename_button.setEnabled(bool(meeting_id))
        self.delete_button.setEnabled(bool(meeting_id))
        self.play_button.setEnabled(completed_audio)
        self.transcribe_button.setEnabled(completed_audio and self.model_box.count() > 0 and not active)
        self.cancel_button.setEnabled(active and snapshot.meeting_id == meeting_id)
        self.retry_button.setEnabled(
            snapshot.state in ("cancelled", "error") and snapshot.meeting_id == meeting_id
        )
        self.import_button.setEnabled(not self._import_busy)
        if hasattr(self, "save_transcript_button"):
            self.save_transcript_button.setEnabled(self._dirty and self._loaded_run_id is not None)
            self.play_segment_button.setEnabled(self.segment_table.currentRow() >= 0)
            self.export_transcript_button.setEnabled(self._loaded_run_id is not None)

    def _choose_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import audio", "", "Audio files (*.wav *.mp3 *.m4a *.flac)"
        )
        if path:
            self.import_file(Path(path))

    def import_file(self, path: Path) -> None:
        if self._import_busy:
            raise RuntimeError("An audio import is already running")
        self._import_busy = True
        self._update_buttons()
        self.status_label.setText("Importing and checking local audio…")

        def run() -> None:
            try:
                self.import_finished.emit(import_audio(self.store, path))
            except Exception as exc:
                self.import_failed.emit(str(exc))

        threading.Thread(target=run, daemon=True).start()

    def _import_done(self, meeting_id: str) -> None:
        self._import_busy = False
        self.refresh(selected_id=meeting_id)
        self.status_label.setText("Audio imported locally")
        self._refresh_cleanup()

    def _import_error(self, message: str) -> None:
        self._import_busy = False
        self._update_buttons()
        self.status_label.setText(f"Import failed: {message}")
        QMessageBox.warning(self, "Audio import failed", message)
        self._refresh_cleanup()

    def _rename(self) -> None:
        meeting_id = self._selected_id()
        if not meeting_id:
            return
        try:
            self.library.rename(meeting_id, self.name_edit.text())
            self.refresh(selected_id=meeting_id)
        except Exception as exc:
            QMessageBox.warning(self, "Cannot rename meeting", str(exc))

    def _delete_meeting(self) -> None:
        meeting_id = self._selected_id()
        if not meeting_id:
            return
        meeting = self.library.get(meeting_id)
        answer = QMessageBox.question(
            self, "Delete meeting?",
            f"Delete '{meeting.name}' and its fahmm audio, transcripts, minutes, metadata, "
            "and temporary files?\n\nThis cannot be undone. Exports, clipboard copies, and "
            "system backups remain. Ordinary deletion is not secure erasure.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.player.stop()
            self.deletion.delete(meeting_id)
            self.refresh()
            self.status_label.setText("Meeting data deleted locally")
        except Exception as exc:
            self._refresh_cleanup()
            QMessageBox.warning(self, "Could not delete meeting", str(exc))

    def _retry_deletion_cleanup(self) -> None:
        item = self.pending_deletions.currentItem()
        if item is None:
            return
        try:
            self.deletion.retry_cleanup(item.data(Qt.UserRole))
            self._refresh_cleanup()
            self.status_label.setText("Incomplete meeting deletion cleaned locally")
        except Exception as exc:
            QMessageBox.warning(self, "Could not finish deletion", str(exc))
            self._refresh_cleanup()

    def _clean_abandoned_import(self) -> None:
        item = self.orphan_imports.currentItem()
        if item is None:
            return
        meeting_id = item.data(Qt.UserRole)
        answer = QMessageBox.question(
            self, "Clean abandoned import?",
            f"Remove the unfinished fahmm import {meeting_id}? The original audio file "
            "outside fahmm will remain untouched.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.deletion.cleanup_orphan_import(meeting_id, confirmed=True)
            self._refresh_cleanup()
            self.status_label.setText("Abandoned import cleaned locally")
        except Exception as exc:
            QMessageBox.warning(self, "Could not clean import", str(exc))
            self._refresh_cleanup()

    def _play(self) -> None:
        meeting_id = self._selected_id()
        if not meeting_id:
            return
        try:
            self.player.play(self.library.audio_path(meeting_id))
            self.status_label.setText("Playing local audio")
        except Exception as exc:
            QMessageBox.warning(self, "Cannot play audio", str(exc))

    def play_at(self, seconds: float) -> None:
        meeting_id = self._selected_id()
        if meeting_id:
            self.player.play(self.library.audio_path(meeting_id), seconds)

    def selected_segment_ids(self) -> set[int]:
        rows = {index.row() for index in self.segment_table.selectionModel().selectedRows()}
        return {self.segment_table.item(row, 0).data(Qt.UserRole) for row in rows}

    def open_minutes_source(self, source: dict, play: bool) -> None:
        run_id = source["run_id"]
        if self.run_box.currentData() != run_id:
            index = self.run_box.findData(run_id)
            if index < 0:
                raise ValueError("The cited transcript run is unavailable")
            self.run_box.setCurrentIndex(index)
        for row in range(self.segment_table.rowCount()):
            if self.segment_table.item(row, 0).data(Qt.UserRole) == source["segment_id"]:
                self.segment_table.setCurrentCell(row, 1)
                if play:
                    self.play_at(float(source["start"]))
                return
        raise ValueError("The cited transcript segment is unavailable")

    @staticmethod
    def _time_text(seconds: float) -> str:
        whole = int(seconds)
        return f"{whole // 3600:02d}:{whole // 60 % 60:02d}:{whole % 60:02d}"

    def _refresh_transcripts(self) -> None:
        meeting_id = self._selected_id()
        self.run_box.blockSignals(True)
        self.run_box.clear()
        if meeting_id:
            active = self.store.metadata(meeting_id).get("active_run")
            for run in self.transcripts.list_runs(meeting_id):
                label = (
                    f"{run['created_at'][:19]} · {run['model_repository']} "
                    f"({run['model_revision'][:8]})"
                )
                self.run_box.addItem(label, run["run_id"])
                if run["run_id"] == active:
                    self.run_box.setCurrentIndex(self.run_box.count() - 1)
        self.run_box.blockSignals(False)
        self._load_run()

    def _run_changed(self) -> None:
        meeting_id = self._selected_id()
        run_id = self.run_box.currentData()
        if not meeting_id or not run_id:
            return
        if self._dirty and self._loaded_run_id and run_id != self._loaded_run_id:
            answer = QMessageBox.question(
                self, "Unsaved transcript edits", "Discard unsaved transcript edits?"
            )
            if answer != QMessageBox.Yes:
                self.run_box.blockSignals(True)
                self.run_box.setCurrentIndex(self.run_box.findData(self._loaded_run_id))
                self.run_box.blockSignals(False)
                return
        try:
            self.transcripts.select_run(meeting_id, run_id)
            self._load_run()
        except Exception as exc:
            QMessageBox.warning(self, "Cannot open transcript", str(exc))

    def _load_run(self) -> None:
        meeting_id = self._selected_id()
        run_id = self.run_box.currentData()
        self.segment_table.blockSignals(True)
        self.segment_table.setRowCount(0)
        self._original_segments = {}
        self._loaded_run_id = None
        self._dirty = False
        if meeting_id and run_id:
            try:
                data = self.transcripts.read_run(meeting_id, run_id)
                self._original_segments = {s["id"]: s for s in data["original"]}
                for row, segment in enumerate(data["working"]):
                    self.segment_table.insertRow(row)
                    stamp = QTableWidgetItem(
                        f"{self._time_text(segment['start'])}–{self._time_text(segment['end'])}"
                    )
                    stamp.setFlags(stamp.flags() & ~Qt.ItemIsEditable)
                    stamp.setData(Qt.UserRole, segment["id"])
                    stamp.setData(Qt.UserRole + 1, segment["start"])
                    self.segment_table.setItem(row, 0, stamp)
                    self.segment_table.setItem(row, 1, QTableWidgetItem(segment["text"]))
                self._loaded_run_id = run_id
            except Exception as exc:
                self.status_label.setText(f"Cannot open transcript: {exc}")
        self.segment_table.blockSignals(False)
        self.original_label.setText("Original ASR text: Select a segment")
        self._update_buttons()

    def _mark_dirty(self, item: QTableWidgetItem) -> None:
        if item.column() == 1:
            self._dirty = True
            self.minutes_panel.clear_review()
            self._update_buttons()

    def _show_original(self) -> None:
        row = self.segment_table.currentRow()
        stamp = self.segment_table.item(row, 0) if row >= 0 else None
        if stamp:
            original = self._original_segments.get(stamp.data(Qt.UserRole))
            self.original_label.setText(
                f"Original ASR text: {original['text']}" if original else "Original ASR text: Missing"
            )
        else:
            self.original_label.setText("Original ASR text: Select a segment")
        self._update_buttons()

    def _play_segment(self) -> None:
        row = self.segment_table.currentRow()
        stamp = self.segment_table.item(row, 0) if row >= 0 else None
        if stamp:
            try:
                self.play_at(float(stamp.data(Qt.UserRole + 1)))
            except Exception as exc:
                QMessageBox.warning(self, "Cannot play segment", str(exc))

    def _save_transcript(self) -> None:
        meeting_id = self._selected_id()
        if not meeting_id or not self._loaded_run_id:
            return
        edits = {
            self.segment_table.item(row, 0).data(Qt.UserRole): self.segment_table.item(row, 1).text()
            for row in range(self.segment_table.rowCount())
        }
        try:
            self.transcripts.save_edits(meeting_id, self._loaded_run_id, edits)
            self._dirty = False
            self.status_label.setText("Transcript edits saved locally")
            self._update_buttons()
        except Exception as exc:
            QMessageBox.warning(self, "Could not save transcript", str(exc))

    def _export_transcript(self) -> None:
        meeting_id = self._selected_id()
        run_id = self.run_box.currentData()
        if not meeting_id or not run_id:
            QMessageBox.information(self, "No transcript to export", "Save a transcript run first.")
            return
        if self._dirty:
            QMessageBox.information(
                self, "Unsaved transcript edits",
                "Save transcript edits or discard them before exporting.",
            )
            return
        selected = choose_export_target(self, "transcript.txt", "Text files (*.txt)")
        if selected is None:
            return
        destination, overwrite = selected
        try:
            self.exporter.export_transcript(meeting_id, run_id, destination, overwrite=overwrite)
            self.status_label.setText(f"Transcript exported to {destination}")
        except Exception as exc:
            QMessageBox.warning(self, "Could not export transcript", str(exc))

    def _transcribe(self) -> None:
        meeting_id = self._selected_id()
        model_id = self.model_box.currentData()
        if not meeting_id or not model_id:
            return
        try:
            self.jobs.start(meeting_id, model_id, self.language_box.currentData())
            self.status_label.setText("Loading local Whisper model…")
            self._update_buttons()
        except Exception as exc:
            QMessageBox.warning(self, "Cannot transcribe", str(exc))

    def _retry(self) -> None:
        try:
            self.jobs.retry()
            self.status_label.setText("Retrying local transcription…")
            self._update_buttons()
        except Exception as exc:
            QMessageBox.warning(self, "Cannot retry transcription", str(exc))

    def _tick(self) -> None:
        snapshot = self.jobs.snapshot()
        if snapshot.state in ("loading", "running", "cancelling"):
            if snapshot.progress is None:
                self.progress_bar.setRange(0, 0)
            else:
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(round(snapshot.progress * 100))
            self.status_label.setText(
                f"{snapshot.state.capitalize()} · {snapshot.segment_count} segments processed"
            )
        elif snapshot.state != self._last_job_state and snapshot.state != "idle":
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100 if snapshot.state == "completed" else 0)
            self.status_label.setText(
                f"Transcription {snapshot.state}"
                + (f": {snapshot.error}" if snapshot.error else "")
            )
            self.refresh(selected_id=snapshot.meeting_id)
        self._last_job_state = snapshot.state
        self._update_buttons()
