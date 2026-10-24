//! `roadstyle <command>`: the roadstyle program (`roadstyle help` lists the commands: lib.rs, commands.rs).

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if let Err(e) = roadstyle_cli::commands::run(&args) {
        eprintln!("roadstyle: {e}");
        std::process::exit(2);
    }
}
