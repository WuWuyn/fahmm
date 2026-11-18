pub mod protocol;
pub mod sidecar;
pub mod media;

use serde_json::{Value, json};
use sidecar::{SidecarSupervisor, application_spec};
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Duration;
use tauri::Manager;
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons};

struct BackendState(Mutex<Option<SidecarSupervisor>>);

fn call_backend(app: &tauri::AppHandle, operation: &str, params: Value) -> Result<Value, String> {
    let state = app.state::<BackendState>();
    let guard = state.0.lock().map_err(|_| "BACKEND_UNAVAILABLE")?;
    let backend = guard.as_ref().ok_or("BACKEND_UNAVAILABLE")?;
    backend.call(operation, params, Duration::from_secs(600))
}

fn demo_audio_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    // Optional local fixture: keep the hour-long synthetic recording out of release bundles.
    app.path().local_data_dir().map(|base| base.join("fahmm").join("demo")
        .join("retail-requirements-60m.mp3"))
        .map_err(|_| "DEMO_AUDIO_UNAVAILABLE".to_string())
}

#[tauri::command]
fn bridge_demo_status(app: tauri::AppHandle) -> Result<Value, String> {
    let path = demo_audio_path(&app)?;
    let available = path.metadata().is_ok_and(|metadata| metadata.is_file() && metadata.len() > 0);
    Ok(json!({"available": available}))
}

#[tauri::command]
async fn bridge_import_demo(app: tauri::AppHandle) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let path = demo_audio_path(&app)?;
        if !path.metadata().is_ok_and(|metadata| metadata.is_file() && metadata.len() > 0) {
            return Err("DEMO_AUDIO_UNAVAILABLE".into());
        }
        let path = path.to_str().ok_or("DEMO_AUDIO_UNAVAILABLE")?;
        let result = call_backend(&app, "meeting.import", json!({"nativePath": path}))?;
        if let Some(meeting_id) = result["meetingId"].as_str() {
            let _ = call_backend(&app, "meeting.rename", json!({
                "meetingId": meeting_id,
                "name": "Họp mẫu — Yêu cầu hệ thống bán hàng (60 phút)"
            }));
        }
        Ok(result)
    }).await.map_err(|_| "BACKEND_UNAVAILABLE".to_string())?
}

fn webview_operation_allowed(operation: &str) -> bool {
    !matches!(operation, "meeting.import" | "export.writeMinutes" | "export.writeMinutesDocx" | "export.writeTranscript" | "export.writeTranscriptPlain" | "export.writeAudio" | "media.resolve")
}

#[tauri::command]
async fn bridge_call(app: tauri::AppHandle, operation: String, params: Value) -> Result<Value, String> {
    if !webview_operation_allowed(&operation) {
        return Err("INVALID_REQUEST".into());
    }
    tauri::async_runtime::spawn_blocking(move || call_backend(&app, &operation, params))
        .await.map_err(|_| "BACKEND_UNAVAILABLE".to_string())?
}

#[cfg(test)]
mod host_tests {
    use super::webview_operation_allowed;

    #[test]
    fn paths_require_native_dialog_commands() {
        assert!(!webview_operation_allowed("meeting.import"));
        assert!(!webview_operation_allowed("export.writeMinutes"));
        assert!(!webview_operation_allowed("export.writeMinutesDocx"));
        assert!(!webview_operation_allowed("export.writeTranscript"));
        assert!(!webview_operation_allowed("export.writeTranscriptPlain"));
        assert!(!webview_operation_allowed("export.writeAudio"));
        assert!(!webview_operation_allowed("media.resolve"));
        assert!(webview_operation_allowed("meeting.list"));
    }
}

#[tauri::command]
async fn bridge_import(app: tauri::AppHandle) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let selection = app.dialog().file()
            .add_filter("Audio", &["wav", "mp3", "m4a", "flac"])
            .blocking_pick_file();
        let Some(selection) = selection else { return Ok(json!({"cancelled": true})) };
        let path = selection.into_path().map_err(|_| "INVALID_REQUEST")?;
        let path = path.to_str().ok_or("INVALID_REQUEST")?;
        call_backend(&app, "meeting.import", json!({"nativePath": path}))
    }).await.map_err(|_| "BACKEND_UNAVAILABLE".to_string())?
}

