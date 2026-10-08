# Divided casing and one band

**Status:** the solver part is in `compute_levels` and the renderer draws the divided casing (section 9). The code has no known difference from this page. This page is the specification of the drawing order: the words, the model, the input
and output, the renderer, and the simple `tags` method.

## Words

**Data**

| Word | Meaning |
|---|---|
| **edge** | one row of the input table: one line with one direction |
| **road** | one segment, both of its directions together (same end nodes, same vertices). The model works on roads; the result is copied to every edge of the road |
| **node** | the first or the last vertex of a line, compared by exact coordinates |
| **meet** | two roads meet when they share a node |
| **near** | two roads are near when they are within `band_dist` metres. Roads that meet, and roads that cross, are near (distance 0) |
| **level** | the integer from the tags of a road: the `layer` number, else bridge 1, tunnel −1, else 0 |
| **band** | the integer of a road that decides over and under: a higher band is over a lower band. It is the column `band_col`, or the level when `band_col` is not given |
| **order** | the number of a road (the column `order`, the road-class order, or the priority order: roundabout, tunnel, bridge, then class): where roads meet, the road with the higher order should have the later fill |

**Painting**

| Word | Meaning |
|---|---|
| **casing** | the outline of a road. **Fill**: its colour |
| **casing number**, **fill number** | when the casing, and when the fill, is painted. A higher number is painted later and lies on top. At the same number, all casings are painted before all fills. Each road has one fill number and three casing numbers (a head at each end and a main part) |
| **head** | the first or last `head_m` metres of a road: the part at a node. **Main**: the rest of the road |
| **short road** | a road shorter than `2 · head_m`: it is only a head |
| **ground** | the number 0: the casing number that most roads have |
| **cap** | the shape of the end of a drawn line, round or flat. It is how one line is painted, not an extra object |
| **blob** | the extra circle added at the end of a two-way pair, to fill the notch between its two round lane ends. It is an additional part |

**Requirements** (section 5)

| Word | Meaning |
|---|---|
| **merge** | roads that meet have no outline across each other's colour: a clean junction |
| **stack** | an **upper** road is painted over a **lower** road, outline included. A **stack pair** `(upper, lower)` is a pair of near roads with different bands whose upper road is not short |
| **order wish** | where two roads of equal band meet, the one with the higher order has the later fill. A wish is kept when possible |
| **given up** | a stack pair that could not be satisfied. It is reported in `levels_given_up` |

## 1. The idea

Every road has **one fill number** and a casing in **three parts**: a head at each end and a main part in between.

```
 start node ●━━ head ━━┿━━━━━━ main ━━━━━━┿━━ head ━━● end node

 casing numbers:   a_start         a_main            a_end        one number for each part
 fill number:                         b                           one number for the road
```

- A **head** is the first or last `head_m` metres of the road (default 5 m). It lies next to a node, so it decides how the road joins the roads that meet there.
- The **main** part is the rest. It decides how the road lies over or under the roads near it.

Why: at a junction the casing must not be painted over the colour of the roads that meet there (a clean junction). Along its body, an upper road must be painted over a lower road, outline included.
With one casing number a road that does both has a contradiction. With a head and a main part it does not: the heads join, the main part lies over.

The numbers are found by an optimization (section 7). Its main step is solved as a minimum-cost flow, which is fast on large networks (section 7.5.1).

## 2. The band

Every road has one **band**, an integer. A higher band is over a lower band.

- If `band_col` is given, the band of a road is that column.
- If not, the band is the level from the tags: the `layer` number, else bridge 1, tunnel −1, else 0.

The two sources are never mixed. The algorithm sees only the band.

## 3. Pairs of roads

Two roads are in one of four cases. Each case gets its own constraints (section 5).

| Case | The two roads | What applies |
|---|---|---|
| **meet** | share a node | **Q2** Merge, always. Also **Q4** (the order wish) if their bands are equal and their order numbers differ |
| **cross** | their lines cross and they share no node | **Q3** Stack, if their bands differ and the upper road is not short (section 6) |
| **near** | are within `band_dist` metres (default 10), share no node and do not cross | **Q3** Stack, if their bands differ and the upper road is not short (section 6) |
| **not related** | none of the above | nothing |

The road with the higher band is the **upper** road of a Stack pair. Roads that meet are also within `band_dist` (distance 0), so a pair that meets and has different bands gets **Q3 as well as Q2**.
This is possible because the two constraints use different parts of the casing.

Which part answers to what:

| Part of the road | Answers to | Uses |
|---|---|---|
| **head** | Merge, and the order wish | the head's casing number and the fill number |
| **main** | Stack | the main part's casing number and the fill number |

The fill is one number for the whole road. An order wish exists only between meeting roads with **equal bands**, and a stack pair always has **different** bands. So a wish and a Stack never concern the same pair, and the order
never competes with the band. A failed wish (`order_violations`) can only come from wishes that contradict each other through other constraints.

## 4. The numbers of a road

| Number | For | Range |
|---|---|---|
| `b` | the fill of the road | real numbers from `0` to `2 · max_level` (whole numbers in practice, section 7.6) |
| `a_start`, `a_main`, `a_end` | the casing parts of a road with length ≥ `2 · head_m` | the same |
| `a` | the whole casing of a **short** road (length < `2 · head_m`), used at both its nodes | the same |
| `s` | one per stack pair: the amount by which Q3 is violated (0 = kept) | real, ≥ 0 |
| `t` | one per order pair: the amount by which Q4 is violated (0 = kept) | real, ≥ 0 |

