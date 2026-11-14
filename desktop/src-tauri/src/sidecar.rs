use crate::protocol::{max_frame_bytes, validate_frame};
use serde_json::{Value, json};
use std::collections::HashMap;
use std::ffi::OsString;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, mpsc};
use std::thread::{self, JoinHandle};
use std::time::Duration;

type Reply = Result<Value, String>;

#[derive(Clone)]
pub struct CommandSpec {
    pub program: PathBuf,
    pub args: Vec<OsString>,
    pub cwd: PathBuf,
    pub env: Vec<(OsString, OsString)>,
}

struct Shared {
    pending: Mutex<HashMap<String, mpsc::Sender<Reply>>>,
    connected: AtomicBool,
}

pub struct SidecarSupervisor {
    spec: CommandSpec,
    versions: Vec<u32>,
    child: Mutex<Child>,
    stdin: Mutex<Option<ChildStdin>>,
    shared: Arc<Shared>,
    reader: Option<JoinHandle<()>>,
    next_id: AtomicU64,
}

impl SidecarSupervisor {
    pub fn start(spec: CommandSpec) -> Result<Self, String> {
        Self::start_with_versions(spec, vec![1])
    }

    fn start_with_versions(spec: CommandSpec, versions: Vec<u32>) -> Result<Self, String> {
        let mut process = Command::new(&spec.program);
        process.args(&spec.args).current_dir(&spec.cwd)
            .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null());
        for (key, value) in &spec.env {
            process.env(key, value);
        }
        let mut child = process.spawn().map_err(|_| "BACKEND_UNAVAILABLE".to_string())?;
        let stdin = child.stdin.take().ok_or("BACKEND_UNAVAILABLE")?;
        let stdout = child.stdout.take().ok_or("BACKEND_UNAVAILABLE")?;
        let shared = Arc::new(Shared {
            pending: Mutex::new(HashMap::new()),
            connected: AtomicBool::new(true),
        });
        let reader_shared = Arc::clone(&shared);
        let reader = thread::spawn(move || read_replies(stdout, reader_shared));
        let mut supervisor = Self {
            spec,
            versions: versions.clone(),
            child: Mutex::new(child),
            stdin: Mutex::new(Some(stdin)),
            shared,
            reader: Some(reader),
            next_id: AtomicU64::new(1),
        };
        let hello = supervisor.call("session.hello", json!({"versions": versions}), Duration::from_secs(15));
        match hello {
            Ok(value) if value["selectedVersion"] == 1 => Ok(supervisor),
            Ok(_) => {
                supervisor.stop();
                Err("UNSUPPORTED_VERSION".into())
            }
            Err(error) => {
                supervisor.stop();
                Err(error)
            }
        }
    }

    pub fn is_connected(&self) -> bool {
        self.shared.connected.load(Ordering::SeqCst)
    }

    pub fn call(&self, operation: &str, params: Value, timeout: Duration) -> Reply {
        if !self.is_connected() {
            return Err("BACKEND_UNAVAILABLE".into());
        }
        let id = format!("r-{}", self.next_id.fetch_add(1, Ordering::Relaxed));
        let request = json!({"v": 1, "kind": "request", "id": id, "op": operation, "params": params});
        let mut line = serde_json::to_vec(&request).map_err(|_| "INVALID_REQUEST")?;
        validate_frame(&line).map_err(str::to_string)?;
        line.push(b'\n');
        let (sender, receiver) = mpsc::channel();
        self.shared.pending.lock().unwrap().insert(id.clone(), sender);
        let written = {
            let mut stdin = self.stdin.lock().unwrap();
            stdin.as_mut().map(|handle| handle.write_all(&line).and_then(|_| handle.flush()))
                .unwrap_or_else(|| Err(std::io::Error::from(std::io::ErrorKind::BrokenPipe)))
        };
        if written.is_err() {
            self.shared.pending.lock().unwrap().remove(&id);
            return Err("BACKEND_UNAVAILABLE".into());
        }
        match receiver.recv_timeout(timeout) {
            Ok(reply) => reply,
            Err(_) => {
                self.shared.pending.lock().unwrap().remove(&id);
                Err("BACKEND_TIMEOUT".into())
            }
        }
    }

    pub fn restart(&mut self) -> Result<(), String> {
        let spec = self.spec.clone();
        let versions = self.versions.clone();
        self.stop();
        *self = Self::start_with_versions(spec, versions)?;
        Ok(())
    }

    pub fn stop(&mut self) {
        self.shared.connected.store(false, Ordering::SeqCst);
        if let Ok(mut stdin) = self.stdin.lock() { stdin.take(); }
        fail_pending(&self.shared, "BACKEND_UNAVAILABLE");
        if let Ok(mut child) = self.child.lock() {
            let mut exited = false;
            for _ in 0..50 {
                match child.try_wait() {
                    Ok(Some(_)) => { exited = true; break; }
                    Err(_) => break,
                    Ok(None) => thread::sleep(Duration::from_millis(100)),
                }
            }
            if !exited { let _ = child.kill(); let _ = child.wait(); }
        }
        if let Some(reader) = self.reader.take() {
            let _ = reader.join();
        }
    }
}

