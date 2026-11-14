import os

from PySide6.QtWidgets import QApplication, QMessageBox
from test_providers import FakeCredentials

from fahmm.providers import ProviderProfiles
from legacy.qt.settings_page import SettingsPage

os.environ["QT_QPA_PLATFORM"] = "offscreen"
_APP_HOLDER = []


def test_settings_create_edit_remove_key_delete_and_reopen(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    _APP_HOLDER.append(app)
    secrets = FakeCredentials()
    path = tmp_path / "providers.json"
    page = SettingsPage(ProviderProfiles(path, secrets))
    page.show()
    page.name_edit.setText("Example")
    page.url_edit.setText("https://example.org/v1")
    page.model_edit.setText("example-model")
    page.timeout_spin.setValue(20)
    page.key_edit.setText("test-secret")
    assert page.key_edit.echoMode() == page.key_edit.EchoMode.Password
    page.save_button.click()
    profile_id = page.profile_box.currentData()
    assert profile_id
    assert secrets.get_key(profile_id) == "test-secret"
    assert "test-secret" not in path.read_text(encoding="utf-8")
    page.name_edit.setText("Updated")
    page.save_button.click()
    assert page.profiles.get(profile_id).name == "Updated"
    reopened = SettingsPage(ProviderProfiles(path, secrets))
    index = reopened.profile_box.findData(profile_id)
    reopened.profile_box.setCurrentIndex(index)
    assert reopened.name_edit.text() == "Updated"
    assert reopened.key_edit.text() == ""
    reopened.clear_key_button.click()
    assert secrets.get_key(profile_id) is None
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    reopened.delete_button.click()
    assert ProviderProfiles(path, secrets).list_profiles() == []
    page.close()
    reopened.close()
    app.processEvents()
