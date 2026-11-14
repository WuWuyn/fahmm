"""English Qt recorder interface. Device access starts only on user action."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from fahmm.cloud_minutes import CloudMinutesService
from fahmm.controller import SessionController, State
from fahmm.models import ModelManager
from fahmm.providers import ProviderProfiles
from legacy.qt.meetings_page import MeetingsPage
from legacy.qt.models_page import ModelsPage
from legacy.qt.settings_page import SettingsPage

STATUS_TEXT = {
    State.IDLE: "Ready to record",
    State.STARTING: "Opening devices…",
    State.RECORDING: "● Recording",
    State.PAUSED: "Ⅱ Paused",
    State.FINALIZING: "Creating playback file…",
    State.COMPLETED: "Recording saved",
    State.ERROR: "An error occurred — saved audio is preserved",
}


class RecorderWindow(QMainWindow):
    def __init__(
        self, controller: SessionController, model_manager: ModelManager | None = None,
        provider_profiles: ProviderProfiles | None = None,
        cloud_service: CloudMinutesService | None = None,
    ) -> None:
        super().__init__()
        self.controller = controller
        self.model_manager = model_manager or ModelManager()
        self.provider_profiles = provider_profiles or ProviderProfiles()
        self._last_error: str | None = None
        self._last_state: State | None = None
        self._close_requested = False
        self.setWindowTitle("fahmm — Fah Meeting Minutes")
        self.resize(920, 700)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setSpacing(14)
        title = QLabel("fahmm · Meeting recorder")
        title.setStyleSheet("font-size: 22px; font-weight: 700")
        layout.addWidget(title)
        layout.addWidget(
            QLabel("Audio stays on this device. Capture starts only when you press Record.")
        )

        devices = QGroupBox("Audio sources")
        form = QFormLayout(devices)
        self.system_box = QComboBox()
        self.microphone_box = QComboBox()
        form.addRow("System audio:", self.system_box)
        form.addRow("Microphone:", self.microphone_box)
        self.refresh_button = QPushButton("Refresh devices")
        self.refresh_button.clicked.connect(self.refresh_devices)
        form.addRow(self.refresh_button)
        layout.addWidget(devices)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("font-size: 17px; font-weight: 600")
        self.status_label.setAccessibleName("Recording status")
        layout.addWidget(self.status_label)
        self.timer_label = QLabel("00:00:00")
        self.timer_label.setStyleSheet("font-size: 36px; font-variant-numeric: tabular-nums")
        self.timer_label.setAccessibleName("Recording duration")
        layout.addWidget(self.timer_label)

        buttons = QHBoxLayout()
        self.record_button = QPushButton("Record")
        self.pause_button = QPushButton("Pause")
        self.stop_button = QPushButton("Stop and save")
        self.record_button.clicked.connect(self._on_record)
        self.pause_button.clicked.connect(self._on_pause)
        self.stop_button.clicked.connect(self._on_stop)
        for button in (self.record_button, self.pause_button, self.stop_button):
            button.setMinimumHeight(42)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        recovery = QGroupBox("Incomplete recordings")
        recovery_layout = QVBoxLayout(recovery)
        self.recovery_list = QListWidget()
        recovery_layout.addWidget(self.recovery_list)
        self.recover_button = QPushButton("Recover selected recording")
        self.recover_button.clicked.connect(self._on_recover)
        recovery_layout.addWidget(self.recover_button)
        layout.addWidget(recovery)

        self.result_label = QLabel("Playback file: None yet")
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)
        layout.addStretch()
        self.recorder_page = root
        self.meetings_page = MeetingsPage(
            self.controller.store, self.model_manager, profiles=self.provider_profiles,
            cloud_service=cloud_service,
        )
        self.models_page = ModelsPage(self.model_manager)
        self.settings_page = SettingsPage(self.provider_profiles)

        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        navigation = QHBoxLayout()
        self.stack = QStackedWidget()
        self.nav_buttons: dict[str, QPushButton] = {}
        for name, page in (
            ("Recorder", self.recorder_page),
            ("Meetings", self.meetings_page),
            ("Models", self.models_page),
            ("Settings", self.settings_page),
        ):
            button = QPushButton(name)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, target=name: self.switch_to(target))
            navigation.addWidget(button)
            self.nav_buttons[name] = button
            self.stack.addWidget(page)
        shell_layout.addLayout(navigation)
        shell_layout.addWidget(self.stack)
        self.setCentralWidget(shell)
        self.switch_to("Recorder")

        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._on_record)
        QShortcut(QKeySequence("Space"), self, activated=self._on_pause)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_stop)
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(200)
        self.refresh_devices()
        self.refresh_recovery()
        self._tick()

    def switch_to(self, name: str) -> None:
        names = tuple(self.nav_buttons)
        if name not in self.nav_buttons:
            raise ValueError("Unknown screen")
        self.stack.setCurrentIndex(names.index(name))
        for label, button in self.nav_buttons.items():
            button.setChecked(label == name)
        if name == "Meetings":
            self.meetings_page.refresh_models()
            self.meetings_page.minutes_panel.refresh_providers()
            self.meetings_page.refresh()

    def refresh_devices(self) -> None:
        try:
            devices = self.controller.capture.list_devices()
        except Exception as exc:
            QMessageBox.warning(self, "Cannot list devices", str(exc))
            return
        for source, box in (("system", self.system_box), ("microphone", self.microphone_box)):
            previous = box.currentData()
            box.clear()
            for item in devices[source]:
                box.addItem(item.name, item.id)
            if previous:
                index = box.findData(previous)
                if index >= 0:
                    box.setCurrentIndex(index)

    def refresh_recovery(self) -> None:
        self.recovery_list.clear()
        for meeting in self.controller.store.incomplete():
            label = f"{meeting['created_at'][:19]} · {meeting['id'][:8]}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, meeting["id"])
            self.recovery_list.addItem(item)

    def _on_record(self) -> None:
        if not self.record_button.isEnabled():
            return
        try:
            self.controller.start(self.system_box.currentData(), self.microphone_box.currentData())
        except Exception as exc:
            QMessageBox.warning(self, "Cannot record", str(exc))
        self._tick()

    def _on_pause(self) -> None:
        try:
            state = self.controller.snapshot().state
            if state == State.RECORDING:
                self.controller.pause()
            elif state == State.PAUSED:
                self.controller.resume()
        except Exception as exc:
            QMessageBox.warning(self, "Cannot pause or resume", str(exc))
        self._tick()

    def _on_stop(self) -> None:
        if self.controller.snapshot().state not in (State.STARTING, State.RECORDING, State.PAUSED):
            return
        try:
            self.controller.stop()
        except Exception as exc:
            QMessageBox.warning(self, "Cannot stop", str(exc))
        self._tick()

    def _on_recover(self) -> None:
        item = self.recovery_list.currentItem()
        if item is None:
            return
        try:
            self.controller.recover(item.data(Qt.UserRole))
        except Exception as exc:
            QMessageBox.warning(self, "Cannot recover", str(exc))
        self._tick()

    def _tick(self) -> None:
        snapshot = self.controller.snapshot()
        self.status_label.setText(STATUS_TEXT[snapshot.state])
        self.status_label.setStyleSheet(
            "font-size: 17px; font-weight: 600; color: #c62828"
            if snapshot.state == State.RECORDING
            else "font-size: 17px; font-weight: 600"
        )
        total = int(snapshot.seconds)
        self.timer_label.setText(f"{total // 3600:02d}:{total // 60 % 60:02d}:{total % 60:02d}")
        active = snapshot.state in (State.STARTING, State.RECORDING, State.PAUSED, State.FINALIZING)
        self.record_button.setEnabled(
            not active and self.system_box.count() > 0 and self.microphone_box.count() > 0
        )
        self.system_box.setEnabled(not active)
        self.microphone_box.setEnabled(not active)
        self.refresh_button.setEnabled(not active)
        self.pause_button.setEnabled(snapshot.state in (State.RECORDING, State.PAUSED))
        self.pause_button.setText("Resume" if snapshot.state == State.PAUSED else "Pause")
        self.stop_button.setEnabled(
            snapshot.state in (State.STARTING, State.RECORDING, State.PAUSED)
        )
        self.recover_button.setEnabled(not active and self.recovery_list.currentItem() is not None)
        if snapshot.recording:
            self.result_label.setText(f"Playback file: {snapshot.recording}")
            if snapshot.skipped_chunks:
                self.result_label.setText(
                    self.result_label.text()
                    + f"\nSkipped {len(snapshot.skipped_chunks)} corrupt audio chunks."
                )
        if snapshot.error and snapshot.error != self._last_error:
            self._last_error = snapshot.error
            self.refresh_recovery()
            QMessageBox.warning(self, "Recording error", snapshot.error)
        if snapshot.state == State.COMPLETED and self._last_state != State.COMPLETED:
            self.refresh_recovery()
        self._last_state = snapshot.state
        if self._close_requested and not active:
            self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        state = self.controller.snapshot().state
        if state in (State.STARTING, State.RECORDING, State.PAUSED):
            answer = QMessageBox.question(
                self, "Close fahmm", "Stop recording, save the file, and close the app?"
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self._close_requested = True
            self.controller.stop()
            event.ignore()
            return
        if state == State.FINALIZING:
            self._close_requested = True
            event.ignore()
            return
        event.accept()
