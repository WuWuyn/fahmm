import os
import time
import uuid

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from fahmm.models import InstalledModel
from legacy.qt.models_page import ModelsPage

os.environ["QT_QPA_PLATFORM"] = "offscreen"


class FakeManager:
    def __init__(self, root):
        self.root = root
        self.items = []
        self.selected_id = None

    def installed(self):
        return list(self.items)

    def selected(self):
        return next((item for item in self.items if item.id == self.selected_id), None)

    def download(self, repository, *, progress):
        if repository == "bad/repo":
            raise ValueError("Incompatible repository")
        progress("Downloading model files", 1, 2)
        model = InstalledModel(uuid.uuid4().hex, repository, "Systran", "MIT", "a" * 40,
                               148_000_000, self.root / "model")
        self.items.append(model)
        self.selected_id = model.id
        return model

    def select(self, model_id):
        self.selected_id = model_id
        return self.selected()

    def delete(self, model_id):
        self.items = [item for item in self.items if item.id != model_id]
        self.selected_id = None


def wait_until(predicate):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        QTest.qWait(20)
        if predicate():
            return
    raise AssertionError("Timed out waiting for Models screen")


def test_models_screen_download_select_delete_and_error(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app
    manager = FakeManager(tmp_path)
    warnings = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    page = ModelsPage(manager)
    page.show()
    assert "No meeting audio" in page.findChildren(type(page.details))[1].text()
    assert page.choice_box.count() == 5
    page.download_button.click()
    wait_until(lambda: page.installed_list.count() == 1)
    assert "Installed" in page.status_label.text()
    page.installed_list.setCurrentRow(0)
    assert page.select_button.isEnabled()
    page.select_button.click()
    assert "offline" in page.status_label.text()
    page.delete_button.click()
    assert page.installed_list.count() == 0
    page.choice_box.setCurrentIndex(4)
    page.custom_repo.setText("bad/repo")
    page.download_button.click()
    wait_until(lambda: bool(warnings))
    assert "Incompatible repository" in warnings[0]
    page.close()
