//! The MCP server, driven the way an agent's app drives it: JSON-RPC messages over the program's stdin and stdout (the tests of the
//! Python server, tests/test_mcp_server.py, on Monaco).

use std::io::{BufRead, BufReader, Write};
use std::process::{Command, Stdio};

use serde_json::{json, Value};

const MONACO: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../roadstyle-rs/tests/data/monaco/roads.parquet");

/// The tools' names and the result of one tool call.
fn call(tool: &str, args: Value) -> (Vec<String>, Value) {
    let mut p = Command::new(env!("CARGO_BIN_EXE_roadstyle-mcp")).stdin(Stdio::piped()).stdout(Stdio::piped()).spawn().unwrap();
    let mut stdin = p.stdin.take().unwrap();
    let mut stdout = BufReader::new(p.stdout.take().unwrap());
    let mut send = |m: Value| writeln!(stdin, "{m}").unwrap();
    let mut answer = |id: u64| loop {
        let mut line = String::new();
        assert!(stdout.read_line(&mut line).unwrap() > 0, "the server stopped");
        let m: Value = serde_json::from_str(&line).unwrap();
        if m["id"] == id {
            return m["result"].clone();
        }
    };
    send(json!({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}}));
    assert_eq!(answer(1)["serverInfo"]["name"], "roadstyle");
    send(json!({"jsonrpc": "2.0", "method": "notifications/initialized"}));
    send(json!({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}));
    let mut tools: Vec<String> = answer(2)["tools"].as_array().unwrap().iter().map(|t| t["name"].as_str().unwrap().to_string()).collect();
    tools.sort();
    send(json!({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": tool, "arguments": args}}));
    let res = answer(3);
    p.kill().ok();
    p.wait().ok();
    (tools, res)
}

fn text(res: &Value) -> &str {
    res["content"][0]["text"].as_str().unwrap()
}

#[test]
fn render_file_reads_and_reports() {
    let out = std::env::temp_dir().join("roadstyle-mcp-test/monaco.html");
    let (tools, res) = call("render_file", json!({"path": MONACO, "output_path": out, "options": {"color_by": "highway"}}));
    assert_eq!(tools, ["render_file", "render_place", "snapshot"]);
    // TODO(R3): not an error, "Saved <out>" first, the file written and the preview (A4) after it
    assert_eq!(res["isError"], true, "{res}");
    assert!(text(&res).contains(" edges; classes: ") && text(&res).contains("bounds (w, s, e, n): 7."), "{res}");
    assert!(text(&res).contains("no page writer yet"), "{res}");
    assert!(!out.exists());
}

#[test]
fn misspelt_option_is_an_error_with_a_suggestion() {
    let out = std::env::temp_dir().join("roadstyle-mcp-test/x.html");
    let (_, res) = call("render_file", json!({"path": MONACO, "output_path": out, "options": {"colour_by": "highway"}}));
    assert_eq!(res["isError"], true);
    assert!(text(&res).contains("'colour_by' (did you mean 'color_by'"), "{res}");
    assert!(!out.exists());
}

#[test]
fn a_file_that_is_not_read_yet_is_an_error_that_says_so() {
    let (_, res) = call("render_file", json!({"path": "roads.gpkg"}));
    assert_eq!(res["isError"], true);
    assert!(text(&res).contains("GeoParquet files only"), "{res}");
}

#[test]
fn render_place_sends_the_agent_to_the_python_server() {
    let (_, res) = call("render_place", json!({"place": "Monaco"}));
    assert_eq!(res["isError"], true);
    assert!(text(&res).contains("roadstyle-mcp==0.25.0"), "{res}");
}

#[test]
fn snapshot_is_a_png_or_a_note_without_a_browser() {
    let dir = std::env::temp_dir().join("roadstyle-mcp-test");
    std::fs::create_dir_all(&dir).unwrap();
    let page = dir.join("page.html");
    std::fs::write(&page, "<!doctype html><body style='background:#2a6'><h1>roadstyle</h1></body>").unwrap();
    let (_, res) = call("snapshot", json!({"html_path": page}));
    assert_ne!(res["isError"], true, "{res}");
    // as the Python test: a PNG when Chromium is there, else a note that says how to get it
    let c = &res["content"][0];
    assert!(c["type"] == "image" && c["mimeType"] == "image/png" || text(&res).starts_with("(no preview: no Chromium found"), "{res}");
}
