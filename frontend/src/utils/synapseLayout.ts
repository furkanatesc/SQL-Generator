// Deterministik 3D force yerleşimi: başlangıç konumları tablo-adı hash'inden,
// ~200 iterasyon yay/itme/merkez-yerçekimi. Hub'lar (yüksek degree) merkeze
// daha güçlü çekilir. 150 node için CPU maliyeti milisaniye mertebesindedir
// ve mount'ta bir kez koşar.
import { hashStringToSeed, mulberry32 } from './seededRandom.ts';

export interface SynapseNode { id: string; x: number; y: number; z: number; degree: number }
export interface SynapseEdge { sourceIndex: number; targetIndex: number }
export interface SynapseLayout { nodes: SynapseNode[]; edges: SynapseEdge[] }
export interface SynapseLayoutOptions { iterations?: number; radius?: number }

export function computeSynapseLayout(
  graph: { nodes: string[]; edges: { source: string; target: string }[] },
  opts: SynapseLayoutOptions = {}
): SynapseLayout {
  const iterations = opts.iterations ?? 200;
  const radius = opts.radius ?? 260;
  const ids = graph.nodes;
  const n = ids.length;
  if (n === 0) return { nodes: [], edges: [] };

  const indexById = new Map<string, number>();
  ids.forEach((id, i) => indexById.set(id, i));

  const edges: SynapseEdge[] = [];
  const degree = new Float64Array(n);
  for (const e of graph.edges) {
    const s = indexById.get(e.source);
    const t = indexById.get(e.target);
    if (s === undefined || t === undefined || s === t) continue;
    edges.push({ sourceIndex: s, targetIndex: t });
    degree[s]++;
    degree[t]++;
  }

  // Deterministik başlangıç: her node kendi adının hash'inden küre içi konum alır
  const px = new Float64Array(n);
  const py = new Float64Array(n);
  const pz = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const rand = mulberry32(hashStringToSeed(ids[i]));
    const u = rand() * 2 - 1;
    const theta = rand() * Math.PI * 2;
    const r = radius * Math.cbrt(rand());
    const s = Math.sqrt(Math.max(0, 1 - u * u));
    px[i] = r * s * Math.cos(theta);
    py[i] = r * s * Math.sin(theta);
    pz[i] = r * u;
  }

  const REST = radius * 0.35;
  const SPRING = 0.02;
  const REPULSE = radius * radius * 0.02;
  let maxDegree = 1;
  for (let i = 0; i < n; i++) maxDegree = Math.max(maxDegree, degree[i]);

  const fx = new Float64Array(n);
  const fy = new Float64Array(n);
  const fz = new Float64Array(n);
  for (let it = 0; it < iterations; it++) {
    fx.fill(0); fy.fill(0); fz.fill(0);

    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let dx = px[i] - px[j];
        let dy = py[i] - py[j];
        let dz = pz[i] - pz[j];
        const d2 = dx * dx + dy * dy + dz * dz + 1;
        const f = REPULSE / d2;
        const d = Math.sqrt(d2);
        dx /= d; dy /= d; dz /= d;
        fx[i] += dx * f; fy[i] += dy * f; fz[i] += dz * f;
        fx[j] -= dx * f; fy[j] -= dy * f; fz[j] -= dz * f;
      }
    }

    for (const e of edges) {
      const i = e.sourceIndex;
      const j = e.targetIndex;
      let dx = px[j] - px[i];
      let dy = py[j] - py[i];
      let dz = pz[j] - pz[i];
      const d = Math.sqrt(dx * dx + dy * dy + dz * dz) + 1e-6;
      const f = SPRING * (d - REST);
      dx /= d; dy /= d; dz /= d;
      fx[i] += dx * f; fy[i] += dy * f; fz[i] += dz * f;
      fx[j] -= dx * f; fy[j] -= dy * f; fz[j] -= dz * f;
    }

    for (let i = 0; i < n; i++) {
      const g = 0.004 + 0.02 * (degree[i] / maxDegree);
      fx[i] -= px[i] * g; fy[i] -= py[i] * g; fz[i] -= pz[i] * g;
    }

    const cool = 1 - it / iterations;
    const step = 4 * cool + 0.4;
    for (let i = 0; i < n; i++) {
      const f = Math.sqrt(fx[i] * fx[i] + fy[i] * fy[i] + fz[i] * fz[i]);
      const cap = Math.min(f, step) / (f + 1e-9);
      px[i] += fx[i] * cap; py[i] += fy[i] * cap; pz[i] += fz[i] * cap;
    }
  }

  return {
    nodes: ids.map((id, i) => ({ id, x: px[i], y: py[i], z: pz[i], degree: degree[i] })),
    edges,
  };
}
