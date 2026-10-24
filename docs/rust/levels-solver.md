# How the levels are solved

<p class="lead">About the Rust solver of the drawing levels (the crate <code>roadstyle-levels</code>): what it decides, how its
rules become a graph, and how minimum-cost flows find the numbers.</p>

## What the solver decides

Each road gets four whole numbers, its positions in the drawing order. A higher number is drawn later, so it is on top:

| Number | In the code | What it places |
|---|---|---|
| the fill | `b` (`fill_level`) | the inside of the road |
| the start head of the casing | `a0` (`casing_start`) | the casing at the start of the road |
| the main part of the casing | `a1` (`casing_level`) | the casing between the heads |
| the end head of the casing | `a2` (`casing_end`) | the casing at the end of the road |

The level input (`level_input`) gives the solver the relations of the roads: which roads cross, which meet, and which one is
wanted on top. The solver reads only these tables, never the lines.

## The rules

**Hard rules** always hold:

- **H1.** A casing part is never over the fill of its own road: `a ≤ b`.
- **H2.** Where two roads meet, the head of each one is not over the fill of the other.
- **The box.** Every number is in a range of `2 × max_level / margin` steps: −20 to 20 with the defaults (inside the solver, 0 to
  40).
- **Fixed numbers.** A road that is fixed (for example a hand fix of the level editor) keeps its numbers.

**Soft rules** hold when they can. When they conflict, the solver breaks the fewest, in this order of priority:

1. **Stack.** A road that crosses over another road: the crossing part of its casing is at least one step over the fill of the
   lower road. This is a real bridge or tunnel.
2. **Order wish.** At a place where roads only meet, the fill of one road is over the fill of the other: a roundabout over a
   tunnel, a tunnel over a bridge, a higher class over a lower one.
3. **Near** (only with `near_rules=True`): a part that only comes near the lower road.

After these: **as few positions as possible** (the span of the numbers, with `min_positions`, the default), and then the casings as
close to their fills as possible.

## Every rule has one form

Each rule says: *this number is at most that number, plus a constant*:

```text
x_i − x_j ≤ w
```

| Rule | As `x_i − x_j ≤ w` |
|---|---|
| H1: a casing part not over its fill | `a − b ≤ 0` |
| Stack: the part `a` of the upper road one step over the fill `b'` of the lower road | `b' − a ≤ −1` |
| Order: the fill `b` over the fill `b'` | `b' − b ≤ −1` |
| The box: every number at most `steps` | `x − 0 ≤ steps` |

Rules of this form are a **graph**. Each number is a node, and each rule `x_i − x_j ≤ w` is an arrow from `i` to `j` with the
cost `w`. A bridge whose main casing crosses over a road:

```mermaid
flowchart LR
    road["b'<br/>road's fill"]
    casing["a1<br/>bridge casing"]
    fill["b<br/>bridge fill"]
    road -->|"−1: stack"| casing
    casing -->|"0: H1"| fill
```

*The stack arrow says `b' − a1 ≤ −1`, the H1 arrow says `a1 − b ≤ 0`. A solution: `b' = 0`, `a1 = 1`, `b = 1`.*

The fact that makes the graph useful: **the rules can all hold at the same time when no loop of arrows has a negative total
cost.** A loop with the cost −3 means that, around that loop, the rules ask for 3 steps more than the numbers can give. For
example, three roads that meet in a ring, each one wished over the next one: three order arrows of −1 in a loop. At least one wish
must break, and the misses add up to 3 steps, however they are shared.

## Each stage is a minimum-cost flow

The question of a stage, "break the soft rules of this priority by as few steps as possible", has a twin problem in the graph
(the duality of linear programming): **send flow around the arrows at the least cost**, where

- a hard arrow can carry any amount of flow;
- a soft arrow of this stage can carry at most 1 unit;
- the soft arrows of the later stages are not in the graph yet.

