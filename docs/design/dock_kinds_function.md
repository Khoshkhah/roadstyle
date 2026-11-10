# Object kinds that change after the page starts

**Status:** 2026-11-10. Approved by the owner on 2026-11-09. Built in the same change as this note.

[Object kinds in the data dock](dock_kinds.md) and [part 2](dock_kinds_table_views.md) give the dock its `kinds` as an object. The dock reads the object one time, at start.

## Problem

A host can get a new table after the page has started. In duckOSM Studio, the person can switch on a layer, and a build can finish later. A row of the new table then has no object and no card until the person reloads the page. No kind covers the new table.

## Decision

The option `kinds` is one of two things:

| Value | What the dock does |
|---|---|
| An object `{name: kind}` | Reads it one time, as before. |
| A function `() => {name: kind}`, sync or async | Calls it at start, before each new result picks its kind, and in `data.refreshKinds()`. |

The function returns the same object that the host gave before. Nothing else changes in a kind.

## `data.refreshKinds()`

The host calls it after it changes its tables. It returns a promise.

1. It calls the function `kinds` again.
2. If the current result has asked for a kind, it picks the owner again with the coverage rule of part 2.
3. If the owner is the same (same kind, same id column, same number of objects), it does nothing: the objects are not drawn again, and the selected row and its card stay.
4. If another kind owns the result now, the dock closes the card of the old object and draws the result again.
5. A result that has roads, and a result that has not asked for a kind yet, need no work. The next result calls the function.

With an object as `kinds`, `refreshKinds()` does nothing.

The dock calls the function for each new result. The function must be cheap: it must not run a query on each call.

## Errors

If the function fails or rejects, the dock reports it with `console.error` and the event `kinderror` (`kind: "kinds"`), and the result has no owner. The dock does not keep the old kinds.

## Why a method and not an event

The host knows when it adds a table. A method is the smallest design: one call, a promise that tells when the dock is done, and no event name to learn.

## Host change

None. A host that gives an object works as before. To use the function, a host gives `kinds: () => ...` and calls `data.refreshKinds()` after it adds a table.

## Tests

`tests/test_dock_kinds_browser.py`:

- A kind that the function adds after the start owns the next result, with its note and its card.
- `refreshKinds()` lights the current result with the new kind and does not run the result again.
- With the same owner, `refreshKinds()` does not call `setData` of the layer, and the selected row and card stay.
- An object host does not change: `refreshKinds()` does nothing.
