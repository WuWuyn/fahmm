"""PyInstaller entry point for the Tauri Python sidecar."""

from multiprocessing import freeze_support

if __name__ == "__main__":
    freeze_support()
    from fahmm.bridge.__main__ import main

    raise SystemExit(main())
