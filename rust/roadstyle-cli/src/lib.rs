//! The roadstyle program (docs/design/rust_library.md, plan step A1): one command for each job. `serve` serves the level editor: its page
//! files, and an area folder under `/area/`, on 127.0.0.1 only. The page writes only the area's own files (`WRITABLE`), with a PUT.

use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Component, Path, PathBuf};

/// The name of the area folder (the header X-Area of each answer: the editor shows it).
static AREA_NAME: std::sync::OnceLock<String> = std::sync::OnceLock::new();

/// The files of an area folder that the editor writes: your edits, heads and caps, and the solved levels.
pub const WRITABLE: [&str; 5] = ["edits.csv", "heads.csv", "caps.csv", "levels.csv", "levels_info.json"];

/// Serves `page` (the editor's files) at `/` and `area` at `/area/` on 127.0.0.1:`port`, until the program stops. A PUT of one of
/// `WRITABLE` to `/area/<name>` writes that file (the edits.csv before it is kept as edits.csv.bak).
pub fn serve(area: &Path, page: &Path, port: u16) -> Result<(), String> {
    let name = std::fs::canonicalize(area).ok().and_then(|p| p.file_name().map(|n| n.to_string_lossy().into_owned())).unwrap_or_default();
    AREA_NAME.get_or_init(|| name.chars().filter(|c| !c.is_control()).collect());
    let listener = TcpListener::bind(("127.0.0.1", port)).map_err(|e| format!("serve: 127.0.0.1:{port}: {e}"))?;
    let (area, page) = (area.to_path_buf(), page.to_path_buf());
    for stream in listener.incoming().flatten() {
        let (area, page) = (area.clone(), page.clone());
        std::thread::spawn(move || {
            if let Err(e) = answer(stream, &area, &page) {
                eprintln!("serve: {e}");
            }
        });
    }
    Ok(())
}

/// One request: GET or HEAD of a file, or PUT of a writable area file.
fn answer(stream: TcpStream, area: &Path, page: &Path) -> Result<(), String> {
    let mut reader = BufReader::new(stream.try_clone().map_err(|e| e.to_string())?);
    let mut line = String::new();
    reader.read_line(&mut line).map_err(|e| e.to_string())?;
    let mut parts = line.split_whitespace();
    let (method, target) = (parts.next().unwrap_or(""), parts.next().unwrap_or(""));
    let mut length = 0usize;
    loop {
        let mut h = String::new();
        if reader.read_line(&mut h).map_err(|e| e.to_string())? == 0 || h.trim().is_empty() {
            break;
        }
        if let Some((k, v)) = h.split_once(':') {
            if k.trim().eq_ignore_ascii_case("content-length") {
                length = v.trim().parse().map_err(|_| "a Content-Length that is not a number")?;
            }
        }
    }
    let path = target.split(['?', '#']).next().unwrap_or("/");
    let (root, rel) = match path.strip_prefix("/area/") {
        Some(rel) => (area, rel),
        None => (page, path.trim_start_matches('/')),
    };
    let index = format!("{rel}index.html"); // a folder: its index.html
    let rel = if rel.is_empty() || rel.ends_with('/') { index.as_str() } else { rel };
    let mut out = stream;
    let Some(file) = inside(root, rel) else {
        return reply(&mut out, "404 Not Found", "text/plain", b"not found", 0);
    };
    match method {
        "GET" | "HEAD" => match std::fs::read(&file) {
            Ok(body) => {
                // X-Mtime: the file's time in seconds, for the editor (levels.csv older than an input is solved again)
                let mtime = std::fs::metadata(&file).and_then(|m| m.modified()).ok()
                    .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok()).map_or(0, |d| d.as_secs());
                reply(&mut out, "200 OK", kind(&file), if method == "HEAD" { &[] } else { &body }, mtime)
            }
            Err(_) => reply(&mut out, "404 Not Found", "text/plain", b"not found", 0),
        },
        "PUT" if root == area && WRITABLE.contains(&rel) => {
            let mut body = vec![0u8; length];
            reader.read_exact(&mut body).map_err(|e| e.to_string())?;
            if rel == "edits.csv" && file.exists() {
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

fn kind(file: &Path) -> &'static str {
    match file.extension().and_then(|e| e.to_str()).unwrap_or("") {
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
    fn get_and_put() {
        let dir = std::env::temp_dir().join(format!("roadstyle-serve-{}", std::process::id()));
        let (area, page) = (dir.join("area"), dir.join("page"));
        std::fs::create_dir_all(&area).unwrap();
        std::fs::create_dir_all(&page).unwrap();
        std::fs::write(page.join("index.html"), "editor").unwrap();
        std::fs::write(area.join("edits.csv"), "old").unwrap();
        let port = TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
        let (a, p) = (area.clone(), page.clone());
        std::thread::spawn(move || serve(&a, &p, port));
        std::thread::sleep(std::time::Duration::from_millis(200));
        let ask = |req: &str| {
            let mut s = TcpStream::connect(("127.0.0.1", port)).unwrap();
            s.write_all(req.as_bytes()).unwrap();
            let mut text = String::new();
            s.read_to_string(&mut text).unwrap();
            text
        };
        assert!(ask("GET / HTTP/1.1\r\n\r\n").ends_with("editor"));
        assert!(ask("PUT /area/edits.csv HTTP/1.1\r\nContent-Length: 3\r\n\r\nnew").starts_with("HTTP/1.1 200"));
        assert_eq!(std::fs::read_to_string(area.join("edits.csv")).unwrap(), "new");
        assert_eq!(std::fs::read_to_string(area.join("edits.csv.bak")).unwrap(), "old");
        assert!(ask("PUT /area/roads.parquet HTTP/1.1\r\nContent-Length: 1\r\n\r\nx").starts_with("HTTP/1.1 405"));
        assert!(ask("GET /area/../page/index.html HTTP/1.1\r\n\r\n").starts_with("HTTP/1.1 404"));
        std::fs::remove_dir_all(&dir).ok();
    }
}
