// Ask (docs/design/ask_and_data_dock.md, "3. Ask"; docs/guides/ask.md): an AI agent in the side panel. The person asks a question in words; the agent writes
// SQL, runs it through the data dock, reads the result and answers in a few sentences. Each answer puts its SQL and its table into the data dock, so its roads
// light on the map. The agent can also colour roads, focus on roads and move the map: these are the data dock's layers. It reads and changes the map's own layers, base map, 3D view
// and camera (get_map, set_map), and a host page adds its own tools (the option tools). The person's own key of a free
// OpenAI-compatible service stays in this browser and goes only to that service. There is no server and no model in the browser.
//
//   askPanel({dashboard, data, about, dialect, examples, panel, backLabel, maxSteps, sendRows, providers, tools}) -> EventTarget + {open, close, isOpen, ask, stop,
//     clear, remove, history}
//   events: "answer" {question, text, sql, rows}, "error" {question, message}, "back"
import {editorFrame} from "../frame.js";
import {PROVIDERS, BUSY, chat, models, pickModel} from "./providers.js";
import {inner} from "../data/guard.js";

const $ = (tag, cls, text) => { const e = document.createElement(tag); if(cls) e.className = cls; if(text != null) e.textContent = text; return e; };
const sentence = (s) => { const t = String(s || "").split("\n")[0].replace(/^.*?Error: /, "").trim(); return /[.!?]$/.test(t) ? t : t + "."; };
const short = (t, n) => t.length <= n ? t : t.slice(0, t.lastIndexOf(" ", n)).replace(/[,.;:(]+$/, "") + "…";       // cut at a word
const fmt = (n) => Number(n).toLocaleString("en").replace(/,/g, " ");
const plural = (n, one, more) => `${n} ${n === 1 ? one : more}`;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const lsGet = (k) => { try{ return localStorage.getItem(k); }catch(e){ return null; } };
const lsPut = (k, v) => { try{ v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); }catch(e){} };
const PALETTE = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4", "#f032e6", "#9a6324"];
const ICON_SEND = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>';
const ICON_STOP = '<svg viewBox="0 0 24 24" width="14" height="14"><rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor"/></svg>';
const ICON_UP = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m6 15 6-6 6 6"/></svg>';
const FINAL = "Answer now in 1 to 3 short sentences with the results that you have. Do not call more tools.";

// The prompt is small on purpose: a free tier allows a few thousand tokens a minute, and each step of the agent sends it again ("The token budget")
const PROMPT = `You answer questions about the data of a map page. The data is in a {dialect} database.
{about}

Tools (those with sql take one read-only SELECT or WITH statement):
- run_query(sql): the first rows of the result. The page shows your result as a table and lights its roads.
- color_roads(groups): colours roads; each group: label, color (#rrggbb), sql that selects {id}.
- focus_roads(sql, mode): the roads that the sql selects ({id}) stay; the others are faded
  (mode "fade", the default) or hidden (mode "hide": use it when the person says "only").
- move_map(sql): zooms to the roads that the sql selects ({id}).
- get_map(): the map's layers (on or off), base maps, 3D view and camera now. Call it before you use a layer name.
- set_map(overlays, basemap, view3d, roadFill, tunnel, camera): shows or hides a layer, changes the base map, the 3D view or the camera
  (center [longitude, latitude], zoom, pitch, bearing). Use it when the person asks to show or hide a layer, to change the base map, the
  3D view or the camera (a place by its coordinates). For roads from a query, use move_map.
- draw_chart(sql, kind, x, y, title): a chart of the result in the data dock; kind is bar, line, histogram, scatter or pie;
  x is the column of the labels (bar, pie), of the order (line) or of the numbers (histogram, scatter); y is a number column
  (not for a histogram). Use it when the person asks for a chart, a graph, a plot or a diagram, or when a comparison of 3 to
  40 values is clearer as a chart. Aggregate in the SQL (GROUP BY): a chart draws the rows as they are. A pie needs values
  of 0 or more and at most 6 slices. For the distribution of a number (lengths, speeds) use histogram, not bar.
Use a map tool only when the person asks to see, show, hide, colour, filter, zoom or change the map. You cannot change the data.

Rules:
- Use only names from the schema. Do not guess a name: look it up first.
- About a set of roads: run one query that gives all of them ({id}, name and the useful columns), with no
  LIMIT, sorted by the most important column. The page shows it as the table and lights its roads. A count or a
  "longest" query alone is not enough: run the full query too.
- About roads: select {id}, so the page can light them. Also for a list of street names:
  SELECT {id}, name ... (no DISTINCT), not SELECT DISTINCT name.
- Readable column names (AS), round numbers.
- If a query fails, read the error, fix the SQL, run it again.
- Answer in the language of the question, in 1 to 3 short sentences: the count and the one or two most
  important facts, by street name (for example the longest). The page shows the table and the map.
- Never write {id} values or a list of the rows in the answer.
- If the data cannot answer, say so.

The schema "extra" has the page's own data (each table with what it holds, below): read its columns before you use it.
Schema (schema: table rows, ...):
`;
const LOOKUP = `Look up:
  what a table holds: SELECT table_name, comment FROM duckdb_tables() WHERE schema_name = 's'
  its columns: SELECT column_name, data_type, comment FROM duckdb_columns() WHERE schema_name = 's' AND table_name = 't'`;