`a@v` means the casing number of a road at its node `v`: `a_start` at the start node, `a_end` at the end node, `a` for a short road. A road that starts and ends at the same node uses both heads at that node.

## 5. Constraints

A casing is painted before the fills of the same number, so "casing number ≤ fill number" means "not painted after".

| | Case | Constraint | Meaning |
|---|---|---|---|
| **Q1** | every road (not a pair) | every casing number ≤ its own fill number `b` | a casing is not painted after its own fill. **The heads must stay low:** a head is at a node, so it is also limited by Q2 and cannot be stacked over a lower road |
| **Q2** | **meet**: roads `x` and `y` share a node `v` | `a_x@v ≤ b_y` and `a_y@v ≤ b_x`, for each shared node | **Merge:** the head of one road is not painted after the fill of the other |
| **Q3** | **cross** or **near**, bands differ: `u` is the upper road, `l` the lower | `b_l + δ ≤ a_main_u`, unless the pair is given up. Only for a long upper road (section 6) | **Stack:** the upper road's main casing is painted after the lower road's fill. Only the main part is stacked, because the heads must stay low (Q1). A **meet** pair with different bands gets Q3 too |
| **Q4** | **meet**, bands equal: `x` has a higher order number than `y` | `b_x ≥ b_y + δ`, unless the wish is not kept | the road with the higher order has the later fill |

**Not related:** no constraint.

How the optimization treats the requirements (section 7):

| Requirement | In the optimization |
|---|---|
| **Q1** a casing is not after its own fill | a hard constraint (H1) |
| **Q2** Merge at a meeting | a hard constraint (H2): it is never given up |
| **Q3** Stack | a **penalty** in the objective (T1): the amount by which Q3 is violated is penalised, so Q3 is kept whenever the other constraints allow |
| **Q4** the order wish | a **penalty** in the objective (T2): the amount by which Q4 is violated is penalised |

A requirement is what the drawing needs. A constraint (H) or a penalty term (T) is how the optimization model expresses it. The names are different on purpose.

**Why the heads must stay low (Q1, Q2), and why Q3 stacks only the main part.** A head is at a node, where the upper road joins the roads that meet there, and Q2 says its casing must not be painted after their colours. A head that was also stacked
over the lower road would have to be high, and then every road at that node would have to be high too. So the heads stay low and only the main part goes over the lower road.
Written for a head too, `b_l + δ ≤ a_head_u` would contradict Q2. Example: the head of a bridge `u` joins a ground road `y` (fill `b_y = 0`), and a ground road `l` passes under the bridge (fill `b_l = 0`).
Stack on the head needs `a_head_u ≥ 1`; Merge at the node needs `a_head_u ≤ b_y = 0`. Both hold only if `b_y ≥ 1`: the ground road `y` would have to be raised above `l`, although `y` and `l` are not related.
So on a head, Merge wins and Stack is not written.

The cost: a crossing or near stretch that lies inside a head (within `head_m` of a node) is not stacked (open point 2).

What follows from them:
- A road can be high in its middle and still join the roads at its ends. A bridge in one edge needs no ramp pieces, and the roads under it are not pushed down.
- Q3 and Q1 together give `b_u > b_l`: the upper road's fill is painted after the lower road's fill.

## 6. Short roads

A road shorter than `2 · head_m` has no main part. Its whole casing is one head, with one number used at both nodes.
Such a road can be the **lower** road of a pair, but it is never stacked **over** another road, because it has no main casing to put over it. So a pair whose upper road is short is **not a stack pair**:
it gets no Q3, it is not counted as given up, and it is not reported as a failure. Merge (Q2) still holds for it if the roads meet.

The number of such pairs is reported separately, as `short_upper_pairs` in `levels_info`, so it is visible. Cost of the rule: a short road that really needs to lie over another road
(for example a 3 m bridge over a road) gets no stack.

## 7. The optimization problem

The model is **one linear program** with real variables and **one objective** `Z`. Section 5 lists the **requirements** Q1–Q4 of the drawing. The model expresses them as **hard constraints**
H1–H4 and as the terms T1–T3 of `Z`. How the program is solved is section 7.5. Q1 and Q2 are hard constraints. Q3 and Q4 are penalties, written with non-negative slack variables.

### 7.1 Data and sets

```
R   the roads                                          (both directions of a segment are one road)
C   the casing parts: for a road r with length ≥ 2 · head_m  (r, start), (r, main), (r, end);   for a short road  (r, whole)
M   the meetings: (x, y, v) with x ≠ y, roads x and y share the node v
P   the stack pairs: (u, l)  with  u, l ∈ R,  distance(u, l) ≤ band_dist,  band(u) > band(l),  length(u) ≥ 2 · head_m
O   the order pairs: (x, y)  with  x ≠ y, x and y share a node,  band(x) = band(y),  order(x) > order(y)
```

`road(c)` is the road that casing part `c` belongs to. `a_(x@v)` is the casing part of road `x` at its node `v` (its start head, its end head, or its whole casing if it is short). Pairs with a short upper road are not in `P` (section 6).

### 7.2 Variables

All variables are **real numbers**.

```
b_r          fill number of road r                       in [0, 2L],  L = max_level        for every r ∈ R
a_c          casing number of casing part c              in [0, 2L]                        for every c ∈ C
s_p          violation of Q3 for the stack pair p        s_p ≥ 0                           for every p ∈ P
t_k          violation of Q4 for the order pair k        t_k ≥ 0                           for every k ∈ O
```

### 7.3 The model

The requirements say "painted after", which is a strict inequality. With real numbers it becomes "painted at least **δ** after", where `δ` is the parameter `margin` (default 1). The margin only fixes the scale: only the order of the numbers matters, and any
positive margin gives the same order.

