"""Run a synthetic report through the frozen fahmm sidecar and local Ollama."""
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
SIDECAR = ROOT / 'desktop/src-tauri/binaries/fahmm-sidecar-x86_64-pc-windows-msvc.exe'


def main():
    work = ROOT / '.build' / ('report-smoke-' + uuid.uuid4().hex[:12])
    work.mkdir(parents=True)
    output = work / 'output'
    output.mkdir()
    env = dict(os.environ, LOCALAPPDATA=str(work / 'appdata'), TEMP=str(work), TMP=str(work))
    process = subprocess.Popen([str(SIDECAR)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, encoding='utf-8', env=env)
    number = 0

    def call(op, params):
        nonlocal number
        number += 1
        frame = {'v': 1, 'kind': 'request', 'id': str(number), 'op': op, 'params': params}
        process.stdin.write(json.dumps(frame, ensure_ascii=False) + '\n')
        process.stdin.flush()
        result = json.loads(process.stdout.readline())
        if result.get('kind') != 'response':
            raise RuntimeError(f'{op}: {result}')
        return result['result']

    try:
        call('session.hello', {'versions': [1]})
        models = call('report.models', {})['models']
        print('Models:', [(m['id'], m['installed']) for m in models], flush=True)
        source = ROOT / 'ReportAI_Local_Test/tests/data/vietnamese.txt'
        call('report.addFile', {'nativePath': str(source)})
        call('report.start', {'model': 'qwen3.5:2b-q4_K_M', 'form': ''})
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            state = call('report.status', {})['report']
            if state['state'] != 'running':
                break
            time.sleep(2)
        else:
            raise TimeoutError('Report generation timed out')
        if state['state'] != 'completed' or not state['facts']:
            raise RuntimeError(f"Report failed: {state['detail']}\n{state['preview']}")
        call('report.export', {'nativePath': str(output)})
        workbook = load_workbook(output / 'Bang_Tong_Hop.xlsx', read_only=True)
        assert workbook.sheetnames == ['Tổng hợp', 'Chi tiết nguồn', 'Cần kiểm tra']
        print(json.dumps({'state': state['state'], 'facts': state['facts'],
                          'warnings': state['warnings'], 'metrics': state['metrics'],
                          'output': str(output)}, ensure_ascii=False), flush=True)
    finally:
        process.stdin.close()
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired: process.terminate(); process.wait(timeout=10)


if __name__ == '__main__':
    main()