// graph work in SQL (Kaveh, 2026-11-06: "compute diameter of driving network" got "there is no graph function"): DuckDB's recursive CTE with USING KEY
// keeps one row for each start and node, so a shortest-path search from a few start nodes is one query. The diameter by sweeps (forward from the 4 nodes
// at the edges of the map, then backward from each farthest node) gave the exact value on Monaco's driving network, 6 066 m, in 0.6 s for both queries;
// a double sweep from one node gave only 4 319 m (one-way streets), and all pairs at once took 322 s.
const GRAPH = `Graph questions (a route, a distance on the network, the farthest node, the diameter, connected parts): the network is a
table of directed edges with a start node, an end node and a length, and its nodes have a position (look up the columns).
Shortest distances from some start nodes at once:
  WITH RECURSIVE dist(src, node, d) USING KEY (src, node) AS (
    SELECT n, n, 0.0::DOUBLE FROM (<start nodes>) AS s(n)
    UNION
    (SELECT d0.src, e.<end>, min(d0.d + e.<length>)::DOUBLE FROM recurring.dist AS d0 JOIN <edges> AS e ON e.<start> = d0.node
     LEFT JOIN recurring.dist AS old ON old.src = d0.src AND old.node = e.<end>
     GROUP BY d0.src, e.<end>, old.d HAVING old.d IS NULL OR min(d0.d + e.<length>) < old.d))
  SELECT src, arg_max(node, d) AS far_node, max(d) AS d FROM dist GROUP BY src
The diameter (the longest shortest path) in two queries: 1. start at the 4 nodes at the edges of the map (the smallest and the
largest x and y); 2. run it on the reversed edges (swap <start> and <end>) from each far_node of step 1. The largest d of the
two runs is the diameter. Say that sweeps found it. Never compute all pairs at once: it takes minutes.`;

// an answer as the person reads it: no raw ids ("edge 3363728794791538739", any number of 12 digits or more): the table has them
const noIds = (t) => t.replace(/\b(edges?|edge_id|id)\s*[:=]?\s*\d{12,}\b\s*/gi, "").replace(/\s*\(?\b\d{12,}\b\)?/g, "").replace(/\(\s*\)/g, "")
  .replace(/\s{2,}/g, " ").trim().replace(/^\(([^()]+)\)/, "$1");