```
minimise    Z  =  W1 · T1  +  W2 · T2  +  T3

    T1  =  Σ_{p ∈ P} s_p                                   total violation of Q3
    T2  =  Σ_{k ∈ O} t_k                                   total violation of Q4
    T3  =  Σ_{c ∈ C} ( b_road(c) − a_c )                    compaction: the casings close to their fills

    W2  =  |C| · 2L + 1                                     W2 · (one unit of T2) is more than the whole range of T3
    W1  =  W2 · |O| · (2L + δ) + 1                          W1 · (one unit of T1) is more than the whole range of W2 · T2 + T3

subject to
    H1    a_c  ≤  b_road(c)                                        for every c ∈ C                      (Q1)
    H2    a_(x@v)  ≤  b_y     and     a_(y@v)  ≤  b_x               for every meeting (x, y, v) ∈ M       (Q2)
    H3    b_l + δ − s_p  ≤  a_(u, main)                             for every stack pair p = (u, l) ∈ P   (Q3, with slack)
    H4    b_y + δ − t_k  ≤  b_x                                     for every order pair k = (x, y) ∈ O   (Q4, with slack)

    0 ≤ b_r, a_c ≤ 2L;      s_p, t_k ≥ 0
```

This is one objective (`T4` and `W4` below are there unless `min_positions=False`, section 7.3.1). The weights make it a strict priority: any solution with a smaller T1 is better than any with a larger T1 whatever T2 and T3 are; with equal T1, a smaller T2 wins; then T3.
When nothing needs to be violated, `s = t = 0` and `Z = T3`: the stage 0 of section 7.5.

The weights are of the order of 10¹⁴ on a large network, too large for a floating-point solver. The code therefore gets the same optimum in stages (section 7.5): the smallest T1; then the smallest T2 with T1 held; then the smallest T3 with both held.

#### 7.3.1 Fewest positions (`min_positions`, on by default)

A position is a value that some casing or fill number takes; the page has a set of layers for each position. Without a term for it, the number of positions is not minimised by the model above: only `T3` is. The option `min_positions` (**on by default**) adds a fourth term, the **span** of the numbers, which is a linear stand-in for the number of positions
(the numbers are integers, so there are at most `span + 1` distinct values):

```
minimise    Z  =  W1 · T1  +  W2 · T2  +  W4 · T4  +  T3

    T4  =  H − L                                          the span: the highest number minus the lowest
    W4  =  ( Σ of the positive cost coefficients of T3 ) · 2L + 1       W4 · (one unit of T4) is more than the whole range of T3

with two more variables H and L, and the rows
    x_v  ≤  H      and      L  ≤  x_v          for every variable x_v (every fill and casing number)
    0 ≤ H, L ≤ 2L
```

The priority is `T1`, then `T2`, then the span `T4`, then `T3`. So the option never gives up a stack or an order wish to save a position, but it does trade compaction (`T3`) for fewer positions: the casings may lie a little farther from their fills.
The new rows have the form `x_i − x_j ≤ 0`, like all the others, so stage 0 is still a minimum-cost flow (section 7.5.1); `H` and `L` have supplies `+W4` and `−W4`, and the cost coefficients still sum to 0. In the stages 1–3 the term `W4 · T4` is part of the cost of stage 3 (`T3` is minimised together with it).
The two variables are linked to every other variable. That can make the flow harder or easier: the time is about the same as without the term on most networks, a few times longer on some, and shorter on a very large one. `min_positions=False` leaves the term out: the model of 7.3 with `W4 = 0`.

### 7.4 Requirements, constraints and the terms of the objective

| Requirement | Treated as | Constraint | Term of the objective |
|---|---|---|---|
| **Q1** casing not after its own fill | hard constraint | **H1** | none (T3 measures the distance that H1 keeps non-negative) |
| **Q2** Merge at a meeting | hard constraint, never relaxed | **H2** | none |
| **Q3** Stack | **penalty** | **H3**, relaxed by the slack `s_p` | **T1** = `Σ s_p` |
| **Q4** the order wish | **penalty** | **H4**, relaxed by the slack `t_k` | **T2** = `Σ t_k` |
| not a requirement: ranges as short as possible | preference | none | **T3** |

**Q2 has no term of its own.** It is never relaxed, so Merge always holds. It appears in the objective only by limiting what T3 can reach (a head cannot be above the fill of the road it meets).

**What a slack means.** H3 says `a_(u,main) − b_l ≥ δ − s_p`. If `s_p = 0` the stack is kept with the full margin. If `0 < s_p < δ` the order is still kept (the upper casing is still after the lower fill), only with a smaller margin.
If `s_p ≥ δ` the upper casing is **not after** the lower fill: Q3 is violated and the pair is **given up**. `t_k` works the same way for Q4.

**The penalty counts the amount, not the number.** T1 is the total amount of violation. Where a conflict exists, the solution has the smallest total violation. This differs from "the fewest pairs given up", which is a harder
combinatorial problem.

### 7.5 Solving

The problem of 7.3 is one linear program with the one objective `Z`. It is solved in steps, by what is needed, and each step has one solver.

| Step | What is solved | Solver | When |
|---|---|---|---|
| **Stage 0** | the program without slack variables (`s = t = 0`, `Z = T3`) | **minimum-cost flow** (OR-tools), section 7.5.1 | always tried first |
| Stage 0, not certified | the same program, with the bounds | **HiGHS** (7.5.3) | the flow cannot certify its answer (list in 7.5.1) |
| **Stage 1** | minimise T1 | **HiGHS** | only when stage 0 has no solution |
| **Stage 2** | minimise T2, with `Σ s_p ≤ T1*` | **HiGHS** | same |
| **Stage 3** | minimise T3, with `Σ s_p ≤ T1*` and `Σ t_k ≤ T2*` | **HiGHS** | same |

