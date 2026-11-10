// The read-only guard and the row limit of the data dock and Ask (docs/design/ask_and_data_dock.md, "The read-only guard"). A statement passes when it is
// one SELECT or WITH statement with no word that writes, loads or reads a file or an address; the guard then wraps it in a row limit, one row more than the
// limit, so the caller knows that there are more. The words are checked outside of strings and comments.
//
//   guard(sql, limit) -> {ok: true, sql} | {ok: false, reason}
const REFUSED = ("INSERT UPDATE DELETE MERGE CREATE DROP ALTER TRUNCATE ATTACH DETACH COPY EXPORT IMPORT INSTALL LOAD PRAGMA SET RESET CALL " +
                 "CHECKPOINT VACUUM USE BEGIN COMMIT ROLLBACK GRANT REVOKE").split(" ");

// the SQL with its comments gone and its strings and quoted names made short, so a word in them is not seen
export function bare(sql){
  return String(sql).replace(/--[^\n]*/g, " ").replace(/\/\*[\s\S]*?\*\//g, " ").replace(/'(?:[^']|'')*'/g, "'s'").replace(/"(?:[^"]|"")*"/g, "q");
}
export const inner = (sql) => String(sql).trim().replace(/;\s*$/, "");

// A refused word is a name when it follows SELECT, a comma, AS, WHERE, BY, a dot, AND, OR, NOT, ON, HAVING, CASE, WHEN, THEN, ELSE or an operator: a column called `use`
// (lane_profile.use) is not the USE statement. A statement that writes can only start the text (which must be SELECT or WITH) or follow the `)` of a WITH, so
// those places are still refused. A word after `(` is a name too (count(use)), except the words that write rows: `WITH a AS (...) DELETE` and the like never have `(` before them.
const WRITES = new Set("INSERT UPDATE DELETE MERGE CREATE DROP ALTER TRUNCATE COPY".split(" "));
const NAME_AFTER = /(?:\b(?:SELECT|DISTINCT|AS|WHERE|BY|AND|OR|NOT|ON|HAVING|CASE|WHEN|THEN|ELSE)|[,.=<>+\-*\/%])$/i;
function word(body, w){
  const re = new RegExp(`\\b${w}\\b`, "gi");
  for(let m; (m = re.exec(body));){
    const before = body.slice(0, m.index).trimEnd();
    if(NAME_AFTER.test(before) || (!WRITES.has(w) && before.endsWith("("))) continue;
    return true;
  }
  return false;
}

export function guard(sql, limit = 1000){
  const body = bare(sql).trim().replace(/;\s*$/, "");
  if(!body) return {ok: false, reason: "Write one SELECT or WITH statement."};
  if(body.includes(";")) return {ok: false, reason: "Only one statement is allowed."};
  const first = (body.match(/^\s*\(?\s*(\w+)/) || [])[1] || "";
  if(!/^(SELECT|WITH)$/i.test(first)) return {ok: false, reason: `Only one SELECT or WITH statement is allowed. Found: ${first.toUpperCase() || "nothing"}.`};
  const bad = REFUSED.find((w) => word(body, w));
  if(bad) return {ok: false, reason: `Only one SELECT or WITH statement is allowed. Found: ${bad}.`};
  if(/\b(read_\w+|\w+_scan|glob|sniff_csv|query|query_table|getenv)\s*\(/i.test(body)) return {ok: false, reason: "A query cannot read files, addresses or SQL text."};
  if(/\b(FROM|JOIN)\s+'/i.test(body) || /'[^']*:\/\//.test(String(sql))) return {ok: false, reason: "A query cannot read files or addresses."};
  return {ok: true, sql: limit == null ? inner(sql) : `SELECT * FROM (\n${inner(sql)}\n) AS rs_q LIMIT ${limit + 1}`};
}
