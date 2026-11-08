// The design-edit part (docs/design/design_edit_part.md): a card in the dashboard's panel that opens roadstyle's design panel, and the glue that a host page
// needs around it. The host gives its map, its dashboard and a data adapter; the part does the card and its line of state, the layout, the restore of the saved
// design, the save, the redraw and the link to another card.
//
//   const part = designEditPart({dashboard: rs, map, data, roads, card: {id: "design", label: "Edit design"}, link: {label: "Export →", card: "export"},
//                                tabs: [tilesTab], boundary, storageKey: "mypage"});           // gives an EventTarget
//   part.open(); part.close(); part.isOpen(); part.edited; part.panel           // `panel` is the designPanel (get, setHost, text, base, ...)
//
// The adapter `data` (all of it the host's own data or worker):
//   look()              the look of the map as an object (the page's own look)
//   loadDesign()        the saved design text of the area, or null (it wins over the text that the browser kept)
//   saveDesign(text)    keeps the design text with the area (after 800 ms of quiet; a failed save is a warning)
//   setLook(text)       the host's map worker shows the look on the same tiles; gives a style, or undefined when new tiles are necessary
//   redraw(text, draw)  remembers the look text; with `draw`, draws the map again (new tiles) and gives a note
// Optional: redrawReason() gives a text when the host cannot redraw now (the level editor is open, the map is not drawn): the panel shows it.
// `roads`: the host's roadLayers(...): its prefix and `also` are the panel's restyle options. A host tab is {id, name, key, make, normalize, draw, keep, summary}:
// `summary(value)` gives the text that the card line shows after the name (the value is not part of "changed").
// Events: "change" {design, text, edited}, "close". The host listens to "close" to give its map the padding of its panel again.
import {designPanel} from "./design_panel.js";
import {changes} from "./design.js";

export async function designEditPart({dashboard = globalThis.rs, map, data, roads = null, card = {}, link = null, tabs = [], boundary = null, storageKey = "roadstyle",
                                      panel = document.getElementById("sb"), backLabel = "Steps"}) {
  for (const f of ["look", "loadDesign", "saveDesign", "setLook", "redraw"]) if (typeof data?.[f] !== "function") throw new Error(`designEditPart: data.${f}() is necessary`);
  const events = new EventTarget(), id = card.id ?? "design";
  const send = (type, detail) => events.dispatchEvent(new CustomEvent(type, { detail }));
  let edited = false, saveTimer = null;
  const note = (design) => {
    const hosts = tabs.map((t) => (t.summary && design[t.key] != null ? t.summary(design[t.key]) : "")).filter(Boolean);
    dashboard.sections.note(id, [`${design.name}${edited ? " (changed)" : ""}.`, ...hosts].join(" "));
  };
  // the style without the values of the host tabs: "changed" counts only what the panel itself edits
  const hostless = (d) => ({ ...d, ...Object.fromEntries(tabs.map((t) => [t.key, 0])) });
  const refresh = (p) => { edited = changes(hostless(p.get()), hostless(p.base())).length > 0; note(p.get()); };
  const close = () => { if (!pan?.isOpen()) return; pan.close(); map.resize(); document.body.removeAttribute("data-rs-editing"); send("close"); };
  let pan = null;
  const open = () => { pan.open(); document.body.setAttribute("data-rs-editing", "design"); };
  dashboard.sections.add({ id, label: card.label ?? "Edit design", note: card.note ?? "", icon: card.icon ?? "edit", open });
  pan = await designPanel({
    panel, dashboard, map, look: await data.look(), backLabel, storageKey, boundary, tabs,
    setLook: (text) => data.setLook(text),
    redraw: async (text, draw) => {
      const why = draw ? data.redrawReason?.() : "";
      if (why) { await data.redraw(text, false); return why; }
      return (await data.redraw(text, draw)) ?? (draw ? "The map shows this design." : "");
    },
    restyle: { also: roads?.also ?? [], imagePrefix: roads?.prefix ?? "rs-" },
    link: link && { label: link.label, onClick: () => {
      close();
      if (!dashboard.sections.get(link.card)) return;
      dashboard.sections.fold(link.card, false);
      dashboard.sections.get(link.card).scrollIntoView({ block: "nearest" });
    } },
  });
  const saved = await data.loadDesign();                                // the design of the area wins over the one that the browser kept
  if (saved && !(await pan.load(saved, { draw: false }))) console.warn("design edit part: the saved design is not a design file; it stays as it is until the person changes the design");
  refresh(pan);
  pan.addEventListener("change", (e) => {
    refresh(pan);
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => Promise.resolve(data.saveDesign(e.detail.text)).catch((err) => console.warn("design edit part: the design was not saved:", err.message)), 800);
    send("change", { ...e.detail, edited });
  });
  pan.addEventListener("back", close);
  Object.defineProperty(events, "edited", { get: () => edited, enumerable: true });
  return Object.assign(events, { open, close, isOpen: () => pan.isOpen(), panel: pan });
}
