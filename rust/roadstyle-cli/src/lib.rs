//! The roadstyle program (docs/design/rust_library.md, plan step A1): one command for each job. `serve` serves the level editor: its page
//! files (in the program, `EMBEDDED`, or a folder) and an area folder under `/area/`, on 127.0.0.1 only. The page writes only the area's
//! own files (`WRITABLE`), with a PUT. A request must name this server in `Host` (no DNS rebinding), a PUT must come from its own page
//! (`Origin`), and a body is at most `MAX_BODY` bytes.

use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Component, Path, PathBuf};

include!(concat!(env!("OUT_DIR"), "/embedded.rs"));

/// The name of the area folder (the header X-Area of each answer: the editor shows it).
static AREA_NAME: std::sync::OnceLock<String> = std::sync::OnceLock::new();

/// The files of an area folder that the editor writes: your edits, heads and caps, and the solved levels.
pub const WRITABLE: [&str; 5] = ["edits.csv", "heads.csv", "caps.csv", "levels.csv", "levels_info.json"];

/// The largest body of a PUT (levels.csv of Tartu, 65,000 edges, is about 4 MB), and of a request's line and headers.
pub const MAX_BODY: usize = 16 << 20;
const MAX_HEAD: usize = 64 << 10;

/// The editor's page files: the ones in the program, or a folder (`--page`, while you change them).
#[derive(Clone)]
pub enum Page {
    Embedded,
    Dir(PathBuf),
}

/// Serves the editor's `page` files at `/` and `area` at `/area/` on 127.0.0.1:`port`, until the program stops. A PUT of one of
/// `WRITABLE` to `/area/<name>` writes that file (the edits.csv before it is kept as edits.csv.bak).
pub fn serve(area: &Path, page: Page, port: u16) -> Result<(), String> {
    if matches!(page, Page::Embedded) && !EMBEDDED.iter().any(|(n, _)| n.ends_with("_bg.wasm")) {
        return Err("serve: this build has no WebAssembly package of the editor: run rust/roadstyle-wasm/build_editor.sh, then build again".into());
    }
    let name = std::fs::canonicalize(area).ok().and_then(|p| p.file_name().map(|n| n.to_string_lossy().into_owned())).unwrap_or_default();
    AREA_NAME.get_or_init(|| name.chars().filter(|c| !c.is_control()).collect());
    let listener = TcpListener::bind(("127.0.0.1", port)).map_err(|e| format!("serve: 127.0.0.1:{port}: {e}"))?;
    let area = area.to_path_buf();
    for stream in listener.incoming().flatten() {
        let (area, page) = (area.clone(), page.clone());
        std::thread::spawn(move || {
            if let Err(e) = answer(stream, &area, &page, port) {
                eprintln!("serve: {e}");
            }
        });
    }
    Ok(())
}