pub fn source_mode_spec() -> CommandSpec {
    let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    CommandSpec {
        program: repo.join(".venv/Scripts/python.exe"),
        args: vec![OsString::from("-m"), OsString::from("fahmm.bridge")],
        cwd: repo,
        env: Vec::new(),
    }
}

pub fn application_spec() -> Result<CommandSpec, String> {
    if cfg!(debug_assertions) {
        return Ok(source_mode_spec());
    }
    let executable = std::env::current_exe().map_err(|_| "BACKEND_UNAVAILABLE")?;
    let directory = executable.parent().ok_or("BACKEND_UNAVAILABLE")?.to_path_buf();
    Ok(CommandSpec {
        program: directory.join("fahmm-sidecar.exe"),
        args: Vec::new(),
        cwd: directory,
        env: Vec::new(),
    })
}

impl Drop for SidecarSupervisor {
    fn drop(&mut self) {
        self.stop();
    }
}

fn fail_pending(shared: &Shared, reason: &str) {
    for (_, sender) in shared.pending.lock().unwrap().drain() {
        let _ = sender.send(Err(reason.to_string()));
    }
}

fn read_replies(stdout: impl std::io::Read, shared: Arc<Shared>) {
    let mut reader = BufReader::new(stdout);
    while let Ok(Some(line)) = read_bounded_line(&mut reader) {
        let Ok(frame) = validate_frame(&line) else { break };
        let Some(kind) = frame["kind"].as_str() else { break };
        if kind == "event" {
            continue;
        }
        let Some(id) = frame["id"].as_str() else { break };
        if let Some(sender) = shared.pending.lock().unwrap().remove(id) {
            let reply = if kind == "response" {
                Ok(frame["result"].clone())
            } else {
                Err(frame["error"]["code"].as_str().unwrap_or("OPERATION_FAILED").to_string())
            };
            let _ = sender.send(reply);
        }
    }
    shared.connected.store(false, Ordering::SeqCst);
    fail_pending(&shared, "BACKEND_UNAVAILABLE");
}

