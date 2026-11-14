"""Smoke the source-mode sidecar through its real standard streams."""

import json
import os
import subprocess
import sys


def test_sidecar_handshake_and_health(tmp_path):
    env = {**os.environ, "LOCALAPPDATA": str(tmp_path)}
    process = subprocess.Popen(
        [sys.executable, "-m", "fahmm.bridge"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    requests = (
        {"v": 1, "kind": "request", "id": "hello", "op": "session.hello",
         "params": {"versions": [1]}},
        {"v": 1, "kind": "request", "id": "health", "op": "system.health", "params": {}},
    )
    payload = b"".join((json.dumps(request) + "\n").encode() for request in requests)
    output, errors = process.communicate(input=payload, timeout=15)
    assert process.returncode == 0, errors.decode()
    responses = [json.loads(line) for line in output.splitlines()]
    assert [response["id"] for response in responses] == ["hello", "health"]
    assert all(response["kind"] == "response" for response in responses)
    assert responses[-1]["result"] == {"status": "ready"}


def test_sidecar_error_redacts_provider_request(tmp_path):
    env = {**os.environ, "LOCALAPPDATA": str(tmp_path)}
    process = subprocess.Popen(
        [sys.executable, "-m", "fahmm.bridge"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    requests = (
        {"v": 1, "kind": "request", "id": "hello", "op": "session.hello",
         "params": {"versions": [1]}},
        {"v": 1, "kind": "request", "id": "bad", "op": "provider.save",
         "params": {"name": "Secret", "baseUrl": "https://user:secret@example.org/v1",
                    "modelId": "model", "timeoutSeconds": 30, "profileId": None,
                    "apiKey": "private-api-key"}},
    )
    payload = b"".join((json.dumps(request) + "\n").encode() for request in requests)
    output, errors = process.communicate(input=payload, timeout=15)
    responses = [json.loads(line) for line in output.splitlines()]
    assert responses[-1]["kind"] == "error"
    assert responses[-1]["error"]["code"] == "OPERATION_FAILED"
    assert b"private-api-key" not in output + errors
    assert b"user:secret" not in output + errors