`levels_info["solver"]` says `flow` when stage 0 was solved by the flow and `highs` otherwise. If stage 0 has a solution, nothing is violated and nothing is given up. If it has none, the stages 1–3 find the optimum of `Z`: the weights `W1`, `W2` of 7.3 only express a priority,
and they are too large for a floating-point solver, so the three terms are minimised one after the other, each with the earlier ones held at their optimum (`T1*`, `T2*`, with a small tolerance). The optimum is the same as that of `Z`.

#### 7.5.1 Stage 0 as a minimum-cost flow

**In words.** All the rows of the program say the same kind of thing: *"this number is at most that number plus a constant"*. A program made only of such rows has a twin problem in graph form: how to send goods through a network at the smallest cost, a **minimum-cost flow**.
A flow solver is much faster than a general solver, and from its answer the numbers of the roads are read back with a shortest-path pass.

**The two programs side by side.** Every row of the program has the form `x_i − x_j ≤ c` (a number is at most another number plus `c`; here `c` is 0, or `−δ` for Stack and the order wish, and with the default `δ = 1` it is an integer), and the cost coefficients are integers that sum to 0
(`T3` is the sum of `b − a`: each fill gets `+1` and each casing `−1`).

```
the program (what we want)                            the flow (its twin)

minimise    Σ_v  cost_v · x_v                         minimise    Σ_rows  c · f_row
subject to  x_i − x_j ≤ c        for each row          subject to  f_row ≥ 0               for each row
                                                                   (what leaves a node) − (what enters it) = − cost_v

one number x_v for each variable                      one node for each variable;  one arc  i → j  of cost c  for each row (i, j)
```

Each row becomes an arc from `i` to `j` with cost `c`. A node `v` has a **supply** of `−cost_v` units: a node with supply `+1` sends one unit out, a node with supply `−1` takes one unit in. The flow `f_row` is how much runs on the arc. Whatever the program's optimal value is,
the flow's optimal value is its negative (this is the duality of linear programming). The arcs have no upper limit on the flow (in the code: more than the total supply).

**A small example.** An upper road `u` over a lower road `l`. Variables: the casing `a_u` and fill `b_u` of `u`, the casing `a_l` and fill `b_l` of `l`. Rows: `a_u ≤ b_u` (H1), `a_l ≤ b_l` (H1), and Stack `b_l + 1 ≤ a_u` (H3 with `δ = 1`). The objective is `(b_u − a_u) + (b_l − a_l)`.

```
rows                          arcs (i → j, cost c)        supplies (− cost)
a_u − b_u ≤  0                a_u → b_u,   0              a_u: +1   b_u: −1
a_l − b_l ≤  0                a_l → b_l,   0              a_l: +1   b_l: −1
b_l − a_u ≤ −1                b_l → a_u,  −1
```

The flow: `a_u` sends its unit to `b_u` over the first arc, `a_l` sends its unit to `b_l` over the second. Both arcs cost 0, so the flow costs 0, and so the program's optimum is 0: both casings sit exactly at their own fills.

**From the flow back to the numbers.** The flow tells which rows are *tight* (the arcs that carry flow). The numbers are then read off a graph of distances:

1. Take a new node `Z` and an arc `Z → v` of cost 0 to every variable.
2. For every row `x_i − x_j ≤ c` an arc `j → i` of cost `c` (the row says `x_i` is at most `x_j + c`).
3. For every row that carries flow, also an arc `i → j` of cost `−c` (the row is tight: `x_i = x_j + c`).
4. `x_v` is the shortest distance from `Z` to `v`. It is found by relaxing all arcs at once, over and over (vectorised), until no distance changes.
5. The numbers are shifted so that the lowest is 0.

Such an `x` satisfies every row, with equality exactly where the flow runs. By complementary slackness this makes it an optimal solution of the program. All numbers are integers.

In the example: the arcs are `b_u → a_u` (0) and `a_u → b_u` (0), `b_l → a_l` (0) and `a_l → b_l` (0), and `a_u → b_l` (−1), plus `Z` to all (0). The distances are `a_u = 0`, `b_u = 0`, `b_l = −1` (through `a_u`), `a_l = −1`. After the shift: `a_l = b_l = 0` and `a_u = b_u = 1`: the upper road is painted after the lower one, as Stack asks.

**The bounds** `0 ≤ x ≤ 2 · max_level` are not in the flow. Shifting `x` does not change the cost, so the lowest value is 0, and the bound that can matter is the highest value. It is checked after the relaxation.

**Checks.** The solution is checked against every row (an error if one fails: it would be a bug). The flow **cannot certify** its answer, and HiGHS solves the program instead, when:
the flow has no solution (the program has no bounded optimum without its bounds); an arc of the flow is saturated (a negative cycle: the rows have no solution); the data are not integers (for example a `margin` that is not an integer); a variable with a cost is in no row;
the relaxation does not converge in `n + 2` rounds; or the highest value is above `2 · max_level`.

**Why the flow, and why only for stage 0.** A flow solver uses the structure of the rows and is much faster than a general solver on this size. The stages 1–3 stay with HiGHS because their conditions "T1 held at its optimum" and "T2 held" are rows with many variables, not of the form `x_i − x_j ≤ c`, so they are not a flow.
One weighted flow with the weights `W1`, `W2` of 7.3 is possible in principle (a slack becomes a capacity), but the weights reach 10¹⁴ on a large network, and the integer arithmetic of the flow solver (costs times the number of nodes) overflows. The stages 1–3 are only needed when requirements truly conflict, which is rare.

