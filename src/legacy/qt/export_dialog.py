"""User-selected local export destination and explicit replacement decision."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget


def choose_export_target(
    parent: QWidget, filename: str, filter_text: str
) -> tuple[Path, bool] | None:
    chosen, _ = QFileDialog.getSaveFileName(
        parent, "Export meeting document", filename, filter_text
    )
    if not chosen:
        return None
    destination = Path(chosen)
    if destination.exists():
        answer = QMessageBox.question(
            parent,
            "Replace existing file?",
            f"Replace the existing file at {destination}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return None
        return destination, True
    return destination, False
