use regex::Regex;
use serde_json::Value;
use std::sync::OnceLock;

static CONTRACT: OnceLock<Value> = OnceLock::new();

fn contract() -> &'static Value {
    CONTRACT.get_or_init(|| {
        serde_json::from_str(include_str!("../../protocol/contract.json"))
            .expect("valid bridge contract")
    })
}

pub fn max_frame_bytes() -> usize {
    contract()["maxFrameBytes"].as_u64().unwrap() as usize
}

fn id_ok(value: Option<&Value>) -> bool {
    let Some(id) = value.and_then(Value::as_str) else {
        return false;
    };
    let pattern = contract()["requestIdPattern"].as_str().unwrap();
    Regex::new(pattern).unwrap().is_match(id)
}

fn fields_match(value: Option<&Value>, fields: &Value) -> bool {
    let Some(object) = value.and_then(Value::as_object) else {
        return false;
    };
    fields.as_object().is_some_and(|expected| {
        object.keys().all(|name| expected.contains_key(name)) && expected.iter().all(|(name, kind)| {
            let item = object.get(name);
            match kind.as_str().unwrap_or("") {
                "string" => item.and_then(Value::as_str).is_some(),
                "string?" => item.is_none_or(|part| part.is_null() || part.is_string()),
                "number" => item.and_then(Value::as_f64).is_some(),
                "number?" => item.is_none_or(|part| part.is_null() || part.as_f64().is_some()),
                "integer" => item.and_then(Value::as_i64).is_some(),
                "boolean" => item.and_then(Value::as_bool).is_some(),
                "string[]" => item.and_then(Value::as_array).is_some_and(|items| {
                    items.iter().all(Value::is_string)
                }),
                "integer[]" => item.and_then(Value::as_array).is_some_and(|items| {
                    items.iter().all(|item| item.as_i64().is_some())
                }),
                "number[]" => item.and_then(Value::as_array).is_some_and(|items| {
                    items.iter().all(|item| item.as_f64().is_some())
                }),
                "object" => item.and_then(Value::as_object).is_some(),
                "object?" => item.is_none_or(|part| part.is_null() || part.is_object()),
                "object[]" => item.and_then(Value::as_array).is_some_and(|items| {
                    items.iter().all(Value::is_object)
                }),
                _ => false,
            }
        })
    })
}

pub fn validate_frame(raw: &[u8]) -> Result<Value, &'static str> {
    if raw.len() > max_frame_bytes() {
        return Err("FRAME_TOO_LARGE");
    }
    let frame: Value = serde_json::from_slice(raw).map_err(|_| "MALFORMED_FRAME")?;
    if frame.get("v").and_then(Value::as_u64) != contract()["version"].as_u64() {
        return Err("UNSUPPORTED_VERSION");
    }
    let valid = match frame.get("kind").and_then(Value::as_str) {
        Some("request") | Some("response") => {
            let op = frame.get("op").and_then(Value::as_str).unwrap_or("");
            let spec = &contract()["operations"][op];
            let (field, shape) = if frame["kind"] == "request" {
                ("params", "params")
            } else {
                ("result", "result")
            };
            id_ok(frame.get("id")) && !spec.is_null() && fields_match(frame.get(field), &spec[shape])
        }
        Some("error") => {
            let error = &frame["error"];
            let code = error["code"].as_str().unwrap_or("");
            id_ok(frame.get("id"))
                && contract()["errorCodes"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .any(|known| known == code)
                && error["message"].as_str().is_some_and(|message| message.len() <= 200)
        }
        Some("event") => {
            let name = frame.get("event").and_then(Value::as_str).unwrap_or("");
            let spec = &contract()["events"][name];
            !spec.is_null()
                && (frame.get("jobId").is_none() || id_ok(frame.get("jobId")))
                && fields_match(frame.get("data"), spec)
        }
        _ => false,
    };
    if valid { Ok(frame) } else { Err("INVALID_FRAME") }
}

#[cfg(test)]
mod tests {
    use super::validate_frame;
    use serde_json::Value;

    #[test]
    fn shared_contract_fixtures() {
        let fixtures: Value = serde_json::from_str(include_str!("../../protocol/fixtures.json")).unwrap();
        for frame in fixtures["valid"].as_array().unwrap() {
            assert!(validate_frame(frame.to_string().as_bytes()).is_ok());
        }
        for frame in fixtures["invalid"].as_array().unwrap() {
            assert!(validate_frame(frame.to_string().as_bytes()).is_err());
        }
        assert!(validate_frame(fixtures["malformed"].as_str().unwrap().as_bytes()).is_err());
        assert_eq!(validate_frame(&vec![b'x'; 1_048_577]), Err("FRAME_TOO_LARGE"));
    }
}
