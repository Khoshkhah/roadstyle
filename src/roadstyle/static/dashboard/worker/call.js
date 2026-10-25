// A Web Worker's calls, both sides (the level editor's worker, editor/level_worker.js, and the studio's, ui/studio/worker.js): a message
// {type, id, ...} goes to the worker, which answers {id, ok: true, ...fields} or {id, ok: false, error}. Bytes go as transferred buffers.

/** The page's side: call(msg, transfer?) -> a Promise of the worker's answer (its fields), or a rejection with its error. When the worker
 * stops (its script or WebAssembly fails to load, no memory), every waiting call is rejected with that error, so that no call waits. */
export function caller(worker){
  let last = 0;
  const pending = new Map();
  worker.onmessage = (e) => {
    const p = pending.get(e.data.id);
    if(!p) return;
    pending.delete(e.data.id);
    e.data.ok ? p.ok(e.data) : p.no(new Error(e.data.error));
  };
  const fail = (e) => {
    const err = new Error(`the worker stopped: ${(e && e.message) || "it could not load or read a message"}`);
    pending.forEach(p => p.no(err));
    pending.clear();
  };
  worker.onerror = fail;
  worker.onmessageerror = fail;
  return (msg, transfer = []) => new Promise((ok, no) => { const id = ++last; pending.set(id, {ok, no}); worker.postMessage({...msg, id}, transfer); });
}

/** The worker's side: each message goes to handlers[msg.type](msg) after `ready`; the handler gives the answer's fields (`transfer`: the
 * buffers to transfer), or throws. */
export function answer(handlers, ready = null){
  globalThis.onmessage = async (e) => {
    const m = e.data;
    try {
      await ready;
      if(!handlers[m.type]) throw new Error(`no call ${m.type}`);
      const {transfer = [], ...out} = (await handlers[m.type](m)) || {};
      globalThis.postMessage({...out, id: m.id, ok: true}, transfer);
    } catch(err){
      globalThis.postMessage({id: m.id, ok: false, error: String((err && err.message) || err)});
    }
  };
}
