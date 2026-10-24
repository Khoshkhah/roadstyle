# Review checklist: the design patterns to look for

The 8 patterns of the design audit of 2026-10-23 ([audit_2026-10-23.md](audit_2026-10-23.md)). Each step's report gives one line for
each pattern that the step removed or added, with its place. A step does not add a new instance of a pattern without a reason in its
report.

| # | Pattern | Example that was fixed |
|---|---|---|
| 1 | One step does several jobs: it must be stages with a typed border | step (f): the style, its sources and the tiles were one call |
| 2 | The same data is stored or repeated in several places (per feature, per tile, per zoom) | step (b): each piece held a copy of its road's properties |
| 3 | Two code paths do the same job | `make_tiled` and `make_style` each ran stage 1 with their own loop |
| 4 | Text or JSON where typed data fits | step (b): the roads and the marks were JSON maps |
| 5 | Work is done again that could be done once or cached | the levels are solved again for each style (audit R12) |
| 6 | A hidden name contract across languages (`__rs_*` properties, layer id prefixes) | the dashboard finds layers by id prefix (audit R7) |
| 7 | Coupling that blocks reuse: a module that knows its caller or a file format | step (a): the engine read Parquet bytes |
| 8 | Memory and copy hot spots | step (b): 16.4 KB for each road on Tartu, now 5.5 KB |