**Several optima.** The program often has several optimal solutions; the flow returns one of them and HiGHS another. The cost is the same; the numbers can differ in a few roads; the drawing satisfies the same requirements.

#### 7.5.2 The preparation

Before any solver, the data are prepared with arrays, not loops over geometries: the end points of all edges are numbered by exact equality (`numpy.unique` on the coordinates), two edges are one road when their end nodes and their vertices, in one direction or the other, are the same,
the lengths and the bands come from columns, and the near pairs from one `STRtree` query. The rows of the program are then built from these.

#### 7.5.3 HiGHS

HiGHS **interior point** with crossover, through `scipy.optimize.linprog(method="highs-ipm")`, on a sparse matrix. `time_limit` is passed to HiGHS. A solve that is not optimal raises an error. The interior point is used because the dual simplex stalls on large networks. Crossover ends at a vertex, so the numbers are still integers.

#### 7.5.4 Bounds and the ground

The variables are non-negative, with an upper limit of `2 · max_level`. The lower bound pins the lowest number at 0 (the cost does not change if every number is shifted by the same amount), so the solver returns the lowest layering.
Afterwards the numbers are shifted so that the casing number most roads have is 0, the ground (tunnels then get negative numbers).

### 7.6 The numbers

Every constraint compares two variables (`x − y ≤ c`), and the constants are `0` and `−δ`. Such a system has a vertex solution whose values are multiples of `δ`, and the simplex method returns a vertex. With the default `δ = 1` the numbers are integers.
After solving, the values are rounded to 6 decimals. If any value is not within 10⁻⁶ of an integer (for example with `δ = 0.5`), the values are only ranked: equal values share a position.

### 7.7 What "given up" means

A stack pair is **given up** when `s_p ≥ δ · (1 − 10⁻⁶)`: Q3 is violated for it. An order wish is **not kept** when `t_k ≥ δ · (1 − 10⁻⁶)`. Pairs with a short upper road are not in `P`; they are counted separately as `short_upper_pairs`.
Without any violation (stage 0) nothing is given up.

## 8. Input and output

```python
rs.compute_levels(edges, method="solve", band_col=None, order=None, band_dist=10.0, head_m=5.0, max_level=20, margin=1.0, time_limit=60.0)
```

### Input

**Data** (what the function reads):

| Argument | What to give | Needed |
|---|---|---|
| `edges` | GeoDataFrame of road lines (LineString), any CRS; both directions of a road may be present | always |
| `band_col` | name of a column of integers (null = 0): the band of each road. If not given, the band is calculated from the tag columns below | optional |
| `layer_col`, `bridge_col`, `tunnel_col` | names of the OSM tag columns (defaults `layer`, `bridge`, `tunnel`), read for the band when `band_col` is not given, and for `order="priority"` | optional |
| `order` | name of a column of numbers, `"class"` (the road-class order), or `"priority"` (roundabouts, then tunnels, then bridges, then the road-class order; the default of `render_edges`): the higher number wins where roads meet. A road with no number (null; for `"class"`, no `highway`) takes **no part in the order**: no wish is made for it, with any road | optional |
| `highway_col` | name of the road-class column (default `highway`), read only for `order="class"` and `"priority"` | optional |
| `junction_col` | name of the OSM `junction` column (default `junction`), read only for `order="priority"`: `roundabout` or `circular` is a roundabout. A missing column means no roundabouts | optional |

**Settings** (how it runs):

| Argument | Default | Meaning |
|---|---|---|
| `method` | `"solve"` | `"solve"` is the algorithm of this page. `"tags"` is the closed-form rule of section 10 (it ignores `band_col` and `order`) |
| `band_dist` | 10 | metres: two roads closer than this, with different bands, are a stack pair |
| `head_m` | 5.0 | metres: the length of each head; a road shorter than `2 · head_m` is one head |
| `max_level` | 20 | the range of the numbers: every casing and fill number is in `[0, 2 · max_level]` before the shift to the ground. A stack deeper than `2 · max_level / margin + 1` positions cannot be satisfied: the extra pairs are given up |
| `margin` | 1.0 | `δ`: how much later a road must be painted where one must be painted after another. Only the order of the numbers matters, so it changes the scale and nothing else (with the range: the number of positions that fit). Must be greater than 0 |
| `min_positions` | True | the span term of 7.3.1: fewer positions (layers) in the page, a little less compaction; `False` leaves it out |
| `near_rules` | False | also lift the parts of a stack pair's upper road that only come near the lower one, as last-priority rules (off by default since 2026-10-08; an input of `level_input` / make since 2026-10-08, written as `near` rows, see `level_input.md`) |
| `time_limit` | 60 | seconds for each LP solve |

### Output

The same table as `edges` (same rows, order, index and columns) with four integer columns added. The input is not changed.

| Column | Meaning |
|---|---|
| `casing_start` | casing number of the start head |
| `casing_level` | casing number of the main part (the one the renderer draws today) |
| `casing_end` | casing number of the end head |
| `fill_level` | the fill number |

A short road has the same number in the three casing columns. The two directions of a road share the road's numbers, but `casing_start` belongs to the first vertex of the row's own geometry: the reversed direction has `casing_start` and `casing_end` swapped. The numbers are a ranking: a higher number is painted later. The casing number
that most roads have is 0 (the ground).

Two notes are also set in `result.attrs`:

