//! User-authorized audio paths received from native drag-and-drop events.

use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{Duration, Instant};

const DROP_TTL: Duration = Duration::from_secs(120);

#[derive(Default)]
pub struct AudioDropState(Mutex<PendingState>);

#[derive(Default)]
struct PendingState {
    next_token: u32,
    pending: Option<PendingDrop>,
}

struct PendingDrop {
    token: u32,
    path: PathBuf,
    received_at: Instant,
}

fn supported_audio(path: &std::path::Path) -> bool {
    path.extension()
        .and_then(|extension| extension.to_str())
        .is_some_and(|extension| {
            ["wav", "mp3", "m4a", "flac"]
                .iter()
                .any(|allowed| extension.eq_ignore_ascii_case(allowed))
        })
}

impl AudioDropState {
    /// A token can only refer to a path delivered by the OS, never an IPC path.
    pub fn register(&self, paths: &[PathBuf]) -> Result<u32, &'static str> {
        let mut state = self.0.lock().map_err(|_| "INVALID_REQUEST")?;
        state.pending = None;
        if paths.len() != 1 {
            return Err("multiple");
        }
        if !supported_audio(&paths[0]) {
            return Err("unsupported");
        }
        state.next_token = state.next_token.wrapping_add(1).max(1);
        let token = state.next_token;
        state.pending = Some(PendingDrop {
            token,
            path: paths[0].clone(),
            received_at: Instant::now(),
        });
        Ok(token)
    }

    pub fn take(&self, token: u32) -> Option<PathBuf> {
        let mut state = self.0.lock().ok()?;
        let pending = state.pending.as_ref()?;
        if pending.received_at.elapsed() > DROP_TTL {
            state.pending = None;
            return None;
        }
        if pending.token != token {
            return None;
        }
        state.pending.take().map(|pending| pending.path)
    }

    pub fn discard(&self, token: u32) {
        if let Ok(mut state) = self.0.lock() {
            if state
                .pending
                .as_ref()
                .is_some_and(|pending| pending.token == token)
            {
                state.pending = None;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_only_one_supported_native_drop_and_consumes_it_once() {
        let state = AudioDropState::default();
        assert_eq!(state.register(&[]), Err("multiple"));
        assert_eq!(
            state.register(&["a.mp3".into(), "b.wav".into()]),
            Err("multiple")
        );
        assert_eq!(state.register(&["bad.txt".into()]), Err("unsupported"));
        let token = state.register(&["voice.MP3".into()]).unwrap();
        assert_eq!(state.take(token + 1), None);
        assert_eq!(state.take(token), Some("voice.MP3".into()));
        assert_eq!(state.take(token), None);
    }

    #[test]
    fn later_or_discarded_drops_cannot_reuse_old_tokens() {
        let state = AudioDropState::default();
        let old = state.register(&["first.wav".into()]).unwrap();
        let new = state.register(&["second.flac".into()]).unwrap();
        state.discard(old);
        assert_eq!(state.take(old), None);
        state.discard(new);
        assert_eq!(state.take(new), None);
    }

    #[test]
    fn expired_drop_cannot_be_imported() {
        let state = AudioDropState::default();
        let token = state.register(&["audio.m4a".into()]).unwrap();
        state
            .0
            .lock()
            .unwrap()
            .pending
            .as_mut()
            .unwrap()
            .received_at = Instant::now() - DROP_TTL - Duration::from_secs(1);
        assert_eq!(state.take(token), None);
    }
}