/// One request: GET or HEAD of a file, or PUT of a writable area file.
fn answer(stream: TcpStream, area: &Path, page: &Page, port: u16) -> Result<(), String> {
    let mut out = stream.try_clone().map_err(|e| e.to_string())?;
    let mut reader = BufReader::new(stream);
    // the request line and the headers, at most MAX_HEAD bytes
    let mut head = Vec::new();
    {
        let mut limited = (&mut reader).take(MAX_HEAD as u64);
        loop {
            let mut line = String::new();
            if limited.read_line(&mut line).map_err(|e| e.to_string())? == 0 {
                if limited.limit() == 0 {
                    return reply(&mut out, "431 Request Header Fields Too Large", "text/plain", b"headers too large", 0);
                }
                break;
            }
            if line.trim().is_empty() {
                break;
            }
            head.push(line);
        }
    }
    let first = head.first().cloned().unwrap_or_default();
    let mut parts = first.split_whitespace();
    let (method, target) = (parts.next().unwrap_or(""), parts.next().unwrap_or(""));
    let header = |name: &str| head.iter().skip(1).find_map(|h| {
        let (k, v) = h.split_once(':')?;
        k.trim().eq_ignore_ascii_case(name).then(|| v.trim().to_string())
    });
    // this server only: a page of another site reaches 127.0.0.1 through DNS rebinding with its own name in Host
    let own = [format!("127.0.0.1:{port}"), format!("localhost:{port}")];
    if !header("host").is_some_and(|h| own.contains(&h)) {
        return reply(&mut out, "403 Forbidden", "text/plain", b"not this server's Host", 0);
    }
    let path = target.split(['?', '#']).next().unwrap_or("/").trim_start_matches('/');
    let index = format!("{path}index.html"); // a folder: its index.html
    let rel = if path.is_empty() || path.ends_with('/') { index.as_str() } else { path };
    let Some(area_rel) = rel.strip_prefix("area/") else {
        // the editor's page files: read only
        if !matches!(method, "GET" | "HEAD") {
            return reply(&mut out, "405 Method Not Allowed", "text/plain", b"the page's files are read only", 0);
        }
        let body = match page {
            Page::Embedded => EMBEDDED.iter().find(|(n, _)| *n == rel).map(|(_, b)| b.to_vec()),
            Page::Dir(dir) => inside(dir, rel).and_then(|f| std::fs::read(f).ok()),
        };
        return match body {
            Some(b) => reply(&mut out, "200 OK", kind(rel), if method == "HEAD" { &[] } else { &b }, 0),
            None => reply(&mut out, "404 Not Found", "text/plain", b"not found", 0),
        };
    };
    let Some(file) = inside(area, area_rel) else {
        return reply(&mut out, "404 Not Found", "text/plain", b"not found", 0);
    };
    match method {
        "GET" | "HEAD" => match std::fs::read(&file) {
            Ok(body) => {
                // X-Mtime: the file's time in seconds, for the editor (levels.csv older than an input is solved again)
                let mtime = std::fs::metadata(&file).and_then(|m| m.modified()).ok()
                    .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok()).map_or(0, |d| d.as_secs());
                reply(&mut out, "200 OK", kind(area_rel), if method == "HEAD" { &[] } else { &body }, mtime)
            }
            Err(_) => reply(&mut out, "404 Not Found", "text/plain", b"not found", 0),
        },
        "PUT" if WRITABLE.contains(&area_rel) => {
            // from this server's own page only (a browser sends Origin with a PUT)
            if header("origin").is_some_and(|o| !own.iter().any(|h| o == format!("http://{h}"))) {
                return reply(&mut out, "403 Forbidden", "text/plain", b"not this server's page", 0);
            }
            let length: usize = header("content-length").ok_or("a PUT with no Content-Length")?.parse()
                .map_err(|_| "a Content-Length that is not a number")?;
            if length > MAX_BODY {
                return reply(&mut out, "413 Content Too Large", "text/plain", b"more than 16 MB", 0);
            }
            let mut body = vec![0u8; length];
            reader.read_exact(&mut body).map_err(|e| e.to_string())?;
            if area_rel == "edits.csv" && file.exists() {
                std::fs::copy(&file, area.join("edits.csv.bak")).map_err(|e| e.to_string())?;
            }
            std::fs::write(&file, &body).map_err(|e| format!("{}: {e}", file.display()))?;
            reply(&mut out, "200 OK", "text/plain", b"saved", 0)
        }
        _ => reply(&mut out, "405 Method Not Allowed", "text/plain", b"only GET, and PUT of the area's own files", 0),
    }
}

/// `rel` under `root`, or None for a path with `..`, a root or a drive in it.
fn inside(root: &Path, rel: &str) -> Option<PathBuf> {
    let rel = Path::new(rel);
    rel.components().all(|c| matches!(c, Component::Normal(_))).then(|| root.join(rel))
}

fn kind(file: &str) -> &'static str {
    match Path::new(file).extension().and_then(|e| e.to_str()).unwrap_or("") {
        "html" => "text/html; charset=utf-8",
        "js" | "mjs" => "text/javascript",
        "css" => "text/css",
        "json" => "application/json",
        "wasm" => "application/wasm",
        "csv" => "text/csv; charset=utf-8",
        "png" => "image/png",
        "svg" => "image/svg+xml",
        _ => "application/octet-stream",
    }
}