| Key | Content |
|---|---|
| `levels_given_up` | list of `(upper_row, lower_row)`: the stack pairs given up (`s ≥ δ`), as row positions in the table, counted from 0. A warning is also shown when the list is not empty |
| `levels_info` | dict: `pairs` (stack pairs, the set `P`), `roads`, `short_roads` (shorter than `2 · head_m`), `short_upper_pairs` (near pairs with different bands whose upper road is short: not stack pairs, section 6), `order_pairs`, `order_violations` (order wishes not kept), `solves` (number of problems solved: 1 when nothing is violated, else 4; 0 when there is nothing to solve), `solver` (`flow`: stage 0 solved as a minimum-cost flow; `highs`: by HiGHS, section 7.5), `status` (`OPTIMAL`), `seconds` |

## 9. The renderer

The web renderer draws the divided casing. The code is in `render_web.py` (`_mark_levels`, `_casing_parts`, `_level_layers`, `_twin_ends`).

### 9.1 Input

```python
rs.render_edges(edges, casing_level_col="casing_level", fill_level_col="fill_level",
                casing_start_col="casing_start", casing_end_col="casing_end", head_m=5.0)
```

| Argument | Default | Meaning |
|---|---|---|
| `casing_level_col` | `None` | column of the casing number of the **main** part |
| `fill_level_col` | `None` | column of the fill number |
| `casing_start_col`, `casing_end_col` | `None` | columns of the casing numbers of the start head and the end head. A column that is not given counts as the main number |
| `head_m` | 5.0 | the length of each head in metres. Use the value given to `compute_levels` |

The numbers are read as follows: an empty or non-numeric value is 0, a float is rounded to an integer, the main casing number is never above the fill number (if it is, the two are swapped), and a head number
is never above the fill number (it is lowered to it). The page has one pair of layers for each position that occurs in any of the four columns.

The heads are drawn only when `casing_start_col` or `casing_end_col` is given. Without them the casing is one line per edge at the main number, as before. `tiles=True` works with them (section 12.1).

### 9.2 The pieces of a casing

The fill is **one line per edge**, in the source `roads`, at its fill number. The casing comes from its **own source, `casings`**, as pieces:

| Edge | Casing pieces |
|---|---|
| a LineString of length ≥ `2 · head_m` whose three casing numbers are not all equal | **three**: the first `head_m` metres at the start number, the middle at the main number, the last `head_m` metres at the end number |
| a LineString shorter than `2 · head_m` whose three numbers are not all equal | **two**: the first half at the start number, the second half at the end number (`short_road_heads.md`) |
| a LineString whose three numbers are equal | **one**, the whole edge |
| any other geometry | **one**, as it is |

How the cut is made: the line is projected to local metres (`x · 111320 · cos(latitude)`, `y · 111320`), cut at `head_m` from each end, and projected back; coordinates are rounded to 7 decimals. A piece that
comes out empty is dropped.

**The ends of the pieces.** The line ends are round everywhere in roadstyle, because a round end seals the seam where two roads meet. In the divided casing the **main** piece ends at two cuts, not at a node. Its ends are
**flat (butt)**: a round end there would reach into the head zone by half the casing width (a fixed number of pixels, many metres when zoomed out), and the main piece is painted above the heads, so the round end could cover the
fill of a road that meets at the node. The **heads** and the unsplit casings keep **round** ends: a head is painted low, so it cannot cover a neighbour's fill. The flat ends use the existing flat-end layers of `cap_col`
(`roads-casing-sq`): the main piece carries `__rs_cap = true`. The cost is a small gap at the cut where the road bends sharply.

A piece carries the properties that the casing layers read: every `__rs_*` property except the fills, the road-class column, the filter column, the metre-width column, and `lvl`; its own casing number as
`__rs_cl`; and `__rs_road`, the id of its edge (the index of the edge in the data). Popup columns are not copied, so the source is small: about one piece more than edges.

`casing_start` belongs to the **first vertex of the edge's own geometry**, and `casing_end` to its last. The two directions of a road run opposite ways, so `compute_levels` gives the reversed direction its two head numbers swapped.

### 9.3 The layers and their order

For every position `p`, in ascending order, the page has these layers, in this order:

| Order | Layer | Source | Draws | Filter |
|---|---|---|---|---|
| 1 | blob casing `roads-ends-casing` (`-lv<p>` for `p ≠ 0`) | `ends` | the round casing at the ends of two-way pairs | `__rs_cl == p` |
| 2 | casing layers `roads-casing`, `-sq`, `-dash`, and `roads-casing-bridge` for bridges (`-lv<p>`) | **`casings`** | the casing pieces; `-sq` (flat ends) draws the main pieces, the others are round | `__rs_cl == p` |
| 3 | fill layers `roads-fill`, `-sq`, `-pat`, `-dash<n>` (`-lv<p>`); the blob fill `roads-ends-fill` just before `roads-fill` | `roads`, `ends` | the fills | `__rs_fl == p` |
| 4 | arrows `roads-arrows` (`-lv<p>`) | `slots` | one-way arrows | `fl == p` |
| 5 | names `roads-labels` (`-lv<p>`) | `slots` | street names | `fl == p` |

So at every position **all casings are painted first, then all fills**, and a higher position is painted over a lower one. Within a layer the order is not defined: the sort key is the constant 0. The
road class, `layer`, `bridge` and `tunnel` do not order anything (they are inputs of the solver, section 12).

**Twin end blobs.** A two-way road is drawn as two lanes. Where a plain pair ends at a node, the two round lane ends leave a notch, and a **twin end blob** (a circle centred on the node, wide as both lanes) fills it.
The blob is an extra drawing added at the end of the pair, not a change of the lines. It has a casing ring and a fill circle:

