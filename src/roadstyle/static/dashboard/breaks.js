// NATURAL BREAKS for live data (Fisher-Jenks): the cut points that split numbers into k sets so that the numbers inside a set are as close
// as possible (the least sum of squares). The sets have different numbers of members: they follow the gaps in the data.
// More than MAXP different values: the values are first merged into MAXP groups of about the same size, and the cuts fall between groups.
const MAXP = 800;
// the points {x: mean, w: weight, lo: smallest value}: equal values are one point
function points(sorted){
  const p = [];
  for(const v of sorted){ const q = p[p.length - 1]; if(q && q.lo === v) q.w++; else p.push({x: v, w: 1, lo: v}); }
  if(p.length <= MAXP) return p;
  const total = sorted.length, out = [];
  let cur = null;
  for(const q of p){
    if(!cur) cur = {s: q.x * q.w, w: q.w, lo: q.lo}; else { cur.s += q.x * q.w; cur.w += q.w; }
    if(cur.w >= total / MAXP){ out.push({x: cur.s / cur.w, w: cur.w, lo: cur.lo}); cur = null; }
  }
  if(cur) out.push({x: cur.s / cur.w, w: cur.w, lo: cur.lo});
  return out;
}
// the k-1 cut points, ascending: a value v is in set n, where n is the number of cuts that are <= v. Fewer cuts when there are fewer different values.
export function naturalBreaks(values, k){
  const p = points(values.filter(v => typeof v === "number" && isFinite(v)).sort((a, b) => a - b)), m = p.length;
  k = Math.min(k, m);
  if(k < 2) return [];
  const W = new Float64Array(m + 1), S1 = new Float64Array(m + 1), S2 = new Float64Array(m + 1);
  p.forEach((q, i) => { W[i + 1] = W[i] + q.w; S1[i + 1] = S1[i] + q.w * q.x; S2[i + 1] = S2[i] + q.w * q.x * q.x; });
  const sse = (i, j) => { const w = W[j + 1] - W[i], s = S1[j + 1] - S1[i]; return S2[j + 1] - S2[i] - s * s / w; };   // points i..j in one set
  const D = [Float64Array.from({length: m}, (_, j) => sse(0, j))], B = [new Int32Array(m)];
  for(let c = 1; c < k; c++){
    const d = new Float64Array(m).fill(Infinity), b = new Int32Array(m);
    for(let j = c; j < m; j++) for(let i = c; i <= j; i++){ const x = D[c - 1][i - 1] + sse(i, j); if(x < d[j]){ d[j] = x; b[j] = i; } }
    D.push(d); B.push(b);
  }
  const cuts = [];
  for(let c = k - 1, j = m - 1; c >= 1; c--){ const i = B[c][j]; cuts.push(p[i].lo); j = i - 1; }
  return cuts.reverse();
}
// the set of a value: the number of cuts that are <= the value
export const setOf = (cuts, v) => cuts.filter(c => c <= v).length;
