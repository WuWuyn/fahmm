# Earlier Qt interface

This directory preserves the earlier PySide6 screens for regression tests and the previous portable build. The supported desktop development entry is `desktop/` with Tauri. Install the optional `legacy-qt` extra only when running historical Qt tests or rollback checks:

```powershell
uv run --locked --extra legacy-qt pytest -q
uv run --locked --extra legacy-qt python scripts/verify_qt_rollback.py
```

The normal Python sidecar and new Windows bundle do not import these modules.
