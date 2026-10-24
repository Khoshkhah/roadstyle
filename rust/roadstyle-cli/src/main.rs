//! `roadstyle <command>`: the roadstyle program. Commands: `serve <area folder> [--port N] [--page DIR]` (the level editor; its page files
//! are in the program, `--page` takes them from a folder while you change them); `snapshot <page.html> <out.png> [camera, size, times]`
//! (a PNG of a saved page, drawn by Chromium: roadstyle-snapshot).

const USAGE: &str = "usage: roadstyle serve <area folder> [--port 8780] [--page <a folder of the editor's files, in place of the program's>]
       roadstyle snapshot <page.html> <out.png> [--center LON,LAT] [--zoom Z] [--pitch P] [--bearing B] [--width 1200] [--height 800]
                          [--scale 1] [--settle 2.5] [--timeout 40]";

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if let Err(e) = run(&args) {
        eprintln!("roadstyle: {e}");
        std::process::exit(2);
    }
}

fn run(args: &[String]) -> Result<(), String> {
    match args.first().map(String::as_str) {
        Some("serve") => {
            let (mut area, mut port, mut page) = (None, 8780u16, None);
            let mut it = args[1..].iter();
            while let Some(a) = it.next() {
                match a.as_str() {
                    "--port" => port = it.next().and_then(|p| p.parse().ok()).ok_or("--port needs a number")?,
                    "--page" => page = Some(it.next().ok_or("--page needs a folder")?.clone()),
                    _ if area.is_none() => area = Some(a.clone()),
                    _ => return Err(format!("unknown argument {a}\n{USAGE}")),
                }
            }
            let area = std::path::PathBuf::from(area.ok_or(USAGE)?);
            let page = page.map_or(roadstyle_cli::Page::Embedded, |p| roadstyle_cli::Page::Dir(p.into()));
            println!("level editor: http://127.0.0.1:{port}/level_editor/  ({}; Ctrl+C to stop)", area.display());
            roadstyle_cli::serve(&area, page, port)
        }
        Some("snapshot") => snapshot(&args[1..]),
        _ => Err(USAGE.into()),
    }
}

fn snapshot(args: &[String]) -> Result<(), String> {
    use roadstyle_snapshot::{Camera, Shot};
    let (mut files, mut cam, mut shot) = (Vec::new(), Camera::default(), Shot::default());
    let mut it = args.iter();
    while let Some(a) = it.next() {
        if !a.starts_with("--") {
            files.push(a.clone());
            continue;
        }
        let v = it.next().ok_or(format!("{a} needs a value"))?;
        let num = |v: &str| v.parse::<f64>().map_err(|_| format!("{a} needs a number, not {v:?}"));
        match a.as_str() {
            "--center" => {
                let ll: Vec<f64> = v.split(',').map(num).collect::<Result<_, _>>()?;
                cam.center = Some(<[f64; 2]>::try_from(ll).map_err(|_| "--center needs LON,LAT")?);
            }
            "--zoom" => cam.zoom = Some(num(v)?),
            "--pitch" => cam.pitch = Some(num(v)?),
            "--bearing" => cam.bearing = Some(num(v)?),
            "--width" => shot.width = num(v)? as u32,
            "--height" => shot.height = num(v)? as u32,
            "--scale" => shot.scale = num(v)?,
            "--settle" => shot.settle = std::time::Duration::from_secs_f64(num(v)?),
            "--timeout" => shot.timeout = std::time::Duration::from_secs_f64(num(v)?),
            _ => return Err(format!("unknown argument {a}\n{USAGE}")),
        }
    }
    let [page, out] = <[String; 2]>::try_from(files).map_err(|_| USAGE.to_string())?;
    roadstyle_snapshot::snapshot(page.as_ref(), out.as_ref(), &cam, &shot).map_err(|e| e.to_string())?;
    println!("{out}");
    Ok(())
}