fn reply(out: &mut TcpStream, status: &str, kind: &str, body: &[u8], mtime: u64) -> Result<(), String> {
    let head = format!("HTTP/1.1 {status}\r\nContent-Type: {kind}\r\nContent-Length: {}\r\nX-Mtime: {mtime}\r\nX-Area: {}\r\nCache-Control: no-store\r\n\
                        Connection: close\r\n\r\n", body.len(), AREA_NAME.get().map_or("", String::as_str));
    out.write_all(head.as_bytes()).and_then(|_| out.write_all(body)).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_paths_inside_the_root() {
        let root = Path::new("/srv/area");
        assert_eq!(inside(root, "edits.csv"), Some(root.join("edits.csv")));
        assert_eq!(inside(root, "pkg/a.wasm"), Some(root.join("pkg/a.wasm")));
        assert!(inside(root, "../secret").is_none() && inside(root, "/etc/passwd").is_none() && inside(root, "a/../../b").is_none());
    }

    #[test]
    fn the_editor_files_are_in_the_program() {
        for f in ["level_editor/index.html", "level_editor/app.js", "level_editor.html", "dashboard/index.js", "dashboard/dashboard.css", "popup.css", "popup.js"] {
            assert!(EMBEDDED.iter().any(|(n, b)| *n == f && !b.is_empty()), "{f}");
        }
    }

    /// A server on a free port with a page folder and an area folder; `ask(request)` gives the answer's text.
    fn server(tag: &str) -> (PathBuf, impl Fn(&str) -> String, u16) {
        let dir = std::env::temp_dir().join(format!("roadstyle-serve-{tag}-{}", std::process::id()));
        let (area, page) = (dir.join("area"), dir.join("page"));
        std::fs::create_dir_all(&area).unwrap();
        std::fs::create_dir_all(&page).unwrap();
        std::fs::write(page.join("index.html"), "editor").unwrap();
        std::fs::write(area.join("edits.csv"), "old").unwrap();
        let port = TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
        let (a, p) = (area.clone(), page.clone());
        std::thread::spawn(move || serve(&a, Page::Dir(p), port));
        std::thread::sleep(std::time::Duration::from_millis(200));
        let ask = move |req: &str| {
            let mut s = TcpStream::connect(("127.0.0.1", port)).unwrap();
            s.write_all(req.as_bytes()).ok();
            let mut text = String::new();
            s.read_to_string(&mut text).ok();
            text
        };
        (area, ask, port)
    }

    #[test]
    fn get_and_put() {
        let (area, ask, port) = server("put");
        let host = format!("Host: 127.0.0.1:{port}\r\n");
        assert!(ask(&format!("GET / HTTP/1.1\r\n{host}\r\n")).ends_with("editor"));
        let put = format!("PUT /area/edits.csv HTTP/1.1\r\n{host}Origin: http://127.0.0.1:{port}\r\nContent-Length: 3\r\n\r\nnew");
        assert!(ask(&put).starts_with("HTTP/1.1 200"));
        assert_eq!(std::fs::read_to_string(area.join("edits.csv")).unwrap(), "new");
        assert_eq!(std::fs::read_to_string(area.join("edits.csv.bak")).unwrap(), "old");
        assert!(ask(&format!("PUT /area/roads.parquet HTTP/1.1\r\n{host}Content-Length: 1\r\n\r\nx")).starts_with("HTTP/1.1 405"));
        assert!(ask(&format!("PUT /index.html HTTP/1.1\r\n{host}Content-Length: 1\r\n\r\nx")).starts_with("HTTP/1.1 405"));
        assert!(ask(&format!("GET /area/../page/index.html HTTP/1.1\r\n{host}\r\n")).starts_with("HTTP/1.1 404"));
    }

    #[test]
    fn another_host_or_origin_is_refused() {
        let (area, ask, port) = server("host");
        assert!(ask("GET / HTTP/1.1\r\nHost: evil.example:80\r\n\r\n").starts_with("HTTP/1.1 403"));
        assert!(ask("GET / HTTP/1.1\r\n\r\n").starts_with("HTTP/1.1 403"));
        assert!(ask(&format!("GET / HTTP/1.1\r\nHost: localhost:{port}\r\n\r\n")).starts_with("HTTP/1.1 200"));
        let put = format!("PUT /area/edits.csv HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nOrigin: http://evil.example\r\nContent-Length: 1\r\n\r\nx");
        assert!(ask(&put).starts_with("HTTP/1.1 403"));
        assert_eq!(std::fs::read_to_string(area.join("edits.csv")).unwrap(), "old");
    }

    #[test]
    fn a_body_or_headers_too_large_are_refused() {
        let (area, ask, port) = server("size");
        let big = format!("PUT /area/edits.csv HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Length: {}\r\n\r\n", MAX_BODY + 1);
        assert!(ask(&big).starts_with("HTTP/1.1 413"));
        let long = format!("GET / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nX-Long: {}\r\n\r\n", "a".repeat(MAX_HEAD + 10));
        assert!(ask(&long).starts_with("HTTP/1.1 431"));
        assert_eq!(std::fs::read_to_string(area.join("edits.csv")).unwrap(), "old");
    }
}
