// The AI services of Ask (docs/design/ask_and_data_dock.md, "The providers"; docs/guides/ask.md): only services with a free key, and one request form for all of
// them, the OpenAI-compatible chat (Google gives an OpenAI-compatible address for Gemini too). Each address accepts a request from a browser page (CORS),
// checked on 2026-11-05. The key goes only in the header of a request to the provider's own address, never in a URL.
//
//   PROVIDERS: [{id, name, base, model, keys, onlyFree}]
//   chat(p, {key, model, messages, tools, toolChoice, signal}) -> the assistant message {content, tool_calls}; an error has `status` and `wait` (seconds)
//   models(p, key, signal) -> the model names of the key;  pickModel(names) -> a model with tool support
export const PROVIDERS = [
  {id: "gemini", name: "Google Gemini", base: "https://generativelanguage.googleapis.com/v1beta/openai", model: "gemini-2.5-flash", keys: "https://aistudio.google.com/apikey"},
  {id: "groq", name: "Groq", base: "https://api.groq.com/openai/v1", model: "openai/gpt-oss-120b", keys: "https://console.groq.com/keys"},
  {id: "cerebras", name: "Cerebras", base: "https://api.cerebras.ai/v1", model: "gpt-oss-120b", keys: "https://cloud.cerebras.ai"},
  {id: "mistral", name: "Mistral", base: "https://api.mistral.ai/v1", model: "mistral-small-latest", keys: "https://console.mistral.ai/api-keys"},
  {id: "openrouter", name: "OpenRouter (free models)", base: "https://openrouter.ai/api/v1", model: "openai/gpt-oss-120b:free", keys: "https://openrouter.ai/keys", onlyFree: true},
];

// the names of the models change often, so Ask takes one from the provider's own list: the first match of this list, never a model for speech, images,
// embeddings or safety
const PREFER = [/gpt-oss-120b/, /mistral-medium-latest/, /mistral-small-latest/, /kimi-k2/, /llama-4-maverick/, /qwen3/, /gpt-oss-20b/, /llama-4-scout/,
                /^gemini-[\d.]+-flash$/, /^gemini-[\d.]+-pro$/, /llama-3\.3-70b/];
const SKIP = /whisper|guard|tts|embed|image|audio|compound|allam|playai|aqa|imagen|veo|learnlm|gemma|lite|preview|exp/i;
export function pickModel(ids){
  for(const re of PREFER){ const m = ids.filter((i) => re.test(i) && !SKIP.test(i)).sort().reverse()[0]; if(m) return m; }
  return ids.find((i) => !SKIP.test(i)) || ids[0];
}

// the provider's own words of an error: {error: {message}}, {error: "..."}, {message} or the text
const said = (text) => { try{ const b = JSON.parse(text); return (b.error && (b.error.message || b.error)) || b.message || text; }catch(e){ return text; } };
function refused(p, r, text){
  const e = new Error(`${p.name} refused the request (HTTP ${r.status}): ${String(said(text)).slice(0, 300)}`);
  e.status = r.status; e.wait = Number(r.headers.get("retry-after")) || null;
  return e;
}

export async function chat(p, {key, model, messages, tools, toolChoice = "auto", signal}){
  const r = await fetch(p.base + "/chat/completions", {method: "POST", signal,
    headers: {"Content-Type": "application/json", "Authorization": "Bearer " + key},
    body: JSON.stringify({model, messages, tools, tool_choice: toolChoice, temperature: 0})});
  const text = await r.text();
  if(!r.ok) throw refused(p, r, text);
  return JSON.parse(text).choices[0].message;
}

export async function models(p, key, signal){
  const r = await fetch(p.base + "/models", {headers: {"Authorization": "Bearer " + key}, signal}), text = await r.text();
  if(!r.ok) throw refused(p, r, text);
  const ids = (JSON.parse(text).data || []).map((m) => String(m.id).replace(/^models\//, ""));     // Google names a model "models/<name>"
  return p.onlyFree ? ids.filter((i) => i.endsWith(":free")) : ids;                                 // OpenRouter: only its free models
}
