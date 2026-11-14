import json

import numpy as np
from test_media import make_audio

from fahmm.library import MeetingLibrary
from fahmm.media import import_audio
from fahmm.storage import MeetingStore


def test_library_reopens_recorded_imported_and_legacy_meetings(tmp_path):
    root = tmp_path / "meetings"
    store = MeetingStore(root)
    recorded = store.create({"system": "speaker", "microphone": "mic"})
    store.write_chunk(recorded, "system", 0, np.ones(1000))
    store.finalize(recorded)
    source = tmp_path / "existing.mp3"
    make_audio(source)
    imported = import_audio(store, source)
    legacy = store.create({"system": "speaker", "microphone": "mic"})
    legacy_path = root / legacy / "metadata.json"
    data = store.metadata(legacy)
    for key in ("name", "source_kind", "audio_file", "privacy_mode", "processing_state"):
        data.pop(key)
    data["schema_version"] = 1
    legacy_path.write_text(json.dumps(data), encoding="utf-8")

    reopened = MeetingLibrary(MeetingStore(root))
    meetings = {item.id: item for item in reopened.list_meetings()}
    assert set(meetings) == {recorded, imported, legacy}
    assert meetings[recorded].source_kind == "recorded"
    assert meetings[imported].source_kind == "imported"
    assert meetings[legacy].privacy_mode == "restricted"
    assert reopened.audio_path(imported).exists()
    assert reopened.audio_path(recorded).exists()
    reopened.rename(imported, "Customer interview")
    assert MeetingLibrary(MeetingStore(root)).get(imported).name == "Customer interview"
    reopened.set_privacy_mode(imported, "cloud_permitted")
    assert MeetingLibrary(MeetingStore(root)).get(imported).privacy_mode == "cloud_permitted"