Flow goes only around the loops whose cost is negative, because only there it lowers the cost. The least cost of the flow is minus
the fewest steps that must be broken. The flow also shows **which** rules break: the soft arrows that carry flow. With no
negative loop there is no flow, and nothing breaks.

The stages run in the order of priority: stack, then order, then near. After each stage, the solver **locks** its result, so a
later stage cannot spoil it:

| After a stage, an arrow | becomes | so that |
|---|---|---|
| soft, with flow (broken) | a hard rule the other way: `x_i − x_j ≥ w` | the later stages cannot repair it at the cost of this stage's best value |
| soft, with no flow (kept) | a hard rule | it stays kept |
| hard, with flow (tight) | also its reverse: `x_i − x_j = w` | the best value of this stage stays the best |

Then the next stage adds its own soft arrows to the graph and solves again.

## The last stage: fewest positions, then close casings

The last flow has a different goal: the casing parts as close to their fills as possible (the sum of `b − a` over all casing
parts), with a very large weight on the span (the highest number minus the lowest), so the span comes first.

1. **The least span.** Two extra nodes, `H` and `L`, hold the highest and the lowest number (every number between them). The least
   span is a shortest-path length from `L` to `H` in the graph of the hard rules. An arrow `H − L ≤ span` keeps it.
2. **The closest casings.** Each casing part sends one unit of flow to the fill of its road. The cheapest flow that delivers all
   these units gives the least sum of `b − a`.

## From the flow back to the numbers

The flow does not give the numbers directly. It gives which rules are **tight** (the arrows with flow) and which have room. The
numbers are the shortest distances in the graph that the flow leaves: each arrow with room keeps `x_i ≤ x_j + w`, and each arrow
with flow also keeps `x_j ≤ x_i − w`. The distances satisfy every rule, with equality exactly where the flow runs, and this makes
them the best numbers. They are whole numbers. Then `compute_levels` moves them so that the most common casing position is 0 (the
ground).

## The flow algorithm

`roadstyle-levels::flow` is a minimum-cost flow with whole numbers, by the **primal-dual** method:

1. Each node has a potential. With it, every arrow gets a reduced cost that is not negative.
2. A Dijkstra search on the reduced costs, from the nodes that still have flow to send, finds the cheapest paths.
3. A maximum flow along the arrows of reduced cost 0 sends as much as these paths can carry.
4. The potentials grow by the distances, and the method repeats until all flow is sent.

The costs of the levels are small (0, −1 and the span), so there are few rounds. When some numbers are fixed, their arrows have
negative costs, and a Bellman-Ford search gives the first potentials.

## The checks

- **The flow** is checked against its potentials (complementary slackness): the two agree only when the flow is the cheapest one.
- **The answer** is checked against every hard rule: each casing part not over its fill, the heads of roads that meet, the fixed
  numbers and the box. A failure is an error, never a quiet result.
- **A loop of hard rules** (a negative loop with no soft arrow in it) has no solution. It is an error that names it.

The solver returns the numbers, the best value of each stage (the steps by which stack rules, order wishes and near rules are
broken, and the cost of the last stage), and the pairs that it did not keep. `compute_levels` gives these pairs as
`levels_given_up` (the stacks) and `levels_orders_not_kept` (the order wishes).

## Examples from the tests

| Test (`roadstyle-levels::solve`) | The rules | The result |
|---|---|---|
| `a_bridge_over_a_road` | one stack: the bridge's main casing over the road | the casing over the road's fill, the bridge's fill over its casing; nothing broken |
| `four_bands_in_three_numbers` | four roads that cross at one point, each over all below it, in a box of 3 numbers (0, 1, 2) | one stack pair gives way: the stack stage breaks 1 step |
| `a_ring_of_wishes_cannot_all_hold` | three roads in a ring, each wished over the next one | one wish breaks; the order stage breaks 3 steps |

**See also:** [Which road is on top](../guides/levels.md) (how to use the levels) ·
[Inputs and outputs](../reference/formats.md#the-level-data) (the level columns) ·
[Architecture of the Rust version](architecture.md)
