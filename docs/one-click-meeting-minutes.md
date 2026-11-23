# One-click meeting minutes

## Desktop journey

1. Record or import a meeting, then run local transcription. Save any transcript corrections you make.
2. Open the meeting's **Minutes / Biên bản** tab. Press **Generate meeting minutes / Tạo biên bản**. No meeting type, template, provider profile, or prompt is required.
3. If an Ollama language model is selected and installed, it writes a source-linked draft in the DENSO meeting-minutes form. It fills the Dashboard, SQDCM, color-alert, 3D-model, data, project-action, and partner-support tables only from cited transcript passages. Long transcripts are processed in bounded chunks, followed by a whole-meeting summary. If Ollama cuts off a JSON response at its output limit, the affected chunk is split and retried while retaining the original transcript citation IDs. Missing facts remain `Chưa rõ`. Progress appears while the background job runs. **Create fast extractive draft / Tạo biên bản trích xuất nhanh** is also available when Ollama is ready: it uses the existing local extraction path without calling the model. If Ollama is not ready, the primary button creates that extractive draft. Both modes create a new source-linked minutes version that opens automatically, with no claim review or approval step.
4. If edits are needed, open **Edit meeting details and notes / Sửa thông tin và nội dung biên bản**. Each note retains its saved source and audio seek button. Save edits as a new version; previous versions remain available in **Saved version / Phiên bản đã lưu**.
5. Use **Copy Markdown / Sao chép Markdown**, **Export MD / Xuất MD**, or **Export Word / Xuất Word** to export the selected saved version. Unsaved edits must be saved or explicitly discarded first.

The action is disabled when the active transcript is missing or contains only blank text. A failed generation leaves existing minutes intact and permits retry. Regeneration asks before discarding unsaved edits and creates a separate version.

## What the draft means

The local AI generator uses Ollama and an installed language model to write a semantic summary and categorized form entries. The executive summary lists each available category and item in a table before the detailed sections; KPI groups, project work, support requests, and any next steps appear in tables. Other meeting types also show actions and next steps in tables. The model is instructed to correct clear Vietnamese transcription errors without guessing uncertain names or figures. Each accepted entry has a transcript citation; entries with invalid citations are omitted. An invalid chunk summary is retried and, where possible, split before reporting failure; a truncated response is retried with a larger output allowance without reducing the number of form entries. Explicit named FPT tasks and DENSO support requests omitted by a small model are kept as source-linked extractive entries, so those entries may retain transcription errors. The summary must have valid citations or generation fails without replacing earlier versions. Model claims are still suggestions to check against the cited audio. Unknown participants, actual meeting date, location, owners, and deadlines stay unknown. An action suggestion is not an assigned task. The DENSO form is used for the primary general meeting action; advanced specialized meeting types retain their existing structure.

The extractive generator is available even when Ollama is ready. Its version is labeled as transcript extraction, not AI summarization. The two modes are distinguished in the saved version and Markdown export. If AI generation fails, the error remains visible; the app does not silently substitute an extractive draft. You can explicitly choose the fast draft afterward.

Ollama responses are read as a stream, so an actively generating model can take more than five minutes without being canceled by the client. Local minutes requests disable model thinking explicitly to reserve the output budget for the structured response; this does not guarantee every model or transcript will succeed. A connection that stops producing data for five minutes can still time out; the error distinguishes connection, timeout, and HTTP failures. Long recordings can take considerably longer on a busy machine.

## Set up local AI

1. Install and run [Ollama for Windows](https://ollama.com/download/windows) separately.
2. Open **Models / Mô hình** in FAHMM. Under **Local AI for meeting minutes / AI cục bộ để tạo biên bản**, download **Qwen3 4B Instruct** (about 2.5 GB) or select another Ollama model already installed. On a 4 GB VRAM machine, Ollama may also use system memory. The speech models listed below are only for transcription.
3. Return to the meeting and press **Generate meeting minutes / Tạo biên bản**. A label next to the button states which mode will run. Ollama is contacted only on `127.0.0.1:11434`; the local AI path does not use provider profiles or send transcript data to a remote API. Model download itself requires internet access.

**Advanced minutes options / Tùy chọn biên bản nâng cao** keeps specialized meeting types available. The separate optional provider flow requires a cloud-permitted privacy classification, selected and reviewed transcript segments, an exact payload preview, and confirmation for each send. The primary action never sends meeting content to a provider.

## Experimental ASR settings

The default remains CPU `int8` with beam size 5. To test CUDA and a smaller beam, set these variables in the shell that launches fahmm or its ASR worker:

```powershell
$env:FAHMM_ASR_DEVICE = 'cuda'
$env:FAHMM_ASR_COMPUTE_TYPE = 'int8_float16'
$env:FAHMM_ASR_BEAM_SIZE = '1'
```

Only `cpu`/`int8` and `cuda`/`int8_float16` combinations are accepted; the compute type defaults to the matching value when omitted. Beam size accepts integers from 1 to 10. CUDA is experimental: compatible CTranslate2 libraries, NVIDIA drivers and sufficient VRAM are required. Initialization errors are reported rather than silently switching devices. A smaller beam can change recognition quality, so compare it against the default using an authorized reference transcript. Remove the three variables and restart the app to restore defaults.

## Acceptance boundary

Automated fixtures verify versioning, citations, rejection of invalid model source IDs, export, background job status, and UI states. Model output quality on real Vietnamese recordings, audio source capture, and clean Windows package remain separate acceptance gates.
