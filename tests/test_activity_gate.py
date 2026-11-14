"""Deletion gate covers active meeting writers and a second app process."""

import os
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest
from test_asr_jobs import hanging_worker, prepared_job
from test_controller import FakeCapture, await_state
from test_minutes_store import make_meeting_with_run

from fahmm.cloud_minutes import CloudMinutesService
from fahmm.controller import SessionController, State
from fahmm.offline_minutes import OfflineMinutesService
from fahmm.providers import ProviderProfiles
from fahmm.storage import MeetingStore


def test_recording_and_recovery_block_direct_delete(tmp_path, monkeypatch):
    store = MeetingStore(tmp_path / "meetings")
    controller = SessionController(FakeCapture(), store)
    meeting_id = controller.start("speaker", "mic")
    await_state(controller, State.RECORDING)
    with pytest.raises(RuntimeError, match="recording"):
        store.begin_deletion(meeting_id)
    controller.stop()
    controller.wait(5)
    assert store.active_activities(meeting_id) == ()

    entered, release = threading.Event(), threading.Event()

    def delayed_finalize(_meeting_id):
        entered.set()
        assert release.wait(5)
        return original_finalize(_meeting_id)

    original_finalize = store.finalize
    monkeypatch.setattr(store, "finalize", delayed_finalize)
    controller.recover(meeting_id)
    try:
        assert entered.wait(3)
        with pytest.raises(RuntimeError, match="recovery"):
            store.begin_deletion(meeting_id)
    finally:
        release.set()
    deadline = time.monotonic() + 5
    while store.active_activities(meeting_id) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert store.active_activities(meeting_id) == ()
    store.begin_deletion(meeting_id)
    store.end_deletion(meeting_id)


def test_asr_and_job_start_race_block_delete(tmp_path):
    jobs, meeting_id, model_id, _ = prepared_job(tmp_path, hanging_worker)
    store = jobs.store
    jobs.start(meeting_id, model_id)
    with pytest.raises(RuntimeError, match="asr"):
        store.begin_deletion(meeting_id)
    jobs.cancel()
    jobs.wait(10)
    assert store.active_activities(meeting_id) == ()
    store.begin_deletion(meeting_id)
    try:
        with pytest.raises(RuntimeError, match="being deleted"):
            jobs.start(meeting_id, model_id)
    finally:
        store.end_deletion(meeting_id)


def test_offline_and_provider_generation_hold_activity(tmp_path, monkeypatch):
    store, meeting_id, _ = make_meeting_with_run(tmp_path / "meetings")
    offline = OfflineMinutesService(store)
    profiles = ProviderProfiles(tmp_path / "profiles.json")
    cloud = CloudMinutesService(store, profiles)

    def exercise(service, kind, call):
        entered, release = threading.Event(), threading.Event()

        def wait_for_release(*_args):
            entered.set()
            assert release.wait(5)
            return "done"

        monkeypatch.setattr(service, "_generate", wait_for_release)
        result = []
        thread = threading.Thread(target=lambda: result.append(call()))
        thread.start()
        try:
            assert entered.wait(3)
            with pytest.raises(RuntimeError, match=kind):
                store.begin_deletion(meeting_id)
        finally:
            release.set()
            thread.join(5)
        assert result == ["done"]
        assert store.active_activities(meeting_id) == ()

    exercise(offline, "offline_minutes", lambda: offline.generate(meeting_id))
    snapshot = SimpleNamespace(meeting_id=meeting_id)
    exercise(cloud, "provider_generation", lambda: cloud.generate(snapshot, None))


def test_direct_provider_send_blocks_delete(tmp_path):
    store, meeting_id, _ = make_meeting_with_run(tmp_path / "meetings")
    store.set_privacy_mode(meeting_id, "cloud_permitted")
    store.begin_cloud_send(meeting_id)
    try:
        with pytest.raises(RuntimeError, match="provider_send"):
            store.begin_deletion(meeting_id)
    finally:
        store.end_cloud_send(meeting_id)
    store.begin_deletion(meeting_id)
    store.end_deletion(meeting_id)


@pytest.mark.skipif(os.name != "nt", reason="Windows file locking and app smoke only")
def test_second_app_instance_is_rejected_then_crash_releases_lock(tmp_path):
    data_root = tmp_path / "local" / "fahmm"
    store = MeetingStore(data_root / "meetings")
    meeting_id = store.create({})
    env = {**os.environ, "LOCALAPPDATA": str(tmp_path / "local")}
    holder_code = (
        "from pathlib import Path; from fahmm.single_instance import SingleInstanceLock; "
        "import sys,time; lock=SingleInstanceLock(Path(sys.argv[1])); "
        "lock.acquire(); print('ready',flush=True); time.sleep(30)"
    )
    holder = subprocess.Popen(
        [sys.executable, "-c", holder_code, str(data_root)], env=env,
        stdout=subprocess.PIPE, text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "ready"
        second = subprocess.run(
            [sys.executable, "-m", "fahmm.bridge"], env=env,
            input="", capture_output=True, text=True, timeout=15, check=False,
        )
        assert second.returncode == 2
    finally:
        holder.kill()
        holder.wait(5)
        holder.stdout.close()
    restarted = subprocess.run(
        [sys.executable, "-m", "fahmm.bridge"], env=env,
        input="", capture_output=True, text=True, timeout=15, check=False,
    )
    assert restarted.returncode == 0, restarted.stderr
    assert store.metadata(meeting_id)["id"] == meeting_id