| Part of the blob | Painted at | Why |
|---|---|---|
| fill circle | the fill number of the road (one number for both lanes) | the same as the lanes' fills |
| casing ring | the **head** number at that node: `casing_start` or `casing_end` of the lane that ends there | the ring sticks out past the node, like a head, so it must be low like the head. At the main number it could cover the fill of a road that meets at the node |

The ring is hidden where another road at that node has a fill number **below the head number**, because the ring would then cut across that road.

Which pairs get a blob: only plain pairs with round ends. A bridge, a tunnel, a dashed class, and a pair drawn flat with `cap_col` get none. At the cuts of a divided casing there is no blob: no two lanes end side by side there.

**Bridges.** The bridge look is drawn in the casing of its position: for every position that has a bridge edge there is one more casing layer, `roads-casing-bridge` (`-lv<p>`), from the same source as the other casing
layers. It draws the casing pieces of the edges tagged `bridge` with the bridge casing colour (black by default, `bridge_casing_color`), the heavier bridge width and flat ends. The other casing layers leave bridge edges to it.
A bridge is still painted at its own numbers; the fill is the normal fill.

**Layers that exist but draw nothing in this mode:** the low, high and bridge band layers (their filters match nothing). The 3D bridge decks of `view_3d` are a separate shape and still follow the tags.

### 9.4 The page

- **Colour by, rsColor:** they recolour the fill layers of every position. The casing keeps its palette colour.
- **Class filter and queries:** the class filter applies to the casing layers too. A query by road id also hides the casing pieces of the hidden edges (through `__rs_road`).
- **Hover and selection:** they work on the `roads` source (the fill line), not on the casing pieces.
- **`rsColor` lift:** it raises only the fill of the coloured roads within their position. The casing pieces are not lifted.

## 10. The `tags` method

`compute_levels(method="tags")` (not the default) is a closed-form rule on the tags and on which roads share a node. No search, no solver, O(number of edges). It ignores `band_col` and `order` and raises an error if they are given.

**Level of a road, `L(r)`:** the `layer` number if it is a non-zero number, else bridge = 1, tunnel = −1, else 0. (`bridge` and `tunnel` are true unless null, `NaN`, `""`, `"no"`, `"false"`, `"0"`, `0` or `False`.)

**Level of a node, `N(v)`:** let `S(v)` be the levels of the roads that end at the node `v`. `N(v)` is the value in `[min S(v), max S(v)]` nearest to 0:

```
N(v) = min( max(0, min S(v)), max S(v) )
```

So a node where a ground road ends, or where one road going up and one going down end, is 0; otherwise it takes the level nearest the ground.

**The numbers of a road:**

```
casing = min( N(start), N(end), L )          the three casing numbers are equal
fill   = max( N(start), N(end), L )
```

**Example** (bundled sample `notebooks/data/sodermalm_edges.gpkg`, rows counted from 0): one direction along Centralbron in Stockholm, the bridge, then the Söderledstunneln tunnel, then a ground road.

| Row | Edge | `L` | Casing | Fill | Why |
|---|---|---|---|---|---|
| 2134 | Centralbron, bridge, 132 m | 1 | 1 | 1 | only bridge edges end at both nodes: `N = 1` |
| 828 | Centralbron, bridge, 132 m | 1 | 0 | 1 | a tunnel edge also ends at its end node (levels 1 and −1): `N = 0` |
| 1558 | Söderledstunneln, `layer=-1`, 180 m | −1 | −1 | 0 | its start node is that same node: `N = 0` |
| 440 | Söderledstunneln, `layer=-2`, 652 m | −2 | −2 | −1 | edges of levels −1 and −2 end at the node it shares with row 1558: `N = −1` |
| 2219 | Söderledstunneln, `layer=-2`, 578 m | −2 | −2 | −1 | both nodes are at −1 |
| 2469 | Söderledstunneln, `layer=-2`, 185 m | −2 | −2 | 0 | a ground road ends at its end node: `N = 0` |
| 2468 | Söderleden, ground, 29 m | 0 | 0 | 0 | a ground road is always `[0, 0]` |

**Why Merge holds.** Two roads sharing the node `v` both have `N(v)` among the three values behind their numbers, so `N(v)` lies between the casing and the fill of both: neither casing is after the other's fill.

**Limits.** It sees only tagged levels, so a crossing without tags is drawn flat. A bridge stored as **one edge** from ground to ground gets casing 0 and fill `L`: its colour is over the road below, but its casing is not after that road's fill, so it has no outline over it.
Skanstullsbron in the sample is such a bridge (row 207: `[0, 3]`); with `method="solve"` its main casing is over the roads under it.

## 11. Storage in the duckOSM file

The solve takes long on a large network, so the result can be saved with the data and read back, instead of being computed at every render. The code is in `levels_store.py`; it needs the `duckdb` extra.

**Where.** In the area's own `.duckdb` file, in a new schema **`visualization`**. The schemas of a duckOSM file each hold one kind of layer (`driving`, `walking`, `cycling`: networks; `features`: OSM features; `raw`: the import). The
schema `visualization` holds layers computed for drawing.

| Table | Columns | Content |
|---|---|---|
| `visualization.edge_levels` | `edge_id` BIGINT, `casing_start`, `casing_level`, `casing_end`, `fill_level` (INTEGER) | one row for every edge, keyed by the content hash `edge_id` |
| `visualization.edge_levels_meta` | one row: `method`, `head_m`, `band_dist`, `margin`, `max_level`, `band_source`, `order_source`, `min_positions`, `n_edges`, `edge_hash`, `roadstyle_version`, `created` | what the numbers were computed with |

