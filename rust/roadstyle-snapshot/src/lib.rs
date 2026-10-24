//! PNG pictures of saved roadstyle pages (plan step A4 in docs/design/rust_library.md). Chromium draws the page over CDP
//! (headless_chrome), with the steps of roadstyle's Python snapshot (src/roadstyle/snapshot.py, Playwright): open the page, wait until
//! MapLibre has loaded, move the camera, let the tiles and labels settle, write the viewport as a PNG. The same Chromium gives the same
//! picture as Python. The browser is not downloaded: `find_browser` names where it looks.

use std::fmt;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use headless_chrome::protocol::cdp::{Emulation, Page};
use headless_chrome::{Browser, LaunchOptions};
use serde_json::{json, Value};

/// The camera of the picture. A field that is None keeps the page's own opening view (its fitted bounds).
#[derive(Clone, Debug, Default)]
pub struct Camera {
    /// lon, lat
    pub center: Option<[f64; 2]>,
    pub zoom: Option<f64>,
    pub pitch: Option<f64>,
    pub bearing: Option<f64>,
}

/// The picture's size and times, with the defaults of Python's snapshot.
#[derive(Clone, Debug)]
pub struct Shot {
    /// the viewport in CSS pixels
    pub width: u32,
    pub height: u32,
    /// the device pixel ratio: 2 writes a 2*width x 2*height PNG
    pub scale: f64,
    /// the time after loading for the tiles and labels to finish drawing
    pub settle: Duration,
    /// the longest time for the map to load
    pub timeout: Duration,
}

impl Default for Shot {
    fn default() -> Shot {
        Shot { width: 1200, height: 800, scale: 1.0, settle: Duration::from_millis(2500), timeout: Duration::from_secs(40) }
    }
}

#[derive(Debug)]
pub enum SnapshotError {
    /// no Chromium in these places
    NoBrowser { searched: Vec<String> },
    /// Chromium did not start
    Launch(String),
    /// the page or the browser did not answer in this time
    Timeout(Duration),
    /// the page did not open, or the browser failed while it drew the page
    Page(String),
    Io(std::io::Error),
}

impl fmt::Display for SnapshotError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SnapshotError::NoBrowser { searched } => write!(f, "no Chromium found (searched: {}). Install one with: npx playwright \
                install chromium-headless-shell, or set CHROME to a Chrome or Chromium program", searched.join("; ")),
            SnapshotError::Launch(e) => write!(f, "Chromium did not start: {e}"),
            SnapshotError::Timeout(t) => write!(f, "the page or the browser did not answer in {} s", t.as_secs_f64()),
            SnapshotError::Page(e) => write!(f, "the page: {e}"),
            SnapshotError::Io(e) => write!(f, "{e}"),
        }
    }
}

impl std::error::Error for SnapshotError {}

impl From<std::io::Error> for SnapshotError {
    fn from(e: std::io::Error) -> SnapshotError {
        SnapshotError::Io(e)
    }
}

/// The time for the page and the browser to answer (open the page, run a script, take the picture): Playwright's default, as in Python.
/// `Shot::timeout` is only the time for the map to load.
const ANSWER: Duration = Duration::from_secs(30);

const PATH_NAMES: [&str; 5] = ["chromium", "chromium-browser", "chrome", "google-chrome", "google-chrome-stable"];

/// The Chromium program, in this order: the CHROME variable (when it is set, only it), a Chrome or Chromium on PATH, the newest
/// Chromium of Playwright (PLAYWRIGHT_BROWSERS_PATH or ~/.cache/ms-playwright; the headless shell first, as Playwright uses it).
pub fn find_browser() -> Result<PathBuf, SnapshotError> {
    if let Some(c) = std::env::var_os("CHROME") {
        let p = PathBuf::from(&c);
        return if p.is_file() { Ok(p) } else { Err(SnapshotError::NoBrowser { searched: vec![format!("CHROME={}", p.display())] }) };
    }
    let mut searched = vec!["CHROME (not set)".to_string()];
    for dir in std::env::split_paths(&std::env::var_os("PATH").unwrap_or_default()) {
        for n in PATH_NAMES {
            if dir.join(n).is_file() {
                return Ok(dir.join(n));
            }
        }
    }
    searched.push(format!("{} on PATH", PATH_NAMES.join(", ")));
    let cache = std::env::var_os("PLAYWRIGHT_BROWSERS_PATH").map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|h| Path::new(&h).join(".cache/ms-playwright")));
    if let Some(cache) = cache {
        for (prefix, program) in [("chromium_headless_shell-", "chrome-headless-shell-linux64/chrome-headless-shell"),
                                  ("chromium-", "chrome-linux64/chrome")] {
            // the newest revision: the largest number after the prefix
            let newest = std::fs::read_dir(&cache).into_iter().flatten().flatten()
                .filter_map(|e| Some((e.file_name().to_str()?.strip_prefix(prefix)?.parse::<u32>().ok()?, e.path())))
                .max_by_key(|(n, _)| *n);
            if let Some(p) = newest.map(|(_, d)| d.join(program)).filter(|p| p.is_file()) {
                return Ok(p);
            }
        }
        searched.push(format!("{}/chromium*", cache.display()));
    }
    Err(SnapshotError::NoBrowser { searched })
}

