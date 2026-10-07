# A short road keeps its two heads

**Status:** implemented 2026-10-04 ("go with your suggestion"). It changes one rule of `levels_split_casing.md`, section 9.

## The case

The casing of a road is drawn as pieces: the first `head_m` metres at the start number, the middle at the main number, the last `head_m` metres at the end number. A road shorter than
`2 · head_m` was one piece at the **main** number, so its two head numbers were never drawn.

That is harmless when the numbers were solved with the same `head_m`: the solver (section 6) gives a short road one number in all three columns. It is wrong when the page cuts with a longer
`head_m` than the numbers were solved with. lanestyle does (the numbers are duckOSM's, solved with `head_m` 5; lanestyle draws with 25 m). A 21 m ground road after a tunnel
(`176334444#1f`, Monaco) has the numbers start 0, main 3, end 3 against the tunnel's 0: with 25 m it was one piece at 3, so its casing lay over the tunnel's fill and a line showed between two roads that meet.

## The rule

The head is `h = min(head_m, length / 2)`. The casing of an edge whose three numbers are not all equal is the first `h` metres at the start number, the middle at the main number
(none when `length ≤ 2h`), and the last `h` metres at the end number. A short road is therefore two halves, one at each head's number. Nothing changes for a road of `2 · head_m` or more, for a road whose three numbers
are equal, or when the page and the solver use the same `head_m` (a short road has equal numbers then).

| Edge | Casing pieces |
|---|---|
| length ≥ `2 · head_m`, numbers not all equal | three, as before |
| length < `2 · head_m`, numbers not all equal | **two**: the first half at the start number, the second half at the end number |
| numbers all equal, or any other geometry | one, as before |

## Not done

The head is still one global length. A fork whose branches stay together for longer than the head still shows a casing line after it; a head that depends on the junction is a change of the solver.
