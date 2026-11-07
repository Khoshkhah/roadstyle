// The AI services of Ask (docs/design/ask_and_data_dock.md, "The providers"; docs/guides/ask.md): only services with a free key, and one request form for all of
// them, the OpenAI-compatible chat (Google gives an OpenAI-compatible address for Gemini too). Each address accepts a request from a browser page (CORS),
// checked on 2026-11-05 (Z.ai on 2026-11-07). The key goes only in the header of a request to the provider's own address, never in a URL.
//
//   PROVIDERS: [{id, name, base, model, keys, onlyFree, free, paid, headers, temperature}]
//   chat(p, {key, model, messages, tools, toolChoice, signal}) -> the assistant message {content, tool_calls}; an error has `status` and `wait` (seconds)
//   models(p, key, signal) -> the model names of the key;  pickModel(names) -> a model with tool support;  rankModels(names) -> the same order, all
//   chatModels(names) -> the names without the models that do not chat (the list of the Model box)
export const PROVIDERS = [
  {id: "gemini", name: "Google Gemini", base: "https://generativelanguage.googleapis.com/v1beta/openai", model: "gemini-3.8-flash", keys: "https://aistudio.google.com/apikey"},
  {id: "groq", name: "Groq", base: "https://api.groq.com/openai/v1", model: "openai/gpt-oss-120b", keys: "https://console.groq.com/keys"},
  {id: "openrouter", name: "OpenRouter (free models)", base: "https://openrouter.ai/api/v1", model: "openai/gpt-oss-120b:free", keys: "https://openrouter.ai/keys", onlyFree: true},
  // Z.ai's model list names only its paid models, and a paid model with no balance gives HTTP 429 "Insufficient balance". `free` is the list
  // that Ask can use: the free models that answered a request with a new key (2026-11-07)
  {id: "zai", name: "Z.ai (GLM)", base: "https://api.z.ai/api/paas/v4", model: "glm-4.5-flash", keys: "https://z.ai/manage-apikey/apikey-list", free: ["glm-4.5-flash"]},
  // Claude is the one paid service (the person's own credit; a decision of 2026-11-07). Its OpenAI-compatible address takes the key as a Bearer
  // header; a call from a browser page needs the header anthropic-dangerous-direct-browser-access, and its model list (/models) needs
  // anthropic-version (`headers`, sent with each request). Its new models refuse `temperature` (HTTP 400 "deprecated"): `temperature: false`.
  {id: "claude", name: "Claude (paid)", base: "https://api.anthropic.com/v1", model: "claude-sonnet-5-5", keys: "https://console.anthropic.com/settings/keys",
   paid: true, temperature: false, headers: {"anthropic-dangerous-direct-browser-access": "true", "anthropic-version": "2023-06-01"}},
];

// the names of the models change often, so Ask takes one from the provider's own list: the first match of this list, never a model for speech, images,
// embeddings or safety
const PREFER = [/gpt-oss-120b/, /kimi-k2/, /llama-4-maverick/, /qwen3/, /gpt-oss-20b/, /llama-4-scout/,
                /^gemini-[\d.]+-flash$/, /^gemini-[\d.]+-pro$/, /llama-3\.3-70b/, /^claude-sonnet/];
// NOT_CHAT: models that do not chat with tools (speech, music, images, embeddings, safety, live audio, robots, agents of their own; the
// names of Gemini's and Groq's lists on 2026-11-07); the Model box does not list them. SKIP: also the models that the
// automatic pick does not take (small, preview or test models), which a person can still pick in the box
const NOT_CHAT = /whisper|guard|tts|embed|image|audio|playai|aqa|imagen|veo|moderation|orpheus|lyria|banana|transcribe|live|translate|robotics|computer-use|deep-research|antigravity/i;
const SKIP = new RegExp(NOT_CHAT.source + "|compound|allam|learnlm|gemma|lite|preview|exp", "i");
export const chatModels = (ids) => ids.filter((i) => !NOT_CHAT.test(i));
// the models in the order of the automatic pick: the best match of each PREFER line, then the others that SKIP does not leave out
export function rankModels(ids){
  const top = PREFER.map((re) => ids.filter((i) => re.test(i) && !SKIP.test(i)).sort().reverse()[0]).filter(Boolean);
  return [...new Set([...top, ...ids.filter((i) => !SKIP.test(i))])];
}
export function pickModel(ids){ return rankModels(ids)[0] || ids[0]; }

// the provider's own words of an error: {error: {message}}, {error: "..."}, {message}, a list of one of these (Google's OpenAI-compatible
// address sends [{error: ...}]) or the text
const said = (text) => { try{ let b = JSON.parse(text); if(Array.isArray(b)) b = b[0] || {}; return (b.error && (b.error.message || b.error)) || b.message || text; }
  catch(e){ return text; } };
// the error of a call. A server error (HTTP 500, 502, 503, 504) is a service that is busy or down for a short time, not a refusal: Ask waits
// and tries again (ask_panel.js, callModel), and the person reads "busy", not "refused". An HTTP 429 that says "insufficient balance" or
// "insufficient quota" (Z.ai, OpenAI) is no money on the account, not a limit for each minute: a wait does not help, so it is a refusal (status 402).
export const BUSY = new Set([500, 502, 503, 504]);
function refused(p, r, text){
  const why = String(said(text)).slice(0, 300), status = r.status === 429 && /insufficient.(balance|quota)/i.test(why) ? 402 : r.status;
  const e = new Error(BUSY.has(status) ? `${p.name} is busy now (HTTP ${status}): ${why} Try again in a minute, or choose another service under AI.`
    : status === 429 ? `${p.name}'s free limit (HTTP 429): ${why}` : `${p.name} refused the request (HTTP ${r.status}): ${why}`);
  e.status = status; e.wait = Number(r.headers.get("retry-after")) || null;
  return e;
}

export async function chat(p, {key, model, messages, tools, toolChoice = "auto", signal}){
  const r = await fetch(p.base + "/chat/completions", {method: "POST", signal,
    headers: {"Content-Type": "application/json", "Authorization": "Bearer " + key, ...p.headers},
    body: JSON.stringify({model, messages, tools, tool_choice: toolChoice, ...(p.temperature === false ? {} : {temperature: 0})})});
  const text = await r.text();
  if(!r.ok) throw refused(p, r, text);
  return JSON.parse(text).choices[0].message;
}

export async function models(p, key, signal){
  const r = await fetch(p.base + "/models", {headers: {"Authorization": "Bearer " + key, ...p.headers}, signal}), text = await r.text();
  if(!r.ok) throw refused(p, r, text);
  const ids = (JSON.parse(text).data || []).map((m) => String(m.id).replace(/^models\//, ""));     // Google names a model "models/<name>"
  if(p.free) return p.free;                                                                        // Z.ai: the key works; its list has only paid models
  return p.onlyFree ? ids.filter((i) => i.endsWith(":free")) : ids;                                 // OpenRouter: only its free models
}