`band_source` is `"tags"` or the name of the `band_col`; `order_source` is the `order` argument (a column name, `"class"`, or null); `min_positions` is true, or empty when it was off.

```python
levels = rs.compute_levels(roads, method="solve", order="class")        # roads: one row per edge_id, with the edges of all modes
rs.save_levels(con, levels)                                              # con: an open, writable duckdb connection

levels = rs.load_levels(con, roads, order="class")                       # roads in any order; the expected parameters, with the names and defaults of compute_levels
table  = rs.load_levels(con, order="class")                              # without edges: the table edge_id + the four columns
```

**Rules**
- The numbers are computed on the **roads of all modes together** (one row per `edge_id`, as in mapstyle's `load_roads`), because the order depends on all of them. They are not computed per mode.
- `save_levels` takes the result of `compute_levels`, which carries its own parameters in `result.attrs["levels_params"]`, so the stored parameters cannot differ from the computation. It replaces both tables. A frame that does not come from
  `compute_levels`, or whose `edge_id` is not unique, is refused.
- Saving and reading are **explicit calls**. Nothing is written while rendering.
- `load_levels` compares the stored parameters with the ones you expect, and, if you give `edges`, the number and a hash of the `edge_id` values (`edge_hash`, over the sorted ids) with the stored ones. If anything differs, or the table does not exist, it raises a
  `ValueError` that says what differs. It **never recomputes silently**. The hash catches a changed set of edges, not a changed geometry.
- With `edges`, the result is a copy of `edges` (in its own row order) with the four columns added.

## 12. The only way of drawing

`render_edges(edges)` draws by positions and by nothing else.

- **No level columns given.** `render_edges` first calls `compute_levels(edges, method="solve", order="class", band_col=band_col)`
  (section 7) on the edges it is given, and draws the result. The result is the same as computing the columns yourself with these arguments.
- **Level columns given** (`casing_level_col`, `fill_level_col`, and the head columns). They are drawn as they are; nothing is computed.
- **Removed.** The three bands (low, ground, high), the class order (`ROAD_Z` as a draw order, `line-sort-key`), `order_col`, and the
  separate bridge layers. A road class now acts only through `order="class"` in the solver. `band_col` stays as an *input of the solver* (section 2), not as a drawing rule. `cap_col` stays.
- **scipy** and **ortools** are core dependencies of roadstyle (no extra).
- **3D (`view_3d`).** The extruded decks follow the bridge tags. Below `flat_below` the bridge is its flat line, drawn at its positions; from `flat_below` up that flat line (its casing layer and the bridge edges in the position layers) is hidden and the deck is shown.
- **Errors, no silent fallback.** If the solver finds no solution in `time_limit`, `compute_levels` raises (as in section 7.5); `render_edges` does not draw by another rule.
- **`tiles=True`** works with positions (section 12.1).
- **Time.** Computing the positions takes long on a large network. It should be computed once with `compute_levels`, saved with `save_levels`, and drawn with the columns.

### 12.1 Tiles

`tiles=True` packs the roads in one PMTiles archive (module `tiles.py`; the page reads only the tiles in view). With positions the archive has these tile layers, all in the one source `roads`:

| Tile layer | Features | Made like |
|---|---|---|
| `roads` | one line per edge (fill, arrows' edge, popups) | as before: simplified per zoom, clipped to the tile |
| `casings` | the casing pieces of section 9.2 (main piece and heads) | the same as `roads`: simplified, clipped |
| `ends` | the twin end caps (points) | whole, once, as `slots` |
| `slots` | the labels and arrows | as before |

- A layer of the page whose source was `casings` or `ends` reads the same tile layer of the source `roads` (`source-layer`). Nothing else about the layers changes: same ids, same filters, same positions.
- The pieces and caps carry the properties the layers read (`__rs_*`, the class column, `lvl`, the width column), and their edge's id as `__rs_road` / `__rs_road2`.
- The page's filters (class filter, `rsFilter`, `rsColor`) pick a layer's kind by its tile layer name when tiled (`roads`, `casings`, `ends`), by its source name when not.
- **The positions are computed for the whole network, also with tiles.** The page has one set of layers for all tiles on screen, so a number of one tile is compared with the numbers of the next tile at every border. Tiles solved one by one cannot guarantee that two roads that meet at a border have numbers in the right order: the height of a group of roads is free in each solve. So the tiles hold numbers of one solve.
- The archive grows with the pieces: the casing layer has about three features per edge. (open point 8).

## 13. Open points

1. **A short upper road.** Its pairs are not stack pairs (section 6). A short road that truly needs to lie over another road gets no stack. `short_upper_pairs` shows how many pairs this concerns.
2. **A crossing inside a head.** A crossing can lie within `head_m` of a node, where the casing is the head, not the main part. Stack as written (on the main part) is then not what is seen.
3. **Default `head_m`.** 5 m is the default. It is not a tuned value: other values were not compared at every zoom. A larger value skips more pairs (section 6).
4. **Conflicts.** With order wishes only between roads of equal bands, a conflict is rare, so stage 0 (one problem) usually succeeds. The stages 1–3 are tested only with a range that is too small.
5. **Positions in use.** The number of positions is not minimised. Only the total distance between casings and fills is (T3).
6. **Weight of a part.** Each casing part counts once in T3, whatever its length in metres.
7. **Seams.** Where the three pieces of a casing meet, the line caps could show a seam when the three numbers differ. Not checked.
8. **Tiles.** Size and opening time of a large map, tiled against inline, are not compared. MapLibre places arrows and street names per tile, so their places differ from the inline map.