fn read_bounded_line(reader: &mut impl BufRead) -> std::io::Result<Option<Vec<u8>>> {
    let mut line = Vec::new();
    loop {
        let available = reader.fill_buf()?;
        if available.is_empty() {
            return if line.is_empty() { Ok(None) } else {
                Err(std::io::Error::new(std::io::ErrorKind::UnexpectedEof, "partial frame"))
            };
        }
        let take = available.iter().position(|byte| *byte == b'\n')
            .map_or(available.len(), |position| position + 1);
        if line.len() + take > max_frame_bytes() + 1 {
            return Err(std::io::Error::new(std::io::ErrorKind::InvalidData, "oversized frame"));
        }
        let ended = available[take - 1] == b'\n';
        line.extend_from_slice(&available[..take]);
        reader.consume(take);
        if ended {
            line.pop();
            if line.last() == Some(&b'\r') { line.pop(); }
            return Ok(Some(line));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{CommandSpec, SidecarSupervisor, read_bounded_line};
    use serde_json::json;
    use std::ffi::OsString;
    use std::io::{BufReader, Cursor};
    use std::path::PathBuf;
    use std::sync::Arc;
    use std::thread;
    use std::time::{Duration, SystemTime, UNIX_EPOCH};

    const FAKE: &str = r#"
import json,sys,time
for line in sys.stdin:
    request=json.loads(line)
    if request['op']=='session.hello':
        if 1 not in request['params']['versions']:
            response={'v':1,'kind':'error','id':request['id'],'error':{'code':'UNSUPPORTED_VERSION','message':'Incompatible protocol'}}
        else:
            response={'v':1,'kind':'response','id':request['id'],'op':'session.hello','result':{'selectedVersion':1,'capabilities':['system.health']}}
    elif request['op']=='system.health':
        if 'slow' in sys.argv: time.sleep(5)
        response={'v':1,'kind':'response','id':request['id'],'op':'system.health','result':{'status':'ready'}}
    else: continue
    print(json.dumps(response),flush=True)
"#;

    fn fixture(slow: bool) -> CommandSpec {
        let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
        let python = repo.join(".venv/Scripts/python.exe");
        let suffix = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        let data = std::env::temp_dir().join(format!("fahmm-sidecar-test-{suffix}"));
        CommandSpec {
            program: python,
            args: if slow { vec![OsString::from("-u"), OsString::from("-c"), OsString::from(FAKE), OsString::from("slow")] }
                  else { vec![OsString::from("-u"), OsString::from("-c"), OsString::from(FAKE)] },
            cwd: repo,
            env: vec![(OsString::from("LOCALAPPDATA"), data.into_os_string())],
        }
    }

    #[test]
    fn correlates_concurrent_replies_and_restarts_explicitly() {
        let mut supervisor = Arc::new(SidecarSupervisor::start(fixture(false)).unwrap());
        let handles: Vec<_> = (0..2).map(|_| {
            let client = Arc::clone(&supervisor);
            thread::spawn(move || client.call("system.health", json!({}), Duration::from_secs(3)))
        }).collect();
        for handle in handles {
            assert_eq!(handle.join().unwrap().unwrap()["status"], "ready");
        }
        Arc::get_mut(&mut supervisor).unwrap().restart().unwrap();
        assert_eq!(supervisor.call("system.health", json!({}), Duration::from_secs(3)).unwrap()["status"], "ready");
    }

    #[test]
    fn rejects_incompatible_sidecar() {
        let result = SidecarSupervisor::start_with_versions(fixture(false), vec![2]);
        assert_eq!(result.err().unwrap(), "UNSUPPORTED_VERSION");
    }

    #[test]
    fn unexpected_exit_fails_pending_call() {
        let supervisor = Arc::new(SidecarSupervisor::start(fixture(true)).unwrap());
        let waiting = Arc::clone(&supervisor);
        let handle = thread::spawn(move || waiting.call("system.health", json!({}), Duration::from_secs(10)));
        thread::sleep(Duration::from_millis(200));
        supervisor.child.lock().unwrap().kill().unwrap();
        assert_eq!(handle.join().unwrap().err().unwrap(), "BACKEND_UNAVAILABLE");
        assert!(!supervisor.is_connected());
    }

    #[test]
    fn timed_out_call_is_not_replayed() {
        let supervisor = SidecarSupervisor::start(fixture(true)).unwrap();
        let result = supervisor.call("system.health", json!({}), Duration::from_millis(30));
        assert_eq!(result.err().unwrap(), "BACKEND_TIMEOUT");
    }

    #[test]
    fn reply_reader_rejects_oversized_lines() {
        let oversized = vec![b'x'; crate::protocol::max_frame_bytes() + 2];
        let mut reader = BufReader::new(Cursor::new(oversized));
        assert!(read_bounded_line(&mut reader).is_err());
    }

    #[test]
    fn frozen_sidecar_restarts_after_graceful_shutdown() {
        let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
        let binary = repo.join("desktop/src-tauri/binaries/fahmm-sidecar-x86_64-pc-windows-msvc.exe");
        if !binary.is_file() { return; }
        let suffix = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        let data = std::env::temp_dir().join(format!("fahmm-frozen-restart-{suffix}"));
        let spec = CommandSpec { program: binary, args: Vec::new(), cwd: repo,
            env: vec![(OsString::from("LOCALAPPDATA"), data.clone().into_os_string())] };
        let mut supervisor = SidecarSupervisor::start(spec).unwrap();
        assert_eq!(supervisor.call("system.health", json!({}), Duration::from_secs(3)).unwrap()["status"], "ready");
        supervisor.restart().unwrap();
        assert_eq!(supervisor.call("system.health", json!({}), Duration::from_secs(3)).unwrap()["status"], "ready");
        drop(supervisor);
        let _ = std::fs::remove_dir_all(data);
    }
}
