use serde_json::json;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;
use tauri::http::{Request, Response, StatusCode};

use crate::call_backend;

const MAX_CHUNK: u64 = 8 * 1024 * 1024;

fn rejected(status: StatusCode) -> Response<Vec<u8>> {
    Response::builder().status(status).body(Vec::new()).unwrap()
}

fn parse_range(header: Option<&str>, size: u64) -> Option<(u64, u64, bool)> {
    if size == 0 { return None; }
    let Some(header) = header else {
        return Some((0, (size - 1).min(MAX_CHUNK - 1), size > MAX_CHUNK));
    };
    let bytes = header.strip_prefix("bytes=")?;
    if bytes.contains(',') { return None; }
    let (start, end) = bytes.split_once('-')?;
    let (start, end) = if start.is_empty() {
        let suffix: u64 = end.parse().ok()?;
        if suffix == 0 { return None; }
        (size.saturating_sub(suffix), size - 1)
    } else {
        let start: u64 = start.parse().ok()?;
        if start >= size { return None; }
        let end = if end.is_empty() { size - 1 } else { end.parse::<u64>().ok()?.min(size - 1) };
        if end < start { return None; }
        (start, end)
    };
    Some((start, end.min(start.saturating_add(MAX_CHUNK - 1)), true))
}

fn file_response(path: &Path, content_type: &str, range: Option<&str>, head: bool,
                 origin: Option<&str>) -> Response<Vec<u8>> {
    let Ok(mut file) = File::open(path) else { return rejected(StatusCode::NOT_FOUND) };
    let Ok(size) = file.metadata().map(|item| item.len()) else { return rejected(StatusCode::NOT_FOUND) };
    let Some((start, end, partial)) = parse_range(range, size) else {
        return Response::builder().status(StatusCode::RANGE_NOT_SATISFIABLE)
            .header("Content-Range", format!("bytes */{size}"))
            .body(Vec::new()).unwrap()
    };
    let length = end - start + 1;
    if file.seek(SeekFrom::Start(start)).is_err() { return rejected(StatusCode::NOT_FOUND) }
    let mut body = if head { Vec::new() } else { vec![0; length as usize] };
    if !head && file.read_exact(&mut body).is_err() { return rejected(StatusCode::NOT_FOUND) }
    let mut builder = Response::builder()
        .status(if partial { StatusCode::PARTIAL_CONTENT } else { StatusCode::OK })
        .header("Content-Type", content_type)
        .header("Accept-Ranges", "bytes")
        .header("Content-Length", length.to_string())
        .header("Cache-Control", "no-store")
        .header("X-Content-Type-Options", "nosniff");
    if partial { builder = builder.header("Content-Range", format!("bytes {start}-{end}/{size}")); }
    if let Some(origin @ ("http://localhost:1420" | "http://tauri.localhost" | "tauri://localhost")) = origin {
        builder = builder.header("Access-Control-Allow-Origin", origin);
    }
    builder.body(body).unwrap()
}

pub fn handle(app: &tauri::AppHandle, request: Request<Vec<u8>>) -> Response<Vec<u8>> {
    if request.method() != "GET" && request.method() != "HEAD" {
        return rejected(StatusCode::METHOD_NOT_ALLOWED);
    }
    let parts: Vec<_> = request.uri().path().split('/').collect();
    if parts.len() != 4 || parts[0] != "" || parts[1] != "media"
        || parts[2].len() != 32 || !parts[2].bytes().all(|byte| byte.is_ascii_hexdigit())
        || parts[3].len() < 32 || !parts[3].bytes().all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_') {
        return rejected(StatusCode::NOT_FOUND);
    }
    let Ok(result) = call_backend(app, "media.resolve", json!({"meetingId": parts[2], "ticket": parts[3]})) else {
        return rejected(StatusCode::NOT_FOUND)
    };
    let (Some(path), Some(content_type)) = (result["nativePath"].as_str(), result["contentType"].as_str()) else {
        return rejected(StatusCode::NOT_FOUND)
    };
    file_response(Path::new(path), content_type,
        request.headers().get("Range").and_then(|value| value.to_str().ok()),
        request.method() == "HEAD",
        request.headers().get("Origin").and_then(|value| value.to_str().ok()))
}

#[cfg(test)]
mod tests {
    use super::{file_response, parse_range};
    use std::fs;
    use tauri::http::StatusCode;

    #[test]
    fn bounded_ranges_and_seek() {
        assert_eq!(parse_range(Some("bytes=2-4"), 10), Some((2, 4, true)));
        assert_eq!(parse_range(Some("bytes=-3"), 10), Some((7, 9, true)));
        assert_eq!(parse_range(Some("bytes=11-"), 10), None);
        assert_eq!(parse_range(Some("bytes=0-"), 10), Some((0, 9, true)));
        assert_eq!(parse_range(None, 10), Some((0, 9, false)));
        let path = std::env::temp_dir().join(format!("fahmm-range-{}", std::process::id()));
        fs::write(&path, b"0123456789").unwrap();
        let response = file_response(&path, "audio/wav", Some("bytes=2-4"), false, None);
        assert_eq!(response.status(), StatusCode::PARTIAL_CONTENT);
        assert_eq!(response.body(), b"234");
        assert_eq!(response.headers()["Content-Range"], "bytes 2-4/10");
        fs::remove_file(path).unwrap();
    }
}