// **bold** and `code` of the model as bold and code, built from text nodes: no HTML of the model goes into the page
function inline(el, text){
  for(const part of String(text).split(/(\*\*[^*]+\*\*|`[^`]+`)/)){
    if(/^\*\*[^*]+\*\*$/.test(part)) el.append($("b", "", part.slice(2, -2)));
    else if(/^`[^`]+`$/.test(part)) el.append($("code", "", part.slice(1, -1)));
    else if(part) el.append(document.createTextNode(part));
  }
  return el;
}

// the default examples: only what every page has (a data dock with tables, and a map with roads, layers and a base map); the agent looks up the names
const GENERAL = [
  {title: "Know the data", items: ["What tables does this data have, and what is in each one?", "How many rows does each table have?",
    "Which columns does the main table have, and which have missing values?"]},
  {title: "Find and count", items: ["Show the first 20 rows of the main table.", "What are the 10 largest values of the most important number column?",
    "How many rows are there for each value of a column that has few values?"]},
  {title: "Show on the map", items: ["Show the 100 roads with the largest value of a number column on the map.", "Show the roads of the most common value of a text column on the map."]},
  {title: "Colour and focus", items: ["Colour the roads by a column that has few values.", "Keep only the roads of the most common value and fade the others."]},
  {title: "The map and the layers", items: ["Which layers does the map have?", "Hide all the layers except the roads.", "Switch to the satellite base map.",
    "Turn on the 3D view.", "Zoom to the roads of the last result."]},
  {title: "Charts", items: ["Draw a bar chart of the number of rows for each value of a column that has few values.", "Draw a histogram of a number column."]},
];

export function askPanel(o = {}){
  const rs = o.dashboard || window.rs, data = o.data;
  if(!data || typeof data.run !== "function") throw new Error("askPanel: data (the data dock) is necessary.");
  const panel = o.panel || document.getElementById("sb"), dialect = o.dialect || "SQL";
  const MAX = o.maxSteps || 6, SEND = o.sendRows || 30, PROVS = o.providers || PROVIDERS, ID = data.idColumn || "edge_id";
  // the examples: the general groups (any data: no name of a table or a column of a project), then the host's own strings and groups;
  // examples: {general: false, groups: [...]} gives only the host's own
  const own = Array.isArray(o.examples) ? o.examples : o.examples && Array.isArray(o.examples.groups) ? o.examples.groups : [];
  const examples = o.examples && o.examples.general === false ? own : [...GENERAL, ...own];
  const events = new EventTarget(), emit = (name, detail) => events.dispatchEvent(new CustomEvent(name, {detail}));
  const phone = () => document.documentElement.classList.contains("rs-phone");
  let loaded = false; data.ready().then(() => { loaded = true; }, () => {});

  // ---- the provider, the model and the key of this browser: rs-settings:ask {provider, model: {<provider>: name}}, rs-key:ask:<provider> ----
  const settings = () => { try{ return JSON.parse(lsGet("rs-settings:ask")) || {}; }catch(e){ return {}; } };
  const putSettings = (s) => lsPut("rs-settings:ask", JSON.stringify(s));
  const prov = () => { const s = settings(), p = PROVS.find((x) => x.id === s.provider) || PROVS[0]; return {...p, model: (s.model && s.model[p.id]) || p.model}; };
  const keyOf = (p = prov()) => lsGet("rs-key:ask:" + p.id) || "";
  const setModel = (m) => { const s = settings(), id = prov().id; s.provider = id; s.model = {...s.model, [id]: m}; putSettings(s); paintWho(); };
  const chatOf = (p, req) => p.chat ? p.chat(req) : chat(p, req);                                   // a provider of the page (a test) has its own chat
  const modelsOf = (p, signal) => p.models ? p.models(keyOf(p), signal) : models(p, keyOf(p), signal);

  // ---- the view: rs.frame; the head row is the tool row (it does not scroll), the body the conversation, the bar the question box ----
  const tools = $("div", "rs-ask-top"), who = $("span", "rs-ask-who"), keyB = $("button", "rs-ask-keyb", "Key"), newB = $("button", "rs-ask-new", "New");
  keyB.type = newB.type = "button"; keyB.setAttribute("aria-pressed", "false"); keyB.title = "Your key for the AI service"; newB.title = "Start a new conversation";
  tools.append(who, keyB, newB);
  const helpB = o.help !== false && rs.help && rs.help.button(tools, {title: "Ask", button: "About Ask",
    intro: "Ask a question about the roads in words. An AI service writes the SQL, runs it on the data of this page, and answers in a few sentences. The table goes to the data dock, and the roads light on the map.",
    terms: [["Key", "Your own key of an AI service. Google Gemini and Groq give a free key. The key stays in this browser and goes only to that service. Other pages on the same address (for example the same github.io site) can read it: use a key with a spending limit."],
            ["Examples", "Questions to try. After the first question, they are above the question box."],
            ["An answer", "The question, the answer and the SQL (open “1 query”). Show puts its table in the dock again, and its roads light on the map. ✕ removes the card."],
            ["MAP", "An answer can colour the roads, focus on some roads (the others fade or hide) or move the map. A colour and a focus stay: they are in the lists of Colour ▾ and Focus ▾ in the data dock. You can also ask to show or hide a map layer, to change the base map, to turn the 3D view on or to move the camera (\"turn off the water\", \"satellite\", \"zoom to Fontvieille\")."],
            ["New", "Starts a new conversation. The map keeps its colours and its focus."]],
    note: "Ask sends your question, the conversation, the names and descriptions of the tables, and the query results (up to 30 rows each) to the AI service. An AI service can be wrong: look at the table and at the SQL."});
  if(helpB) who.after(helpB);                                                                        // the order: provider, ?, Key, New
  const frame = editorFrame({panel, title: "Ask", back: o.backLabel || "Back", head: tools, id: "ask"});
  frame.root.classList.add("rs-ask");
  const body = frame.body, log = $("div", "rs-ask-log"), keyBox = $("div", "rs-ask-key"); keyBox.hidden = true;
  body.append(keyBox, log);
  const toEnd = () => { body.scrollTop = body.scrollHeight; };

  // the empty start: one line about Ask, the key note when there is no key, the examples as chips
  const ex = $("div", "rs-ask-ex"), needKey = $("div", "rs-ask-need");
  // examples: strings and groups {title, items}; a group is a small heading above its chips (the keys and the list's own children are the chips and the headings)
  const chips = (onPick) => examples.flatMap((g) => {
    const one = (q) => { const c = $("button", "rs-ask-q", q); c.type = "button"; c.onclick = () => { onPick(); ask(q); }; return c; };
    return g && typeof g === "object" ? (g.items || []).length ? [...(g.title ? [$("p", "rs-ask-grp", g.title)] : []), ...g.items.map(one)] : [] : [one(String(g))];
  });
  ex.append($("p", "rs-ask-hint", "Ask a question in words. The agent writes the SQL, the table goes to the data dock and the roads light on the map."), needKey, ...chips(() => {}));
  log.append(ex);

  // the question box: one box with the text and a round send button inside; it grows with the text to 6 lines. Above it, after the first question, "Examples ▴".
  const exBar = $("div", "rs-ask-exbar"), exB = $("button", "rs-ask-exb"), exList = $("div", "rs-ask-exlist");
  exB.type = "button"; exB.innerHTML = "Examples " + ICON_UP; exB.setAttribute("aria-expanded", "false"); exList.hidden = true;
  const exOpen = (on) => { exList.hidden = !on; exB.setAttribute("aria-expanded", String(on)); if(on) exList.scrollTop = 0; };
  exList.append(...chips(() => exOpen(false)));
  exB.onclick = () => exOpen(exList.hidden);
  // the list opens upward over the chat: its top is the top of the frame's body at most, and it scrolls inside (the panel's scroll rules)
  const fitList = () => { exList.style.maxHeight = Math.max(80, frame.body.clientHeight - 8) + "px"; };
  new ResizeObserver(fitList).observe(frame.body); fitList();
  // keys: ↑ ↓ walk the examples (the focus scrolls the list to the one in view), Escape closes the list
  exBar.addEventListener("keydown", (e) => {
    if(exList.hidden) return;
    const items = [...exList.querySelectorAll("button.rs-ask-q")], at = items.indexOf(document.activeElement);
    if(e.key === "Escape"){ e.preventDefault(); e.stopPropagation(); exOpen(false); exB.focus(); }
    else if(e.key === "ArrowUp" || e.key === "ArrowDown"){
      e.preventDefault();
      const next = e.key === "ArrowUp" ? (at < 0 ? items.length - 1 : at - 1) : (at < 0 ? -1 : at + 1);
      if(items[next]) items[next].focus(); else if(e.key === "ArrowDown") exB.focus();
    }
  });
  document.addEventListener("click", (e) => { if(!exBar.contains(e.target)) exOpen(false); });
  exBar.append(exList, exB);
  const comp = $("div", "rs-ask-comp"), box = $("textarea"), send = $("button", "rs-ask-send");
  box.rows = 1; box.placeholder = "Ask a question about the roads"; box.setAttribute("aria-label", "Your question"); send.type = "button";
  const grow = () => { box.style.height = "auto"; box.style.height = Math.min(box.scrollHeight, 6 * 20 + 12) + "px"; };
  box.addEventListener("input", grow);
  box.onkeydown = (e) => { if(e.key === "Enter" && !e.shiftKey){ e.preventDefault(); const t = box.value; if(t.trim() && !ctl){ box.value = ""; grow(); ask(t); } } };
  send.onclick = () => { if(ctl){ stop(); return; } const t = box.value; if(t.trim()){ box.value = ""; grow(); ask(t); } };
  const sending = (on) => { send.innerHTML = on ? ICON_STOP : ICON_SEND; send.title = on ? "Stop" : "Ask (Enter)"; send.setAttribute("aria-label", send.title); send.classList.toggle("stop", on); };
  sending(false);
  comp.append(box, send);
  frame.bar.append(exBar, comp);
  const paintStart = () => { const none = !turns.length; ex.hidden = !none; exBar.hidden = none || !exList.querySelector("button"); };

  // ---- the provider's name and the key form (in the view: the person gets the key where it is needed) ----
  function paintWho(){
    const p = prov(), k = keyOf(p);
    who.textContent = k ? `${p.name} · ${p.model}` : `${p.name} · no key`; who.title = who.textContent;
    needKey.replaceChildren();
    if(!k){
      const add = $("button", "sb-primary", "Add a key"); add.type = "button"; add.onclick = () => showKey(true);
      const link = (p) => { const a = $("a", "", p.name); a.href = p.keys; a.target = "_blank"; a.rel = "noopener"; return a; };
      const free = PROVS.filter((x) => x.keys).slice(0, 2), line = $("p", "", "Ask needs your own key. ");
      if(free.length) line.append(...free.flatMap((x, i) => [i ? " and " : "", link(x)]), " give a free key.");
      needKey.append(line, add);
    }
  }
  const showKey = (on) => { keyBox.hidden = !on; log.hidden = on; frame.bar.hidden = on; keyB.classList.toggle("on", on); keyB.setAttribute("aria-pressed", String(on)); if(on) drawKey(); else toEnd(); };
  keyB.onclick = () => showKey(keyBox.hidden);
  function drawKey(){
    const p = prov();
    const sel = $("select"); for(const x of PROVS){ const op = $("option", "", x.name); op.value = x.id; op.selected = x.id === p.id; sel.append(op); }
    const model = $("input", "rs-q"), list = $("datalist"); list.id = "rs-ask-models"; model.value = p.model; model.setAttribute("list", list.id); model.spellcheck = false;
    const key = $("input", "rs-q"); key.type = "password"; key.autocomplete = "off"; key.placeholder = keyOf(p) ? "(a key is saved in this browser)" : "Paste your key";
    const save = $("button", "sb-primary", "Save"), clear = $("button", "", "Clear"), note = $("p", "rs-ask-keynote"), btns = $("div", "rs-ask-btns");
    save.type = clear.type = "button"; btns.append(clear, save);
    const link = $("a", "", "Get a free key from " + p.name); if(p.keys){ link.href = p.keys; link.target = "_blank"; link.rel = "noopener"; } else link.hidden = true;
    // no notes under the form (Kaveh, 2026-11-06: "I think we should remove this part too"): the "?" of Ask says where the key and the data go; the line
    // here shows only the state of a save
    const row = (l, el) => { const r = $("label", "rs-ask-krow"); r.append($("span", "", l), el); return r; };
    const hd = $("div", "rs-ask-keyhd"), back = $("button", "", "‹ Back to chat"); back.type = "button"; back.onclick = () => showKey(false);
    hd.append($("b", "", "Your key"), back);
    keyBox.replaceChildren(hd, row("Provider", sel), link, row("Model", model), list, row("Key", key), btns, note);
    sel.onchange = () => { const s = settings(); s.provider = sel.value; putSettings(s); drawKey(); paintWho(); };
    clear.onclick = () => { lsPut("rs-key:ask:" + prov().id, null); drawKey(); paintWho(); };
    save.onclick = async () => {
      const s = settings(); s.provider = sel.value; putSettings(s);
      if(key.value.trim()) lsPut("rs-key:ask:" + sel.value, key.value.trim());
      key.value = ""; paintWho(); note.textContent = "Checking the key…";
      try{
        const ids = await modelsOf(prov()), typed = model.value.trim(), m = ids.includes(typed) ? typed : pickModel(ids);
        list.replaceChildren(...ids.map((i) => Object.assign($("option"), {value: i})));
        if(m){ setModel(m); model.value = m; }
        note.textContent = `Saved. The key works: ${plural(ids.length, "model", "models")}. Ask uses ${m}${typed && typed !== m ? ` (not "${typed}": the key cannot use it)` : ""}.`;
        setTimeout(() => { if(!keyBox.hidden) showKey(false); }, 1600);                              // back to the chat by itself
      }catch(e){ note.textContent = "Saved, but the key did not work: " + sentence(e.message); }
    };
  }

  // ---- the schema text of the prompt: every table on one line for each schema, the columns of the main table, the page's own tables ----
  let schemaTxt = null, mainTable = null;
  async function promptText(){
    if(!schemaTxt){
      const tables = (await data.schema()).tables || [], groups = {};
      for(const t of tables){ const i = t.name.lastIndexOf("."), sc = i < 0 ? "tables" : t.name.slice(0, i); (groups[sc] = groups[sc] || []).push(`${t.name.slice(i + 1)} ${t.rows ?? "?"}`); }
      mainTable = tables.find((t) => t.main) || tables.find((t) => t.columns) || null;
      const extra = tables.filter((t) => t.name.startsWith("extra.") && t.about);
      schemaTxt = [Object.entries(groups).map(([sc, ts]) => `${sc}: ${ts.join(", ")}`).join("\n"),
        mainTable && mainTable.columns ? `Columns of ${mainTable.name}:\n` + mainTable.columns.map((c) => `  ${c.name} ${c.type || ""}${c.about ? ": " + short(String(c.about), 60) : ""}`).join("\n") : "",
        extra.length ? "The page's own data:\n" + extra.map((t) => `  ${t.name}: ${short(String(t.about), 140)}`).join("\n") : "",
        /duckdb/i.test(dialect) ? LOOKUP : "", /duckdb/i.test(dialect) ? GRAPH : ""].filter(Boolean).join("\n\n");
    }
    return PROMPT.replace("{dialect}", dialect).replace("{about}", o.about || "").replace(/\{id\}/g, ID) + schemaTxt;
  }

  // ---- the tools of the agent: one list. A tool is {name, description, parameters, step(args, c), run(args, c)}; run gives what goes back to the model.
  // Every map tool takes SQL that selects the id column (the same guard as a query); it keeps only the roads that the map draws, and puts its roads into
  // the dock, so the table is what the map shows. No id goes to the provider. ----
  const SQL = {type: "string", description: "One read-only SELECT or WITH statement."}, IDSQL = {type: "string", description: `SQL that selects ${ID}.`};
  const cell = (v) => typeof v === "bigint" ? String(v) : typeof v === "string" && v.length > 200 ? v.slice(0, 200) + "..." : v;
  async function roadsOf(sql){
    const ids = await data.roads(inner(sql)), all = ids.length + ids.missing;
    if(!all) throw new Error("The query selects no roads.");
    if(!ids.length) throw new Error(`None of these ${fmt(all)} roads is on the map. Say so, or choose roads that the map draws.`);
    return ids;
  }
  const notAll = (ids) => ids.missing ? ` (${fmt(ids.length)} of ${fmt(ids.length + ids.missing)} are on the map)` : "";
  // the dock follows the map: the roads of a map tool with their id, name, class and length (the columns that the main table has)
  async function toDock(groups, lit){
    if(!mainTable) return null;
    const have = new Set((mainTable.columns || []).map((c) => c.name));
    const cols = have.size ? [ID, "name", "highway", "length_m"].filter((c) => have.has(c)).map((c) => c === "length_m" ? "round(length_m) AS length_m" : c).join(", ") : "*";
    const one = (g) => `SELECT ${g.label != null ? `'${String(g.label).replace(/'/g, "''")}' AS colour, ` : ""}${cols} FROM ${mainTable.name} WHERE ${ID} IN (SELECT ${ID} FROM (${inner(g.sql)}) AS rs_t)`;
    const q = groups.length > 1 || groups[0].label != null ? `SELECT * FROM (${groups.map(one).join(" UNION ALL ")}) AS rs_m ORDER BY colour${have.has("name") ? ", name" : ""}`
      : one(groups[0]) + (have.has("name") ? " ORDER BY name" : "");
    try{ await data.run(q, {source: "ask"}); if(!lit) data.lightOff(); return data.result(); }
    catch(e){ return null; }                                                                         // the map change stays; the dock keeps its table
  }
  const TOOLS = [
    {name: "run_query", description: "Run one read-only SQL statement and get the first rows.", parameters: {sql: SQL}, required: ["sql"],
     step: (a, c) => `Running query ${c.ok.length + c.failed.length + 1}`,
     async run({sql}, c){
       const r = await data.run(String(sql || ""), {source: "ask"}); c.ok.push(r);
       return {columns: r.columns.map((x) => `${x.name} ${x.type || ""}`.trim()), rows: r.rows.slice(0, SEND).map((row) => row.map(cell)), row_count: r.total ?? r.rows.length, more_rows: !!r.more};
     }},
    {name: "color_roads", description: "Colour roads on the map, one colour for each group.", required: ["groups"],
     parameters: {groups: {type: "array", items: {type: "object", required: ["label", "color", "sql"], properties: {label: {type: "string"}, color: {type: "string", description: "#rrggbb"}, sql: IDSQL}}}},
     step: () => "Colouring the roads",
     async run({groups = []}, c){
       if(!Array.isArray(groups) || !groups.length || groups.length > 8) throw new Error("Give 1 to 8 groups.");
       const gs = [];
       for(const [k, g] of groups.entries()) gs.push({label: String(g.label || "Roads"), color: /^#[0-9a-f]{6}$/i.test(g.color) ? g.color : PALETTE[k], ids: await roadsOf(g.sql), sql: g.sql});
       data.colour(gs.map(({label, color, ids}) => ({label, color, ids})), {sql: gs.map((g) => g.label + ": " + g.sql).join("\n")});
       const text = "Coloured " + gs.map((g) => `${fmt(g.ids.length)} roads (${g.label})${notAll(g.ids)}`).join(" and ");
       c.maps.push({text, sql: gs.map((g) => g.sql), res: await toDock(gs, false)});
       return {done: text + "."};
     }},
    {name: "focus_roads", description: "Keep the roads that the SQL selects; fade or hide the others.", required: ["sql"],
     parameters: {sql: IDSQL, mode: {type: "string", enum: ["fade", "hide"], description: "fade (default): the others stay, faded; hide: the others are hidden (for 'only')."}},
     step: () => "Focusing the map",
     async run({sql, mode}, c){
       const ids = await roadsOf(sql), m = mode === "hide" ? "hide" : "fade";
       data.focus(ids, {sql, mode: m});
       const text = `Focus on ${fmt(ids.length)} roads${notAll(ids)} (the others ${m === "hide" ? "hidden" : "faded"})`;
       c.maps.push({text, sql: [sql], res: await toDock([{sql}], false)});
       return {done: text + "."};
     }},
    {name: "move_map", description: "Zoom the map to the roads that the SQL selects.", parameters: {sql: IDSQL}, required: ["sql"],
     step: () => "Moving the map",
     async run({sql}, c){
       const ids = await roadsOf(sql), res = await toDock([{sql}], true);
       rs.focus(ids);
       const text = `Zoomed to ${fmt(ids.length)} roads${notAll(ids)}`;
       c.maps.push({text, sql: [sql], res, move: true}); c.cam = false;
       return {done: text + "."};
     }},
  ];
  TOOLS.push({name: "draw_chart", description: "Draw a chart of the result of one SQL statement in the data dock.", required: ["sql", "kind", "x"],
    parameters: {sql: SQL, kind: {type: "string", enum: ["bar", "line", "histogram", "scatter", "pie"]}, x: {type: "string", description: "A column of the result."},
                 y: {type: "string", description: "A number column of the result (not for histogram). Leave it out for a bar, line or pie of the count of rows."}, title: {type: "string"}},
    step: () => "Drawing the chart",
    async run({sql, kind, x, y, title}, c){
      const r = await data.run(String(sql || ""), {source: "ask"}); c.ok.push(r);
      await data.chart({kind, x, y: kind === "histogram" ? undefined : y, title});      // a column that is not in the result: an error for the model
      c.chart = {res: data.result(), spec: data.drawnChart(), title};
      return {done: `Drew a ${kind} chart of ${y ? y + " by " : ""}${x} (${fmt(r.total ?? r.rows.length)} rows).`};
    }});
  // ---- the map's own controls (rs.getState / rs.setState): the layers, the base map, the 3D view, the road fill, the tunnel look and the camera. The camera has
  // one path: rs.setState jumps to it; move_map flies to roads (rs.focus). In one answer the last mover wins: showTurn does not fly to the table's roads again
  // after a set_map camera. The page's own state (selection, filter, colours) stays with its tools. ----
  const r5 = (n) => Math.round(n * 1e5) / 1e5;
  function mapNow(){
    const s = rs.getState(), cam = s.camera;
    return {overlays: Object.entries(s.overlays || {}).map(([label, v]) => ({label, on: v.visible !== false})),
      basemaps: rs.basemaps ? rs.basemaps() : [], basemap: s.basemap, view3d: !!s.view3d, roadFill: !!s.roadFill, tunnel: s.tunnel,
      camera: cam && {center: cam.center.map(r5), zoom: Math.round(cam.zoom * 100) / 100, pitch: Math.round(cam.pitch), bearing: Math.round(cam.bearing)}};
  }
  const NUM = (d) => ({type: "number", description: d});
  TOOLS.push({name: "get_map", description: "The map's layers (on or off), base maps, 3D view, road fill, tunnel look and camera now.", parameters: {}, required: [],
    step: () => "Reading the map", async run(){ return mapNow(); }});
  TOOLS.push({name: "set_map", description: "Change the map: show or hide layers, change the base map, the 3D view, the road fill, the tunnel look or the camera. Give only what changes.", required: [],
    parameters: {
      overlays: {type: "array", description: "Layers to show or hide (labels from get_map).", items: {type: "object", required: ["label", "on"], properties: {label: {type: "string"}, on: {type: "boolean"}}}},
      basemap: {type: "string", description: "The key or label of a base map from get_map."},
      view3d: {type: "boolean", description: "The 3D view (tilted camera)."}, roadFill: {type: "boolean", description: "The fill of the roads."},
      tunnel: {type: "object", description: "The look of tunnels (as in get_map).", properties: {strength: NUM("0 to 100"), toward: {type: "string"}, palette: {type: "string"}, ratio: {type: "array", items: {type: "number"}}}},
      camera: {type: "object", description: "Give only what changes.", properties: {center: {type: "array", items: {type: "number"}, description: "[longitude, latitude]"},
        zoom: NUM("0 to 22"), pitch: NUM("0 to 85"), bearing: NUM("degrees")}}},
    step: () => "Changing the map",
    async run(a, c){
      const now = mapNow(), change = {}, done = [], unknown = [];
      const find = (list, v, f) => list.find((x) => [x.key, x.label].some((y) => y != null && String(y).toLowerCase() === String(v).toLowerCase())) || (unknown.push(`${f} ${JSON.stringify(v)}`), null);
      if(a.overlays != null){                                                                    // [{label, on}] or {label: on}
        const list = Array.isArray(a.overlays) ? a.overlays : Object.entries(a.overlays).map(([label, on]) => ({label, on}));
        for(const {label, on} of list){ const o = find(now.overlays, label, "layer"); if(o){ (change.overlays = change.overlays || {})[o.label] = {visible: !!on}; done.push(`${o.label} ${on ? "on" : "off"}`); } }
      }
      if(a.basemap != null){ const b = find(now.basemaps, a.basemap, "base map"); if(b){ change.basemap = b.key; done.push(`base map ${b.label || b.key}`); } }
      for(const k of ["view3d", "roadFill"]) if(a[k] != null){ change[k] = !!a[k]; done.push(`${k === "view3d" ? "3D view" : "road fill"} ${a[k] ? "on" : "off"}`); }
      if(a.tunnel && typeof a.tunnel === "object"){ change.tunnel = a.tunnel; done.push("tunnel look"); }
      const cam = a.camera;
      if(cam && typeof cam === "object"){
        const ok = (v, lo, hi) => Number.isFinite(v) && v >= lo && v <= hi, ll = cam.center, bad = [];
        if(ll != null && !(Array.isArray(ll) && ll.length === 2 && ok(ll[0], -180, 180) && ok(ll[1], -90, 90))) bad.push("center must be [longitude, latitude]");
        if(cam.zoom != null && !ok(cam.zoom, 0, 22)) bad.push("zoom must be 0 to 22");
        if(cam.pitch != null && !ok(cam.pitch, 0, 85)) bad.push("pitch must be 0 to 85");
        if(cam.bearing != null && !Number.isFinite(cam.bearing)) bad.push("bearing must be a number");
        if(bad.length) throw new Error("The camera is wrong: " + bad.join("; ") + ".");
        const {center, zoom, pitch, bearing} = cam, to = {center, zoom, pitch, bearing};
        for(const k in to) if(to[k] == null) delete to[k];
        if(Object.keys(to).length){ change.camera = to; done.push("camera"); c.cam = true; }
      }
      if(done.length) rs.setState(change);
      const text = done.length ? "Map: " + done.join(", ") : "";
      if(text) c.maps.push({text, sql: [], res: null, move: true});
      return {done: done.length ? text + "." : "Nothing changed.", ...(unknown.length ? {not_found: unknown, hint: "Call get_map for the names."} : {}), map: mapNow()};
    }});

  // the host's own tools, in the same form: a name that is in use is refused
  for(const t of o.tools || []){
    if(!t || typeof t.name !== "string" || typeof t.run !== "function") throw new Error("askPanel: a tool of the option tools needs a name and a run function.");
    if(TOOLS.some((y) => y.name === t.name)) throw new Error(`askPanel: the tool name "${t.name}" is already in use.`);
    TOOLS.push({parameters: {}, required: [], description: "", step: () => `Running ${t.name}`, ...t});
  }
  const SPECS = TOOLS.map((t) => ({type: "function", function: {name: t.name, description: t.description, parameters: {type: "object", properties: t.parameters, ...(t.required && t.required.length ? {required: t.required} : {})}}}));

  // ---- one model call: a wait on the free limit (HTTP 429: at most 2 times, each at most 60 s), and one switch to another model that the key can use ----
  async function callModel(messages, signal, final, say){
    let waited = 0, switched = false;
    for(;;){
      const p = prov();
      try{ return await chatOf(p, {key: keyOf(p), model: p.model, messages, tools: SPECS, toolChoice: final ? "none" : "auto", signal}); }
      catch(e){
        if(signal.aborted) throw e;
        const s = e.wait || parseFloat((String(e.message).match(/try again in ([\d.]+)\s*s/i) || [])[1]) || 20;
        // the free limit (429) or a busy service (500, 502, 503, 504: Gemini's 503 "The model is overloaded"): wait, then try again, at most 2 times
        const busy = BUSY.has(e.status);
        if((e.status === 429 || busy) && waited < 2 && s <= 60){
          waited++;
          const n = busy && !e.wait ? 5 * waited : Math.ceil(s);
          for(let k = n; k > 0; k--){ if(signal.aborted) throw new Error("Stopped."); say(busy ? `${p.name} is busy: trying again in ${k} s` : `${p.name}'s free limit: waiting ${k} s`); await wait(1000); }
          continue;
        }
        if(!switched && (e.status === 404 || (e.status === 400 && /model/i.test(String(e.message))))){
          switched = true;
          const next = pickModel((await modelsOf(p, signal).catch(() => [])).filter((i) => i !== p.model));
          if(next){ setModel(next); continue; }
        }
        throw e;
      }
    }
  }
  // what goes back to the model for one tool call: at most 2500 characters; the rows are halved until it fits (rows_sent tells the model)
  function fit(out){
    const big = (k, v) => typeof v === "bigint" ? String(v) : v;
    let s = JSON.stringify(out, big);
    while(s.length > 2500 && out.rows && out.rows.length > 3){ out.rows = out.rows.slice(0, Math.floor(out.rows.length / 2)); out.rows_sent = out.rows.length; s = JSON.stringify(out, big); }
    return s;
  }

  // ---- a question: a card; the loop; the answer with its table in the dock ----
  const turns = []; let ctl = null, cur = null;
  const codes = (sqls) => sqls.map((s) => $("code", "", s));
  const failedEls = (failed) => failed.flatMap((f) => [$("code", "", f.sql), $("p", "rs-ask-err", f.error)]);
  const fold = (cls, summary, ...kids) => { const d = $("details", cls); d.append($("summary", "", summary), ...kids); return d; };
  async function ask(question){
    const text = String(question || "").trim();
    if(!text || ctl) return null;
    const t = {question: text, el: $("div", "rs-ask-turn")}, hd = $("div", "rs-ask-turn-hd"), x = $("button", "rs-ask-x", "✕");
    x.type = "button"; x.title = "Remove this question and its answer"; x.setAttribute("aria-label", x.title);
    x.onclick = () => remove(turns.indexOf(t));                                                     // the card only: the map keeps its layers
    hd.append($("p", "q", text), x); t.el.append(hd);
    turns.push(t); log.append(t.el); paintStart(); toEnd();
    const step = $("p", "step"), say = (s) => { step.textContent = s; if(!step.isConnected) t.el.append(step); toEnd(); };
    const c = {ok: [], failed: [], maps: []}, me = new AbortController();
    ctl = me; cur = t; sending(true);
    try{
      const p = prov();
      if(!keyOf(p)) throw new Error(`Ask needs your own key. Add a key of ${p.name} with Key.`);
      if(!loaded) say("Loading the data…");
      await data.ready();
      const history = turns.filter((y) => y !== t).flatMap((y) => y.hist || []);
      const messages = [{role: "system", content: await promptText()}, ...history, {role: "user", content: text}];
      let fails = 0, answer = null, n = 0;
      for(; n < MAX && answer == null; n++){
        const last = n === MAX - 1;
        say(`Asking ${p.name} (${prov().model})`);
        if(last) messages.push({role: "user", content: FINAL});                                    // the last call answers: no more tools
        const msg = await callModel(messages, me.signal, last, say), calls = (msg && msg.tool_calls) || [];
        if(me.signal.aborted) throw new Error("Stopped.");
        if(!calls.length || last){ if((msg && msg.content || "").trim()) answer = msg.content; break; }
        messages.push({role: "assistant", content: msg.content || "", tool_calls: calls});
        for(const call of calls){
          const name = call.function && call.function.name, tool = TOOLS.find((y) => y.name === name);
          let args = {}; try{ args = JSON.parse(call.function.arguments || "{}"); }catch(e){}
          let out;
          try{
            if(!tool) throw new Error(`There is no tool ${name}.`);
            say(tool.step(args, c)); out = await tool.run(args, c); fails = 0;
          }catch(err){
            if(me.signal.aborted) throw err;
            fails++; const e = sentence(err.message);
            if(name === "run_query") c.failed.push({sql: String(args.sql || ""), error: e});
            out = {error: e}; say(`Query ${c.ok.length + c.failed.length} failed: ${e} Trying again.`);
            if(fails >= 3) throw new Error("Three queries failed one after the other. Last error: " + e);
          }
          messages.push({role: "tool", tool_call_id: call.id, content: fit(out)});
        }
      }
      if(answer == null) throw new Error(`The model gave no answer in ${plural(Math.min(n + 1, MAX), "call", "calls")}. Its last table is in the data dock`);
      step.remove();
      return finish(t, answer, c);
    }catch(err){
      // no silent stop: any error ends the question with a red line, and the box works again; the queries that ran stay readable
      step.remove();
      const message = me.signal.aborted ? "Stopped." : sentence(err.message);
      t.el.append($("p", "rs-ask-err", message));
      const n = c.ok.length + c.failed.length;
      if(n) t.el.append(fold("rs-ask-sqls", `${plural(n, "query", "queries")} ran before the stop`, ...codes(c.ok.map((r) => r.sql)), ...failedEls(c.failed)));
      emit("error", {question: text, message});
      return null;
    }finally{ if(ctl === me){ ctl = null; cur = null; sending(false); } toEnd(); }
  }
  // the answer: its text, a line for each change of the map, the query that made its table (and the others in its details), Show
  function finish(t, answer, c){
    t.cam = c.cam; t.text = answer; t.hist = [{role: "user", content: t.question}, {role: "assistant", content: answer}];
    t.el.append(answerEl(answer, t));
    for(const m of c.maps){ const line = $("div", "rs-ask-map"); line.append($("span", "rs-ask-map-k", "Map"), $("span", "", m.text)); if(!m.move) line.append($("span", "rs-ask-map-to", "in the list of Colour or Focus")); t.el.append(line); }
    // the answer's table: the query with roads that has the most rows (a model often runs the full list, then a count or "LIMIT 2" for the longest); a map
    // tool's roads win over a helper query that the model ran after it
    const size = (r) => r.total ?? (r.rows.length + (r.more ? 1 : 0));
    const withRoads = c.ok.filter((r) => data.keyOf(r)), pool = withRoads.length ? withRoads : c.ok;
    const best = pool.length ? pool.reduce((a, b) => size(b) > size(a) ? b : a) : null;
    let foot = null;
    if(best){
      const n = best.total ?? best.rows.length, plus = best.more && best.total == null ? "+" : "", others = c.ok.filter((r) => r !== best).map((r) => r.sql);
      const d = fold("rs-ask-sqls", `1 query · ${fmt(n)}${plus} row${n === 1 && !plus ? "" : "s"}`, $("code", "", best.sql));
      if(others.length) d.append(fold("rs-ask-failed", `${plural(others.length, "more query", "more queries")} of the agent`, ...codes(others)));
      if(c.failed.length) d.append(fold("rs-ask-failed", `${plural(c.failed.length, "failed attempt", "failed attempts")}, fixed by the agent`, ...failedEls(c.failed)));
      foot = $("div", "rs-ask-foot"); foot.append(d); t.el.append(foot);
    }
    const sqls = c.maps.flatMap((m) => m.sql);
    if(sqls.length){ foot = $("div", "rs-ask-foot"); foot.append(fold("rs-ask-sqls", plural(sqls.length, "map query", "map queries"), ...codes(sqls))); t.el.append(foot); }
    t.res = c.chart ? c.chart.res : [...c.maps].reverse().map((m) => m.res).find(Boolean) || best;
    // a chart answer: a small copy of the chart in the card (no labels, no hover); Show puts the chart in the dock again
    if(c.chart && c.chart.spec){ t.chart = true; const box = $("div", "rs-ask-chart"); t.el.insertBefore(box, foot || null);
      rs.chart(box, {...c.chart.spec, small: true, onPick: null}); if(c.chart.title) box.title = c.chart.title; }
    if(t.res){
      const acts = $("div", "rs-ask-acts"), show = $("button", "rs-ask-show", "Show"); show.type = "button";
      show.title = "Put the table of this answer in the dock again: its roads light on the map"; show.onclick = () => showTurn(t);
      acts.append(show); foot.append(acts);
      showTurn(t, true);                                                                             // after the answer: its table in the dock, the camera on its roads
    }
    const detail = {question: t.question, text: answer, sql: t.res ? t.res.sql : null, rows: t.res ? t.res.rows : []};
    emit("answer", detail);
    return detail;
  }
  // a card's table back into the dock (its roads light), the dock open (on a phone only on a click: one sheet at a time) and the camera on its roads
  function showTurn(t, first){
    data.show(t.res);
    if(data.view) data.view(t.chart ? "chart" : "table");
    if(!first || !phone()) data.open();
    if(data.roadsOf && !(first && t.cam)) data.roadsOf(t.res).then((ids) => { if(ids.length) rs.focus(ids); }, () => {});
  }
  // the answer's text: paragraphs, and "- " or "1. " lines as a real list of at most 3 items, with "… N more in the table"
  function answerEl(text, t){
    const el = $("div", "a"), isItem = (l) => /^([-*•]|\d+[.)])\s+/.test(l);
    for(const b of String(text).replace(/\r/g, "").split(/\n\s*\n/)){
      const lines = b.split("\n").map((l) => l.trim()).filter(Boolean);
      let para = [];
      const flush = () => { if(para.length){ el.append(inline($("p"), noIds(para.join(" ")))); para = []; } };
      for(let i = 0; i < lines.length; i++){
        if(!isItem(lines[i])){ para.push(lines[i]); continue; }
        flush();
        const items = []; while(i < lines.length && isItem(lines[i])) items.push(noIds(lines[i++].replace(/^([-*•]|\d+[.)])\s+/, ""))); i--;
        const ul = $("ul"); items.slice(0, 3).forEach((s) => ul.append(inline($("li"), s))); el.append(ul);
        if(items.length > 3){ const more = $("button", "rs-ask-more", `… ${items.length - 3} more in the table`); more.type = "button"; more.onclick = () => { if(t.res) showTurn(t); }; el.append(more); }
      }
      flush();
    }
    return el;
  }

  // ---- the methods ----
  function stop(){ if(ctl){ ctl.abort(); data.stop(); } }
  function remove(i){
    const t = turns[i]; if(!t) return;
    if(t === cur) stop();
    t.el.remove(); turns.splice(i, 1); paintStart();
  }
  function clear(){ stop(); turns.splice(0).forEach((t) => t.el.remove()); schemaTxt = null; paintStart(); }
  newB.onclick = clear;
  const note = (s) => { try{ rs.sections && rs.sections.note("ask", s); }catch(e){} };
  function open(){ frame.open(); paintWho(); toEnd(); note("Open"); }
  function close(){ frame.close(); exOpen(false); note(turns.length ? plural(turns.length, "question", "questions") : "Ask a question about the data"); }
  frame.addEventListener("back", () => { close(); emit("back"); });
  // a road click while Ask is open: no popup; the data dock opens with the road in its card, where a question can use it (Kaveh, 2026-11-06: "for ask
  // and query part, we should disable popup"). rs:select comes before the popup, so the hold is right for each click, also after a close by the host
  document.addEventListener("rs:select", (e) => { const on = frame.isOpen() && !e.detail.overlay;
    if(rs.holdPopup) rs.holdPopup("ask", on); if(on) data.open(); });
  paintWho(); paintStart();
  return Object.assign(events, {open, close, isOpen: frame.isOpen, ask, stop, clear, remove,
    history: () => turns.map(({question, text, res}) => ({question, text: text ?? null, sql: res ? res.sql : null, rows: res ? res.rows : []}))});
}