#[tauri::command]
async fn bridge_export(app: tauri::AppHandle, meeting_id: String, document_id: String,
                       document_kind: String) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let (operation, id_key, file_name, extension) = match document_kind.as_str() {
            "minutes" => ("export.writeMinutes", "versionId", "minutes.md", "md"),
            "minutesWord" => ("export.writeMinutesDocx", "versionId", "minutes.docx", "docx"),
            "transcript" => ("export.writeTranscript", "runId", "transcript.txt", "txt"),
            "transcriptPlain" => ("export.writeTranscriptPlain", "runId", "transcript.txt", "txt"),
            _ => return Err("INVALID_REQUEST".into()),
        };
        let filter_name = if document_kind == "minutesWord" { "Word document" } else { "Text document" };
        let selection = app.dialog().file().set_file_name(file_name)
            .add_filter(filter_name, &[extension]).blocking_save_file();
        let Some(selection) = selection else { return Ok(json!({"cancelled": true})) };
        let path = selection.into_path().map_err(|_| "INVALID_REQUEST")?;
        let overwrite = if path.exists() {
            app.dialog().message("Replace the existing export file?")
                .title("Confirm overwrite").buttons(MessageDialogButtons::OkCancel)
                .blocking_show()
        } else { false };
        if path.exists() && !overwrite { return Ok(json!({"cancelled": true})) }
        let path = path.to_str().ok_or("INVALID_REQUEST")?;
        let mut params = json!({"meetingId": meeting_id, "nativePath": path, "overwrite": overwrite});
        params[id_key] = json!(document_id);
        call_backend(&app, operation, params)
    }).await.map_err(|_| "BACKEND_UNAVAILABLE".to_string())?
}

#[tauri::command]
async fn bridge_export_audio(app: tauri::AppHandle, meeting_id: String) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let info = call_backend(&app, "export.audioInfo", json!({"meetingId": meeting_id}))?;
        let extension = info["extension"].as_str().ok_or("INVALID_REQUEST")?;
        if !matches!(extension, "wav" | "mp3" | "m4a" | "flac") {
            return Err("INVALID_REQUEST".into());
        }
        let file_name = info["fileName"].as_str().ok_or("INVALID_REQUEST")?;
        let selection = app.dialog().file().set_file_name(file_name)
            .add_filter("Audio recording", &[extension]).blocking_save_file();
        let Some(selection) = selection else { return Ok(json!({"cancelled": true})) };
        let path = selection.into_path().map_err(|_| "INVALID_REQUEST")?;
        let overwrite = if path.exists() {
            app.dialog().message("Replace the existing export file?")
                .title("Confirm overwrite").buttons(MessageDialogButtons::OkCancel)
                .blocking_show()
        } else { false };
        if path.exists() && !overwrite { return Ok(json!({"cancelled": true})) }
        let path = path.to_str().ok_or("INVALID_REQUEST")?;
        call_backend(&app, "export.writeAudio", json!({
            "meetingId": meeting_id, "nativePath": path, "overwrite": overwrite,
        }))
    }).await.map_err(|_| "BACKEND_UNAVAILABLE".to_string())?
}

#[tauri::command]
fn bridge_status(state: tauri::State<'_, BackendState>) -> Result<Value, String> {
    // A long provider call owns the supervisor lock. Keep health checks responsive
    // while that authorized operation is in progress.
    let guard = match state.0.try_lock() {
        Ok(guard) => guard,
        Err(std::sync::TryLockError::WouldBlock) => return Ok(json!({"status": "busy"})),
        Err(std::sync::TryLockError::Poisoned(_)) => return Err("BACKEND_UNAVAILABLE".into()),
    };
    let backend = guard.as_ref().ok_or("BACKEND_UNAVAILABLE")?;
    backend.call("system.health", json!({}), Duration::from_secs(3))
}

#[tauri::command]
fn bridge_restart(state: tauri::State<'_, BackendState>) -> Result<Value, String> {
    let mut guard = state.0.lock().map_err(|_| "BACKEND_UNAVAILABLE")?;
    match guard.as_mut() {
        Some(backend) => backend.restart()?,
        None => *guard = Some(SidecarSupervisor::start(application_spec()?)?),
    }
    Ok(json!({"state": "ready"}))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let backend = application_spec().and_then(SidecarSupervisor::start).ok();
    tauri::Builder::default()
        .register_uri_scheme_protocol("fahmm", |context, request| {
            if context.webview_label() != "main" {
                return tauri::http::Response::builder().status(404)
                    .body(Vec::new()).unwrap();
            }
            media::handle(context.app_handle(), request)
        })
        .plugin(tauri_plugin_dialog::init())
        .manage(BackendState(Mutex::new(backend)))
        .invoke_handler(tauri::generate_handler![bridge_status, bridge_restart,
            bridge_call, bridge_import, bridge_demo_status, bridge_import_demo, bridge_export,
            bridge_export_audio])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
