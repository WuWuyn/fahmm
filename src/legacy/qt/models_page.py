"""English model management screen. Hub calls happen only after Download."""

from __future__ import annotations

import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from fahmm.model_catalog import BY_REPOSITORY, CATALOG
from fahmm.models import InstalledModel, ModelManager


class ModelsPage(QWidget):
    download_progress = Signal(str, int, int)
    download_finished = Signal(object)
    download_failed = Signal(str)

    def __init__(self, manager: ModelManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self._busy = False
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Local Whisper models"))
        layout.addWidget(
            QLabel(
                "Models download only when you click Download. No meeting audio or transcript is sent."
            )
        )

        self.choice_box = QComboBox()
        for choice in CATALOG:
            self.choice_box.addItem(choice.name, choice.repository)
        self.choice_box.addItem("Custom Hugging Face repository…", None)
        self.choice_box.currentIndexChanged.connect(self._update_choice)
        layout.addWidget(self.choice_box)
        self.custom_repo = QLineEdit()
        self.custom_repo.setPlaceholderText("publisher/repository")
        self.custom_repo.setVisible(False)
        layout.addWidget(self.custom_repo)
        self.details = QLabel()
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        self.download_button = QPushButton("Download selected model")
        self.download_button.clicked.connect(self._download)
        layout.addWidget(self.download_button)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        layout.addWidget(QLabel("Installed models"))
        self.installed_list = QListWidget()
        layout.addWidget(self.installed_list)
        buttons = QHBoxLayout()
        self.select_button = QPushButton("Use selected model")
        self.delete_button = QPushButton("Delete selected model")
        self.select_button.clicked.connect(self._select)
        self.delete_button.clicked.connect(self._delete)
        buttons.addWidget(self.select_button)
        buttons.addWidget(self.delete_button)
        layout.addLayout(buttons)
        self.installed_list.currentItemChanged.connect(lambda *_: self._update_buttons())

        self.download_progress.connect(self._show_progress)
        self.download_finished.connect(self._download_done)
        self.download_failed.connect(self._download_error)
        self._update_choice()
        self.refresh()

    def _update_choice(self) -> None:
        repository = self.choice_box.currentData()
        self.custom_repo.setVisible(repository is None)
        if repository is None:
            self.details.setText(
                "Only CTranslate2 Whisper repositories are accepted. The app checks the files and "
                "declared license before installation."
            )
            return
        choice = BY_REPOSITORY[repository]
        size = f"{choice.estimated_bytes / 1_000_000:.0f} MB"
        self.details.setText(
            f"{choice.publisher} · {choice.license} · about {size}. "
            f"{choice.resource_warning or 'Suitable starting point for an ordinary CPU.'}"
        )

    def refresh(self) -> None:
        previous = self.installed_list.currentItem()
        previous_id = previous.data(Qt.UserRole) if previous else None
        self.installed_list.clear()
        selected = self.manager.selected()
        for model in self.manager.installed():
            marker = "● " if selected and model.id == selected.id else ""
            item = QListWidgetItem(
                f"{marker}{model.repository} · {model.license} · "
                f"{model.bytes / 1_000_000:.0f} MB · {model.revision[:8]}"
            )
            item.setData(Qt.UserRole, model.id)
            self.installed_list.addItem(item)
            if model.id == previous_id:
                self.installed_list.setCurrentItem(item)
        self._update_buttons()

    def _update_buttons(self) -> None:
        selected = self.installed_list.currentItem() is not None
        self.select_button.setEnabled(selected and not self._busy)
        self.delete_button.setEnabled(selected and not self._busy)
        self.download_button.setEnabled(not self._busy)

    def _download(self) -> None:
        if self._busy:
            return
        repository = self.choice_box.currentData() or self.custom_repo.text().strip()
        if not repository:
            QMessageBox.warning(self, "Model repository", "Enter a Hugging Face repository ID.")
            return
        choice = BY_REPOSITORY.get(repository)
        if choice and choice.resource_warning:
            answer = QMessageBox.question(self, "Large model", choice.resource_warning)
            if answer != QMessageBox.Yes:
                return
        self._busy = True
        self._update_buttons()
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("Inspecting repository…")

        def run() -> None:
            try:
                model = self.manager.download(
                    repository,
                    progress=lambda stage, current, total: self.download_progress.emit(
                        stage, current, total
                    ),
                )
                self.download_finished.emit(model)
            except Exception as exc:
                self.download_failed.emit(str(exc))

        threading.Thread(target=run, daemon=True).start()

    def _show_progress(self, stage: str, current: int, total: int) -> None:
        self.status_label.setText(stage)
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        else:
            self.progress_bar.setRange(0, 0)

    def _download_done(self, model: InstalledModel) -> None:
        self._busy = False
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText(f"Installed {model.repository} for offline use")
        self.refresh()

    def _download_error(self, message: str) -> None:
        self._busy = False
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Download failed: {message}")
        self._update_buttons()
        QMessageBox.warning(self, "Model download failed", message)

    def _select(self) -> None:
        item = self.installed_list.currentItem()
        if item is None:
            return
        try:
            model = self.manager.select(item.data(Qt.UserRole))
            self.status_label.setText(f"Using {model.repository} offline")
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Cannot select model", str(exc))

    def _delete(self) -> None:
        item = self.installed_list.currentItem()
        if item is None:
            return
        if (
            QMessageBox.question(self, "Delete model", "Delete this local model installation?")
            != QMessageBox.Yes
        ):
            return
        try:
            self.manager.delete(item.data(Qt.UserRole))
            self.status_label.setText("Model deleted; meeting data is unchanged")
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Cannot delete model", str(exc))
