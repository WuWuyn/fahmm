"""Optional provider configuration within the existing Settings screen."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from fahmm.providers import ProviderProfiles


class SettingsPage(QWidget):
    def __init__(self, profiles: ProviderProfiles, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profiles = profiles
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Settings · Optional minutes provider"))
        notice = QLabel(
            "A provider may charge for minutes generation. Meeting content is sent only after "
            "you permit cloud use for that meeting and confirm each request."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.profile_box = QComboBox()
        self.profile_box.currentIndexChanged.connect(self._load_selection)
        layout.addWidget(self.profile_box)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://provider.example/v1")
        self.model_edit = QLineEdit()
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 600)
        self.timeout_spin.setValue(60)
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("Leave blank to keep the saved key")
        form.addRow("Name:", self.name_edit)
        form.addRow("Base URL:", self.url_edit)
        form.addRow("Model ID:", self.model_edit)
        form.addRow("Timeout (seconds):", self.timeout_spin)
        form.addRow("API key (optional):", self.key_edit)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.save_button = QPushButton("Save profile")
        self.delete_button = QPushButton("Delete profile")
        self.clear_key_button = QPushButton("Remove stored API key")
        self.save_button.clicked.connect(self.save_profile)
        self.delete_button.clicked.connect(self.delete_selected)
        self.clear_key_button.clicked.connect(self.remove_key)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.delete_button)
        buttons.addWidget(self.clear_key_button)
        layout.addLayout(buttons)
        self.status_label = QLabel()
        layout.addWidget(self.status_label)
        layout.addStretch()
        self.refresh()

    def refresh(self, selected_id: str | None = None) -> None:
        self.profile_box.blockSignals(True)
        self.profile_box.clear()
        self.profile_box.addItem("New provider…", None)
        for profile in self.profiles.list_profiles():
            self.profile_box.addItem(profile.name, profile.id)
        if selected_id:
            index = self.profile_box.findData(selected_id)
            if index >= 0:
                self.profile_box.setCurrentIndex(index)
        self.profile_box.blockSignals(False)
        self._load_selection()

    def _load_selection(self) -> None:
        profile_id = self.profile_box.currentData()
        if profile_id:
            profile = self.profiles.get(profile_id)
            self.name_edit.setText(profile.name)
            self.url_edit.setText(profile.base_url)
            self.model_edit.setText(profile.model_id)
            self.timeout_spin.setValue(int(profile.timeout_seconds))
        else:
            self.name_edit.clear()
            self.url_edit.clear()
            self.model_edit.clear()
            self.timeout_spin.setValue(60)
        self.key_edit.clear()
        self.delete_button.setEnabled(bool(profile_id))
        self.clear_key_button.setEnabled(bool(profile_id))

    def save_profile(self) -> None:
        try:
            profile = self.profiles.save(
                self.name_edit.text(), self.url_edit.text(), self.model_edit.text(),
                self.timeout_spin.value(), profile_id=self.profile_box.currentData(),
                api_key=self.key_edit.text() or None,
            )
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            self.status_label.setText(f"Could not save profile: {exc}")
            return
        self.refresh(profile.id)
        self.status_label.setText("Provider profile saved locally")

    def remove_key(self) -> None:
        profile_id = self.profile_box.currentData()
        if not profile_id:
            return
        try:
            profile = self.profiles.get(profile_id)
            self.profiles.save(profile.name, profile.base_url, profile.model_id,
                               profile.timeout_seconds, profile_id=profile.id, api_key="")
        except (OSError, ValueError, RuntimeError) as exc:
            self.status_label.setText(f"Could not remove key: {exc}")
            return
        self.key_edit.clear()
        self.status_label.setText("Stored API key removed")

    def delete_selected(self) -> None:
        profile_id = self.profile_box.currentData()
        if not profile_id:
            return
        answer = QMessageBox.question(self, "Delete provider", "Delete this provider profile and key?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.profiles.delete(profile_id)
        except (OSError, ValueError, RuntimeError) as exc:
            self.status_label.setText(f"Could not delete profile: {exc}")
            return
        self.refresh()
        self.status_label.setText("Provider profile deleted")
