//! `roadstyle <command>`: the roadstyle program. Commands: `serve <area folder> [--port N] [--page DIR]` (the level editor; its page files
//! are in the program, `--page` takes them from a folder while you change them).

const USAGE: &str = "usage: roadstyle serve <area folder> [--port 8780] [--page <a folder of the editor's files, in place of the program's>]";

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
        _ => Err(USAGE.into()),
    }
}