/// A picture that was written.
#[derive(Debug)]
pub struct Picture {
    pub path: PathBuf,
    /// what the picture can be missing: a map that did not load in the time (the picture shows it as it was, as Python does)
    pub warning: Option<String>,
}

/// The PNG of the saved page `page`, written to `out`.
pub fn snapshot(page: &Path, out: &Path, camera: &Camera, shot: &Shot) -> Result<Picture, SnapshotError> {
    let url = format!("file://{}", std::path::absolute(page)?.display());
    let options = LaunchOptions::default_builder().path(Some(find_browser()?)).headless(true)
        // as Playwright's launch: no sandbox, no scroll bars in the picture
        .sandbox(false).args(vec![std::ffi::OsStr::new("--hide-scrollbars")])
        .window_size(Some((shot.width, shot.height))).idle_browser_timeout(shot.timeout + shot.settle + ANSWER)
        .build().map_err(|e| SnapshotError::Launch(e.to_string()))?;
    let browser = Browser::new(options).map_err(|e| SnapshotError::Launch(e.to_string()))?;
    // headless_chrome's own time limit (a page or a browser that does not answer) is a Timeout; any other failure is the page's
    let page_err = |e: anyhow::Error| match e.is::<headless_chrome::util::Timeout>() {
        true => SnapshotError::Timeout(ANSWER),
        false => SnapshotError::Page(e.to_string()),
    };
    let tab = browser.new_tab().map_err(page_err)?;
    tab.set_default_timeout(ANSWER);
    tab.call_method(Emulation::SetDeviceMetricsOverride {
        width: shot.width, height: shot.height, device_scale_factor: shot.scale, mobile: false, scale: None, screen_width: None,
        screen_height: None, position_x: None, position_y: None, dont_set_visible_size: None, screen_orientation: None, viewport: None,
        display_feature: None, device_posture: None,
    }).map_err(page_err)?;
    tab.navigate_to(&url).map_err(page_err)?.wait_until_navigated().map_err(page_err)?;
    // a MapLibre page: wait until the map has loaded. A page with no `map` (folium, other pages) only gets the settle time, and a map that
    // does not load in the time is taken as it is, with a warning, as in Python.
    let (start, mut warning) = (Instant::now(), None);
    loop {
        let state = tab.evaluate("window.map && typeof window.map.loaded === 'function' ? window.map.loaded() : null", false)
            .map_err(page_err)?.value.unwrap_or(Value::Null);
        match state {
            Value::Bool(true) => break,
            Value::Null if start.elapsed() > Duration::from_secs(2) => break,
            _ if start.elapsed() > shot.timeout => {
                warning = Some(format!("the map did not load in {} s: the picture shows it as it was then", shot.timeout.as_secs_f64()));
                break;
            }
            _ => std::thread::sleep(Duration::from_millis(100)),
        }
    }
    let mut cam = serde_json::Map::new();
    for (k, v) in [("zoom", camera.zoom), ("pitch", camera.pitch), ("bearing", camera.bearing)] {
        if let Some(v) = v {
            cam.insert(k.into(), json!(v));
        }
    }
    if let Some(c) = camera.center {
        cam.insert("center".into(), json!(c));
    }
    if !cam.is_empty() {
        tab.evaluate(&format!("window.map && window.map.jumpTo({})", Value::Object(cam)), false).map_err(page_err)?;
    }
    std::thread::sleep(shot.settle);
    let png = tab.capture_screenshot(Page::CaptureScreenshotFormatOption::Png, None, None, true).map_err(page_err)?;
    std::fs::write(out, png)?;
    Ok(Picture { path: out.to_path_buf(), warning })
}
