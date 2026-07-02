# Canlı Şema Sinapsı (Faz 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `SpaceSpiderweb.vue` arka planındaki geodesic wireframe tüneli, gerçek veritabanı şemasından (tablolar=node, FK'ler=sinaps) beslenen, ambient sinyal ateşlemeli sinaptik ağ katmanıyla değiştirmek.

**Architecture:** Üç saf TS modülü (`seededRandom`, `synapseNetwork`, `synapseLayout`, `synapsePulse` — deterministik, DOM'suz, testli) + `SpaceSpiderweb.vue` içinde bunları tüketen bir Three.js render katmanı (tek `Points` + tek `LineSegments`, tünelin uniform sözleşmesi `time/scrollZ/blackHoleStrength/blackHoleAngle` devralınır). Spec: `docs/superpowers/specs/2026-07-02-living-schema-synapse-background-design.md`.

**Tech Stack:** Vue 3 `<script setup>` + TypeScript, Three.js (mevcut `three@0.136`), test = `node --experimental-strip-types` custom runner (framework YOK; `frontend/tests/graphSelection.test.ts` düzeni birebir izlenir).

## Global Constraints

- Çalışma branch'i: `feat/synapse-schema-background` (main'den; Task 1 Step 0 açar). PUSH YOK — kullanıcı onayı olmadan push/PR yapılmaz.
- Commit mesajlarına **Claude co-author trailer'ı EKLENMEZ** (kullanıcı talimatı).
- Saf modüllerde `Math.random()` / `Date.now()` / `new Date()` KULLANILMAZ — determinizm şart (seed'li PRNG: `mulberry32`).
- Testler `cd frontend && node --experimental-strip-types tests/<dosya>.test.ts` ile koşulur; import'larda `.ts` uzantısı açık yazılır.
- `npx vite build` her görev sonunda temiz kalmalı. `npm run build` (vue-tsc) main'de ZATEN 7 eski hatayla kırıktır — bu plan yeni vue-tsc hatası EKLEMEMELİ (kıyas listesi: ChatView `Job` unused, SchemaManager `validCustomRelations` unused, 5× `meta is of type unknown`).
- Arka plana tablo adı/etiket ÇİZİLMEZ; backend'e dokunulmaz; şema sekmesi D3 graph'ına dokunulmaz.

---

### Task 1: Seed'li PRNG yardımcıları (`seededRandom.ts`)

**Files:**
- Create: `frontend/src/utils/seededRandom.ts`
- Test: `frontend/tests/seededRandom.test.ts`

**Interfaces:**
- Consumes: —
- Produces: `hashStringToSeed(s: string): number` (FNV-1a 32-bit, unsigned), `mulberry32(seed: number): () => number` ([0,1) döndüren deterministik PRNG). Task 2/3/4 bunları import eder.

- [ ] **Step 0: Branch aç**

```bash
cd C:\Users\furkan\Desktop\SQLGen
git checkout main
git checkout -b feat/synapse-schema-background
```

- [ ] **Step 1: Failing test'i yaz**

`frontend/tests/seededRandom.test.ts`:

```ts
// Çalıştırma: node --experimental-strip-types tests/seededRandom.test.ts
import assert from 'node:assert/strict';
import { hashStringToSeed, mulberry32 } from '../src/utils/seededRandom.ts';

let failures = 0;
const test = (name: string, fn: () => void) => {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (err) {
    failures++;
    console.error(`FAIL ${name}`);
    console.error(err);
  }
};

test('mulberry32 aynı seed ile aynı diziyi üretir', () => {
  const a = mulberry32(42);
  const b = mulberry32(42);
  for (let i = 0; i < 100; i++) assert.equal(a(), b());
});

test('mulberry32 farklı seed ile farklı dizi üretir', () => {
  const a = mulberry32(1);
  const b = mulberry32(2);
  const seqA = Array.from({ length: 10 }, () => a());
  const seqB = Array.from({ length: 10 }, () => b());
  assert.notDeepEqual(seqA, seqB);
});

test('mulberry32 çıktıları [0,1) aralığındadır', () => {
  const r = mulberry32(1234567);
  for (let i = 0; i < 1000; i++) {
    const v = r();
    assert.ok(v >= 0 && v < 1, `aralık dışı: ${v}`);
  }
});

test('hashStringToSeed deterministiktir ve unsigned 32-bit döner', () => {
  assert.equal(hashStringToSeed('MUSTERI'), hashStringToSeed('MUSTERI'));
  const h = hashStringToSeed('SIPARIS');
  assert.ok(Number.isInteger(h) && h >= 0 && h <= 0xffffffff);
});

test('hashStringToSeed farklı string için farklı hash üretir', () => {
  assert.notEqual(hashStringToSeed('TABLO_A'), hashStringToSeed('TABLO_B'));
  assert.notEqual(hashStringToSeed(''), hashStringToSeed('X'));
});

if (failures > 0) {
  console.error(`\n${failures} test başarısız`);
  process.exit(1);
}
console.log('\nTüm testler geçti');
```

- [ ] **Step 2: Testin FAIL ettiğini doğrula**

Run: `cd frontend && node --experimental-strip-types tests/seededRandom.test.ts`
Expected: `ERR_MODULE_NOT_FOUND ... src/utils/seededRandom.ts` ile exit 1.

- [ ] **Step 3: Minimal implementasyonu yaz**

`frontend/src/utils/seededRandom.ts`:

```ts
// Deterministik, seed'li PRNG yardımcıları. Arka plan katmanı her açılışta
// aynı "takımyıldızı" üretmek zorunda: Math.random kullanılmaz.

/** FNV-1a 32-bit string hash — tablo adından stabil seed üretir. */
export function hashStringToSeed(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/** mulberry32 — hızlı, deterministik [0,1) PRNG. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
```

- [ ] **Step 4: Testin PASS ettiğini doğrula**

Run: `cd frontend && node --experimental-strip-types tests/seededRandom.test.ts`
Expected: 5× PASS, `Tüm testler geçti`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/seededRandom.ts frontend/tests/seededRandom.test.ts
git commit -m "feat(frontend): add deterministic seeded PRNG helpers for synapse background"
```

---

### Task 2: Ağ kurucu + prosedürel fallback (`synapseNetwork.ts`)

**Files:**
- Create: `frontend/src/utils/synapseNetwork.ts`
- Test: `frontend/tests/synapseNetwork.test.ts`

**Interfaces:**
- Consumes: `selectGraphData`, `GraphEdgeInput` (`./graphSelection.ts` — mevcut); `mulberry32` (Task 1).
- Produces:
  ```ts
  interface SynapseGraphEdge { source: string; target: string }
  interface SynapseGraph { nodes: string[]; edges: SynapseGraphEdge[]; isFallback: boolean }
  const SYNAPSE_MAX_NODES = 150;
  function buildSynapseGraph(schemaGraph: { nodes?: string[]; edges?: GraphEdgeInput[] } | null | undefined, maxNodes?: number): SynapseGraph
  function buildFallbackGraph(): SynapseGraph  // 60 node ring + 30 chord, deterministik
  ```

- [ ] **Step 1: Failing test'i yaz**

`frontend/tests/synapseNetwork.test.ts`:

```ts
// Çalıştırma: node --experimental-strip-types tests/synapseNetwork.test.ts
import assert from 'node:assert/strict';
import { buildSynapseGraph, buildFallbackGraph, SYNAPSE_MAX_NODES } from '../src/utils/synapseNetwork.ts';

const edge = (source: string, target: string) => ({
  source, target, source_col: `${source}_ID`, target_col: `${target}_ID`,
});

let failures = 0;
const test = (name: string, fn: () => void) => {
  try { fn(); console.log(`PASS ${name}`); }
  catch (err) { failures++; console.error(`FAIL ${name}`); console.error(err); }
};

test('gerçek şema graph\'ı bağlantılı tablolarla ağa dönüşür (izoleler dışarıda)', () => {
  const g = buildSynapseGraph({ nodes: ['A', 'B', 'C', 'IZOLE'], edges: [edge('A', 'B'), edge('B', 'C')] });
  assert.equal(g.isFallback, false);
  assert.deepEqual(new Set(g.nodes), new Set(['A', 'B', 'C']));
  assert.equal(g.edges.length, 2);
  assert.deepEqual(Object.keys(g.edges[0]).sort(), ['source', 'target']);
});

test('maxNodes sınırı selectGraphData üzerinden uygulanır', () => {
  const nodes = Array.from({ length: 200 }, (_, i) => `T${i}`);
  const edges = Array.from({ length: 199 }, (_, i) => edge(`T${i}`, `T${i + 1}`));
  const g = buildSynapseGraph({ nodes, edges }, 150);
  assert.equal(g.isFallback, false);
  assert.equal(g.nodes.length, 150);
  for (const e of g.edges) {
    assert.ok(g.nodes.includes(e.source) && g.nodes.includes(e.target));
  }
});

test('null/undefined/boş şema → deterministik fallback ağ', () => {
  for (const input of [null, undefined, {}, { nodes: [], edges: [] }]) {
    const g = buildSynapseGraph(input as any);
    assert.equal(g.isFallback, true);
    assert.equal(g.nodes.length, 60);
    assert.equal(g.edges.length, 90); // 60 ring + 30 chord
  }
});

test('tek tablolu / edge\'siz şema → fallback', () => {
  const g = buildSynapseGraph({ nodes: ['A'], edges: [] });
  assert.equal(g.isFallback, true);
});

test('edge\'leri yalnız bilinmeyen tablolara işaret eden şema → fallback', () => {
  const g = buildSynapseGraph({ nodes: ['A', 'B'], edges: [edge('X', 'Y')] });
  assert.equal(g.isFallback, true);
});

test('fallback ağ deterministiktir ve self-loop içermez', () => {
  const a = buildFallbackGraph();
  const b = buildFallbackGraph();
  assert.deepEqual(a, b);
  for (const e of a.edges) assert.notEqual(e.source, e.target);
});

if (failures > 0) { console.error(`\n${failures} test başarısız`); process.exit(1); }
console.log('\nTüm testler geçti');
```

- [ ] **Step 2: Testin FAIL ettiğini doğrula**

Run: `cd frontend && node --experimental-strip-types tests/synapseNetwork.test.ts`
Expected: `ERR_MODULE_NOT_FOUND ... src/utils/synapseNetwork.ts` ile exit 1.

- [ ] **Step 3: Minimal implementasyonu yaz**

`frontend/src/utils/synapseNetwork.ts`:

```ts
// Sinaptik arka plan ağının veri kaynağı: gerçek şema graph'ı varsa
// selectGraphData ile (yalnız bağlantılı tablolar, hub-öncelikli, üst sınırlı),
// yoksa seed'li prosedürel küçük-dünya ağı. Arka plan asla boş kalmaz.
import { selectGraphData, type GraphEdgeInput } from './graphSelection';
import { mulberry32 } from './seededRandom';

export interface SynapseGraphEdge { source: string; target: string }

export interface SynapseGraph {
  nodes: string[];
  edges: SynapseGraphEdge[];
  isFallback: boolean;
}

export const SYNAPSE_MAX_NODES = 150;
export const FALLBACK_NODE_COUNT = 60;
export const FALLBACK_CHORD_COUNT = 30;
const FALLBACK_SEED = 0x53514c67;

export function buildFallbackGraph(): SynapseGraph {
  const rand = mulberry32(FALLBACK_SEED);
  const nodes = Array.from({ length: FALLBACK_NODE_COUNT }, (_, i) => `synapse_${i}`);
  const edges: SynapseGraphEdge[] = [];
  for (let i = 0; i < FALLBACK_NODE_COUNT; i++) {
    edges.push({ source: nodes[i], target: nodes[(i + 1) % FALLBACK_NODE_COUNT] });
  }
  const seen = new Set<string>();
  while (seen.size < FALLBACK_CHORD_COUNT) {
    const a = Math.floor(rand() * FALLBACK_NODE_COUNT);
    const b = Math.floor(rand() * FALLBACK_NODE_COUNT);
    const gap = Math.abs(a - b);
    if (a === b || gap === 1 || gap === FALLBACK_NODE_COUNT - 1) continue;
    const key = a < b ? `${a}-${b}` : `${b}-${a}`;
    if (seen.has(key)) continue;
    seen.add(key);
    edges.push({ source: nodes[Math.min(a, b)], target: nodes[Math.max(a, b)] });
  }
  return { nodes, edges, isFallback: true };
}

export function buildSynapseGraph(
  schemaGraph: { nodes?: string[]; edges?: GraphEdgeInput[] } | null | undefined,
  maxNodes: number = SYNAPSE_MAX_NODES
): SynapseGraph {
  const nodes = schemaGraph?.nodes ?? [];
  const edges = schemaGraph?.edges ?? [];
  if (nodes.length >= 2 && edges.length >= 1) {
    const selection = selectGraphData(nodes, edges, maxNodes);
    if (selection.nodes.length >= 2 && selection.edges.length >= 1) {
      return {
        nodes: selection.nodes,
        edges: selection.edges.map((e) => ({ source: e.source, target: e.target })),
        isFallback: false,
      };
    }
  }
  return buildFallbackGraph();
}
```

- [ ] **Step 4: Testin PASS ettiğini doğrula**

Run: `cd frontend && node --experimental-strip-types tests/synapseNetwork.test.ts`
Expected: 6× PASS, `Tüm testler geçti`, exit 0.

- [ ] **Step 5: Regresyon — mevcut graphSelection testleri hâlâ geçiyor mu**

Run: `cd frontend && node --experimental-strip-types tests/graphSelection.test.ts`
Expected: 8× PASS, exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/utils/synapseNetwork.ts frontend/tests/synapseNetwork.test.ts
git commit -m "feat(frontend): synapse graph builder reusing selectGraphData with procedural fallback"
```

---

### Task 3: Deterministik 3D yerleşim (`synapseLayout.ts`)

**Files:**
- Create: `frontend/src/utils/synapseLayout.ts`
- Test: `frontend/tests/synapseLayout.test.ts`

**Interfaces:**
- Consumes: `hashStringToSeed`, `mulberry32` (Task 1); girdi şekli Task 2'nin `SynapseGraph`'ıyla yapısal uyumlu (`{ nodes: string[]; edges: {source,target}[] }`).
- Produces:
  ```ts
  interface SynapseNode { id: string; x: number; y: number; z: number; degree: number }
  interface SynapseEdge { sourceIndex: number; targetIndex: number }
  interface SynapseLayout { nodes: SynapseNode[]; edges: SynapseEdge[] }
  function computeSynapseLayout(
    graph: { nodes: string[]; edges: { source: string; target: string }[] },
    opts?: { iterations?: number; radius?: number }
  ): SynapseLayout
  ```
  Task 4 (`PulseScheduler`) ve Task 5 (render) `SynapseLayout`'u tüketir.

- [ ] **Step 1: Failing test'i yaz**

`frontend/tests/synapseLayout.test.ts`:

```ts
// Çalıştırma: node --experimental-strip-types tests/synapseLayout.test.ts
import assert from 'node:assert/strict';
import { computeSynapseLayout } from '../src/utils/synapseLayout.ts';

const e = (source: string, target: string) => ({ source, target });

let failures = 0;
const test = (name: string, fn: () => void) => {
  try { fn(); console.log(`PASS ${name}`); }
  catch (err) { failures++; console.error(`FAIL ${name}`); console.error(err); }
};

test('deterministiktir: aynı girdi → birebir aynı yerleşim', () => {
  const graph = { nodes: ['A', 'B', 'C', 'D'], edges: [e('A', 'B'), e('B', 'C'), e('C', 'D')] };
  assert.deepEqual(computeSynapseLayout(graph), computeSynapseLayout(graph));
});

test('tüm koordinatlar sonludur (NaN/Infinity yok)', () => {
  const nodes = Array.from({ length: 40 }, (_, i) => `T${i}`);
  const edges = Array.from({ length: 39 }, (_, i) => e(`T${i}`, `T${i + 1}`));
  const layout = computeSynapseLayout({ nodes, edges });
  for (const nd of layout.nodes) {
    for (const v of [nd.x, nd.y, nd.z]) assert.ok(Number.isFinite(v), `${nd.id}: ${v}`);
  }
});

test('hub merkeze yakın konumlanır (yıldız topolojisi)', () => {
  const leaves = Array.from({ length: 10 }, (_, i) => `LEAF${i}`);
  const graph = { nodes: ['HUB', ...leaves], edges: leaves.map((l) => e('HUB', l)) };
  const layout = computeSynapseLayout(graph);
  const r = (nd: { x: number; y: number; z: number }) => Math.sqrt(nd.x ** 2 + nd.y ** 2 + nd.z ** 2);
  const hub = layout.nodes.find((nd) => nd.id === 'HUB')!;
  const leafAvg = layout.nodes.filter((nd) => nd.id !== 'HUB').reduce((s, nd) => s + r(nd), 0) / 10;
  assert.ok(r(hub) < leafAvg, `hub=${r(hub).toFixed(1)} leafAvg=${leafAvg.toFixed(1)}`);
});

test('degree alanları edge listesinden doğru hesaplanır', () => {
  const layout = computeSynapseLayout({ nodes: ['A', 'B', 'C'], edges: [e('A', 'B'), e('A', 'C')] });
  const byId = new Map(layout.nodes.map((nd) => [nd.id, nd]));
  assert.equal(byId.get('A')!.degree, 2);
  assert.equal(byId.get('B')!.degree, 1);
});

test('edge\'ler indeks çiftlerine çevrilir; bilinmeyen/self-loop atlanır', () => {
  const layout = computeSynapseLayout({ nodes: ['A', 'B'], edges: [e('A', 'B'), e('A', 'A'), e('A', 'YOK')] });
  assert.equal(layout.edges.length, 1);
  assert.deepEqual(layout.edges[0], { sourceIndex: 0, targetIndex: 1 });
});

test('boş graph çökmez', () => {
  assert.deepEqual(computeSynapseLayout({ nodes: [], edges: [] }), { nodes: [], edges: [] });
});

if (failures > 0) { console.error(`\n${failures} test başarısız`); process.exit(1); }
console.log('\nTüm testler geçti');
```

- [ ] **Step 2: Testin FAIL ettiğini doğrula**

Run: `cd frontend && node --experimental-strip-types tests/synapseLayout.test.ts`
Expected: `ERR_MODULE_NOT_FOUND ... src/utils/synapseLayout.ts` ile exit 1.

- [ ] **Step 3: Minimal implementasyonu yaz**

`frontend/src/utils/synapseLayout.ts`:

```ts
// Deterministik 3D force yerleşimi: başlangıç konumları tablo-adı hash'inden,
// ~200 iterasyon yay/itme/merkez-yerçekimi. Hub'lar (yüksek degree) merkeze
// daha güçlü çekilir. 150 node için CPU maliyeti milisaniye mertebesindedir
// ve mount'ta bir kez koşar.
import { hashStringToSeed, mulberry32 } from './seededRandom';

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
```

- [ ] **Step 4: Testin PASS ettiğini doğrula**

Run: `cd frontend && node --experimental-strip-types tests/synapseLayout.test.ts`
Expected: 6× PASS, `Tüm testler geçti`, exit 0.
(Hub-merkez testi kuvvet sabitlerine duyarlıdır; FAIL ederse merkez yerçekimindeki degree katsayısını `0.02 → 0.03` yükseltip yeniden koş.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/synapseLayout.ts frontend/tests/synapseLayout.test.ts
git commit -m "feat(frontend): deterministic 3D force layout for synapse background"
```

---

### Task 4: Darbe zamanlayıcı durum makinesi (`synapsePulse.ts`)

**Files:**
- Create: `frontend/src/utils/synapsePulse.ts`
- Test: `frontend/tests/synapsePulse.test.ts`

**Interfaces:**
- Consumes: `SynapseLayout` (Task 3), `mulberry32` (Task 1).
- Produces:
  ```ts
  interface PulseSpec { edgeIndex: number; direction: 1 | -1; startTime: number; duration: number; generation: number }
  interface PulseSchedulerOptions { seed?: number; maxConcurrent?: number; intervalMinSec?: number; intervalMaxSec?: number; maxHops?: number; pulseDurationSec?: number }
  class PulseScheduler {
    constructor(layout: SynapseLayout, opts?: PulseSchedulerOptions)
    tick(now: number): PulseSpec[]        // saniye cinsinden zaman; render döngüsü clock.getElapsedTime() geçirir
    fire(nodeIds: string[], now: number): void   // Faz 2 giriş noktası; bilinmeyen id sessizce atlanır
    setEnabled(enabled: boolean): void    // false → tick []; fire no-op (prefers-reduced-motion)
  }
  ```

- [ ] **Step 1: Failing test'i yaz**

`frontend/tests/synapsePulse.test.ts`:

```ts
// Çalıştırma: node --experimental-strip-types tests/synapsePulse.test.ts
import assert from 'node:assert/strict';
import { PulseScheduler } from '../src/utils/synapsePulse.ts';
import { computeSynapseLayout } from '../src/utils/synapseLayout.ts';

const e = (source: string, target: string) => ({ source, target });
// A-B-C yolu: zincir testleri için minimal topoloji
const pathLayout = () => computeSynapseLayout({ nodes: ['A', 'B', 'C'], edges: [e('A', 'B'), e('B', 'C')] });
// Test edilen davranışı ambient ateşlemeden yalıtmak için devasa aralık
const NO_AMBIENT = { intervalMinSec: 1000, intervalMaxSec: 1000 };

let failures = 0;
const test = (name: string, fn: () => void) => {
  try { fn(); console.log(`PASS ${name}`); }
  catch (err) { failures++; console.error(`FAIL ${name}`); console.error(err); }
};

test('ilk aralık dolmadan ambient darbe yoktur', () => {
  const s = new PulseScheduler(pathLayout(), { seed: 1 });
  assert.deepEqual(s.tick(0), []);
  assert.deepEqual(s.tick(1.0), []); // intervalMin=2sn'den önce
});

test('aralık dolunca ambient darbe ateşlenir (deterministik)', () => {
  const run = () => {
    const s = new PulseScheduler(pathLayout(), { seed: 7 });
    const trace: string[] = [];
    for (let t = 0; t <= 12; t += 0.25) {
      trace.push(JSON.stringify(s.tick(t)));
    }
    return trace;
  };
  const a = run();
  const b = run();
  assert.deepEqual(a, b);
  assert.ok(a.some((frame) => frame !== '[]'), 'hiç darbe ateşlenmedi');
});

test('fire() verilen node\'dan darbe başlatır; bilinmeyen id atlanır', () => {
  const s = new PulseScheduler(pathLayout(), { seed: 1, ...NO_AMBIENT });
  s.fire(['A', 'BILINMEYEN'], 0);
  const pulses = s.tick(0.1);
  assert.equal(pulses.length, 1);
  assert.equal(pulses[0].edgeIndex, 0); // A'nın tek edge'i A-B
  assert.equal(pulses[0].generation, 0);
});

test('darbe bitince komşu edge\'e sıçrar (geldiği edge hariç), maxHops\'ta durur', () => {
  const s = new PulseScheduler(pathLayout(), { seed: 1, ...NO_AMBIENT, pulseDurationSec: 1, maxHops: 2 });
  s.fire(['A'], 0);            // gen0: A-B
  const gen1 = s.tick(1.5);    // gen0 bitti → gen1 B-C
  assert.equal(gen1.length, 1);
  assert.equal(gen1[0].edgeIndex, 1);
  assert.equal(gen1[0].generation, 1);
  const gen2 = s.tick(3.0);    // gen1 bitti → C'nin tek edge'i geldiği edge → sıçrayamaz
  assert.deepEqual(gen2, []);
});

test('eşzamanlı darbe sayısı maxConcurrent ile sınırlıdır', () => {
  const leaves = Array.from({ length: 12 }, (_, i) => `L${i}`);
  const layout = computeSynapseLayout({ nodes: ['HUB', ...leaves], edges: leaves.map((l) => e('HUB', l)) });
  const s = new PulseScheduler(layout, { seed: 1, ...NO_AMBIENT, maxConcurrent: 8 });
  s.fire(leaves, 0);
  assert.equal(s.tick(0.1).length, 8);
});

test('setEnabled(false) → tick boş döner, fire no-op olur', () => {
  const s = new PulseScheduler(pathLayout(), { seed: 1 });
  s.setEnabled(false);
  s.fire(['A'], 0);
  assert.deepEqual(s.tick(10), []);
});

if (failures > 0) { console.error(`\n${failures} test başarısız`); process.exit(1); }
console.log('\nTüm testler geçti');
```

- [ ] **Step 2: Testin FAIL ettiğini doğrula**

Run: `cd frontend && node --experimental-strip-types tests/synapsePulse.test.ts`
Expected: `ERR_MODULE_NOT_FOUND ... src/utils/synapsePulse.ts` ile exit 1.

- [ ] **Step 3: Minimal implementasyonu yaz**

`frontend/src/utils/synapsePulse.ts`:

```ts
// Sinaps darbe zamanlayıcısı — render'dan bağımsız saf durum makinesi.
// Zaman parametre olarak alınır (test edilebilirlik); render döngüsü
// clock.getElapsedTime() geçirir. Ambient ateşleme + zincirleme sıçrama +
// eşzamanlılık sınırı burada; shader yalnız aktif darbe listesini çizer.
import type { SynapseLayout } from './synapseLayout';
import { mulberry32 } from './seededRandom';

export interface PulseSpec {
  edgeIndex: number;
  direction: 1 | -1;
  startTime: number;
  duration: number;
  generation: number;
}

export interface PulseSchedulerOptions {
  seed?: number;
  maxConcurrent?: number;
  intervalMinSec?: number;
  intervalMaxSec?: number;
  maxHops?: number;
  pulseDurationSec?: number;
}

interface IncidentEdge { edgeIndex: number; otherNode: number; direction: 1 | -1 }
interface ActivePulse extends PulseSpec { arrivalNode: number }

export class PulseScheduler {
  private readonly rand: () => number;
  private readonly maxConcurrent: number;
  private readonly intervalMin: number;
  private readonly intervalMax: number;
  private readonly maxHops: number;
  private readonly duration: number;
  private readonly incidents: IncidentEdge[][];
  private readonly indexById: Map<string, number>;
  private active: ActivePulse[] = [];
  private nextAmbientAt: number | null = null;
  private enabled = true;

  constructor(layout: SynapseLayout, opts: PulseSchedulerOptions = {}) {
    this.rand = mulberry32(opts.seed ?? 1);
    this.maxConcurrent = opts.maxConcurrent ?? 8;
    this.intervalMin = opts.intervalMinSec ?? 2;
    this.intervalMax = opts.intervalMaxSec ?? 4;
    this.maxHops = opts.maxHops ?? 2;
    this.duration = opts.pulseDurationSec ?? 0.9;
    this.indexById = new Map(layout.nodes.map((nd, i) => [nd.id, i]));
    this.incidents = layout.nodes.map(() => []);
    layout.edges.forEach((e, edgeIndex) => {
      this.incidents[e.sourceIndex].push({ edgeIndex, otherNode: e.targetIndex, direction: 1 });
      this.incidents[e.targetIndex].push({ edgeIndex, otherNode: e.sourceIndex, direction: -1 });
    });
  }

  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
    if (!enabled) {
      this.active = [];
      this.nextAmbientAt = null;
    }
  }

  fire(nodeIds: string[], now: number): void {
    if (!this.enabled) return;
    for (const id of nodeIds) {
      const node = this.indexById.get(id);
      if (node === undefined) continue;
      this.spawnFromNode(node, now, 0);
    }
  }

  tick(now: number): PulseSpec[] {
    if (!this.enabled) return [];

    const finished = this.active.filter((p) => now >= p.startTime + p.duration);
    this.active = this.active.filter((p) => now < p.startTime + p.duration);
    for (const p of finished) {
      if (p.generation < this.maxHops) {
        this.spawnFromNode(p.arrivalNode, now, p.generation + 1, p.edgeIndex);
      }
    }

    if (this.nextAmbientAt === null) this.nextAmbientAt = now + this.nextInterval();
    if (now >= this.nextAmbientAt) {
      const candidates: number[] = [];
      this.incidents.forEach((inc, i) => { if (inc.length > 0) candidates.push(i); });
      if (candidates.length > 0) {
        this.spawnFromNode(candidates[Math.floor(this.rand() * candidates.length)], now, 0);
      }
      this.nextAmbientAt = now + this.nextInterval();
    }

    return this.active.map(({ arrivalNode: _arrival, ...spec }) => spec);
  }

  private nextInterval(): number {
    return this.intervalMin + this.rand() * (this.intervalMax - this.intervalMin);
  }

  private spawnFromNode(node: number, now: number, generation: number, excludeEdge?: number): void {
    if (this.active.length >= this.maxConcurrent) return;
    const options = this.incidents[node].filter((ie) => ie.edgeIndex !== excludeEdge);
    if (options.length === 0) return;
    const pick = options[Math.floor(this.rand() * options.length)];
    this.active.push({
      edgeIndex: pick.edgeIndex,
      direction: pick.direction,
      startTime: now,
      duration: this.duration,
      generation,
      arrivalNode: pick.otherNode,
    });
  }
}
```

- [ ] **Step 4: Testin PASS ettiğini doğrula**

Run: `cd frontend && node --experimental-strip-types tests/synapsePulse.test.ts`
Expected: 6× PASS, `Tüm testler geçti`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/synapsePulse.ts frontend/tests/synapsePulse.test.ts
git commit -m "feat(frontend): deterministic pulse scheduler state machine for synapse background"
```

---

### Task 5: `SpaceSpiderweb.vue` entegrasyonu (tünel → sinaps katmanı)

**Files:**
- Modify: `frontend/src/components/SpaceSpiderweb.vue` (450 satır; tünel = satır 15-19 değişkenleri, 220-358 kurulum, 397-405 uniform güncellemeleri, 409-410 rotasyon, 436-439 dispose)

**Interfaces:**
- Consumes: `buildSynapseGraph` (Task 2), `computeSynapseLayout` (Task 3), `PulseScheduler`/`PulseSpec` (Task 4), `apiService.getSchema(false)` (mevcut — şema objesi döner, graph `schema.graph.{nodes,edges}` altındadır).
- Produces: `defineExpose({ fireSignal })` — `fireSignal(tableNames: string[]): void` (Faz 2 kancası; Faz 1'de çağıran yok).

Görsel katman test edilemez (framework yok) — bu görevin doğrulaması `npx vite build` + dev server'da manuel gözlem + mevcut testlerin regresyonudur. Saf mantığın tamamı Task 1-4'te test edildi.

- [ ] **Step 1: Import'ları ve modül durumunu değiştir**

Satır 1-27 bölgesinde: `three`/`gsap` import'larından sonra ekle:

```ts
import { apiService } from '../services/api';
import { buildSynapseGraph, type SynapseGraph } from '../utils/synapseNetwork';
import { computeSynapseLayout } from '../utils/synapseLayout';
import { PulseScheduler } from '../utils/synapsePulse';
```

Tünel değişkenlerini (satır 15-19: `coreGeometry`, `coreMaterial`, `innerGeometry`, `innerMaterial`, `innerMesh`) SİL, yerine koy:

```ts
let synapseNodesGeometry: THREE.BufferGeometry | null = null;
let synapseNodesMaterial: THREE.ShaderMaterial | null = null;
let synapseEdgesGeometry: THREE.BufferGeometry | null = null;
let synapseEdgesMaterial: THREE.ShaderMaterial | null = null;
let pulseScheduler: PulseScheduler | null = null;
let synapsePulseArrays: { start: Float32Array; duration: Float32Array; dir: Float32Array } | null = null;
let sceneClock: THREE.Clock | null = null;
let isDisposed = false;
```

`blackHoleState` tanımından sonra görsel ayar sabitlerini ekle (spec §7: elle ayar tek yerden):

```ts
// Sinaps katmanı görsel ayarları — göz kararı ince ayar hep buradan yapılır
const SYNAPSE_STYLE = {
  maxNodes: 150,
  layoutRadius: 260,
  nodeBaseSize: 5.0,
  nodeSizePerDegree: 1.1,
  nodeMaxSize: 15.0,
  hubRatio: 0.1,                          // en bağlantılı %10 amber olur
  nodeColor: [0.85, 0.86, 0.92] as const, // zinc-beyaz
  hubColor: [0.98, 0.75, 0.35] as const,  // amber
  edgeOpacity: 0.14,
  pulseSeconds: 0.9,
  pulseGlowBoost: 0.75,
} as const;
```

- [ ] **Step 2: Sinaps shader'larını modül kapsamına ekle**

`SYNAPSE_STYLE`'dan sonra (onMounted DIŞINDA) ekle. Kara delik warp bloğu tünelin warp'ıyla (eski satır 264-283) birebir aynıdır — sözleşme bozulmaz:

```ts
// Kara delik warp bloğu — tünel shader'ından devralınan sözleşme (bhCenter x=85)
const SYNAPSE_WARP_GLSL = `
  if (blackHoleStrength > 0.0) {
    vec2 bhCenter = vec2(85.0, 0.0);
    vec2 distVec = pos.xy - bhCenter;
    float r = length(distVec) + 0.1;
    float swirl = (4.5 / (r * 0.03 + 2.5)) * blackHoleStrength + blackHoleAngle;
    float cosA = cos(swirl);
    float sinA = sin(swirl);
    vec2 rotatedVec = mat2(cosA, -sinA, sinA, cosA) * distVec;
    float pull = mix(1.0, pow(clamp(r / 550.0, 0.0, 1.0), 1.8), blackHoleStrength * 0.95);
    pos.xy = bhCenter + rotatedVec * pull;
    pos.z -= mix(0.0, 750.0 / (r * 0.005 + 1.0), blackHoleStrength);
  }
`;

const SYNAPSE_NODE_VERT = `
  uniform float time;
  uniform float scrollZ;
  uniform float blackHoleStrength;
  uniform float blackHoleAngle;
  attribute float size;
  attribute vec3 color;
  varying vec3 vColor;
  varying float vDepth;
  void main() {
    vColor = color;
    vec3 pos = position;
    pos.z = mod(pos.z + scrollZ + 400.0, 800.0) - 400.0;
    ${SYNAPSE_WARP_GLSL}
    vDepth = pos.z;
    vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
    float breath = 1.0 + sin(time * 1.4 + position.x * 0.08) * 0.18;
    gl_PointSize = size * breath * (300.0 / -mvPosition.z);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const SYNAPSE_NODE_FRAG = `
  uniform sampler2D pointTexture;
  varying vec3 vColor;
  varying float vDepth;
  void main() {
    vec4 texColor = texture2D(pointTexture, gl_PointCoord);
    if (texColor.a < 0.01) discard;
    float depthFade = smoothstep(-400.0, 400.0, vDepth);
    gl_FragColor = vec4(vColor, depthFade) * texColor;
  }
`;

// Edge wrap per-EDGE yapılır (aMidZ): iki uç aynı offset'i alır, sınırda
// çizgi tüm tüneli kat eden "streak" artefaktı oluşmaz.
const SYNAPSE_EDGE_VERT = `
  uniform float time;
  uniform float scrollZ;
  uniform float blackHoleStrength;
  uniform float blackHoleAngle;
  attribute float aEndpoint;
  attribute float aMidZ;
  attribute float aPulseStart;
  attribute float aPulseDuration;
  attribute float aPulseDir;
  varying float vT;
  varying float vDepth;
  varying float vPulseStart;
  varying float vPulseDuration;
  varying float vPulseDir;
  void main() {
    vT = aEndpoint;
    vPulseStart = aPulseStart;
    vPulseDuration = aPulseDuration;
    vPulseDir = aPulseDir;
    vec3 pos = position;
    float midRaw = aMidZ + scrollZ;
    float offset = (mod(midRaw + 400.0, 800.0) - 400.0) - midRaw;
    pos.z = pos.z + scrollZ + offset;
    ${SYNAPSE_WARP_GLSL}
    vDepth = pos.z;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  }
`;

const SYNAPSE_EDGE_FRAG = `
  uniform float time;
  uniform float edgeOpacity;
  uniform float pulseGlowBoost;
  varying float vT;
  varying float vDepth;
  varying float vPulseStart;
  varying float vPulseDuration;
  varying float vPulseDir;
  void main() {
    vec3 base = vec3(0.31, 0.27, 0.90);   // indigo #4f46e5
    vec3 color = base;
    float alpha = edgeOpacity;
    if (vPulseStart >= 0.0 && vPulseDuration > 0.0) {
      float p = clamp((time - vPulseStart) / vPulseDuration, 0.0, 1.0);
      if (vPulseDir < 0.0) p = 1.0 - p;
      float d = vT - p;
      float glow = exp(-d * d * 60.0);
      color = mix(base, vec3(0.13, 0.83, 0.93), glow);   // cyan #22d3ee
      alpha += glow * pulseGlowBoost;
    }
    float depthFade = smoothstep(-400.0, 400.0, vDepth);
    gl_FragColor = vec4(color, alpha * depthFade);
  }
`;
```

- [ ] **Step 3: Tünel kurulumunu sinaps katmanıyla değiştir**

`onMounted` içindeki "5. Geodesic Wireframe Tunnel" bloğunun TAMAMINI SİL (eski satır 220-358: `addBarycentricAttr`, `wireVertexShader`, `wireFragmentShader`, ico/dodec geometrileri, `outerTunnel`, `innerMesh`). Yerine (yıldız `particleSystem` eklendikten sonra, `generateStarTexture` görünürken):

```ts
  // 5. Canlı Şema Sinapsı — gerçek şemadan beslenen sinaptik ağ katmanı
  const initSynapseLayer = (graph: SynapseGraph) => {
    const layout = computeSynapseLayout(graph, { radius: SYNAPSE_STYLE.layoutRadius });
    if (layout.nodes.length === 0) return;

    const prefersReducedMotion =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    pulseScheduler = new PulseScheduler(layout, {
      seed: 7,
      pulseDurationSec: SYNAPSE_STYLE.pulseSeconds,
    });
    pulseScheduler.setEnabled(!prefersReducedMotion);

    // --- Node'lar (tek Points) ---
    const n = layout.nodes.length;
    const nodePositions = new Float32Array(n * 3);
    const nodeColors = new Float32Array(n * 3);
    const nodeSizes = new Float32Array(n);
    const sortedDegrees = layout.nodes.map((nd) => nd.degree).sort((a, b) => b - a);
    const hubThreshold = sortedDegrees[Math.max(0, Math.floor(n * SYNAPSE_STYLE.hubRatio) - 1)] ?? Infinity;
    layout.nodes.forEach((nd, i) => {
      nodePositions[i * 3] = nd.x;
      nodePositions[i * 3 + 1] = nd.y;
      nodePositions[i * 3 + 2] = nd.z;
      const c = nd.degree >= hubThreshold && nd.degree > 0 ? SYNAPSE_STYLE.hubColor : SYNAPSE_STYLE.nodeColor;
      nodeColors[i * 3] = c[0];
      nodeColors[i * 3 + 1] = c[1];
      nodeColors[i * 3 + 2] = c[2];
      nodeSizes[i] = Math.min(
        SYNAPSE_STYLE.nodeMaxSize,
        SYNAPSE_STYLE.nodeBaseSize + nd.degree * SYNAPSE_STYLE.nodeSizePerDegree
      );
    });
    synapseNodesGeometry = new THREE.BufferGeometry();
    synapseNodesGeometry.setAttribute('position', new THREE.BufferAttribute(nodePositions, 3));
    synapseNodesGeometry.setAttribute('color', new THREE.BufferAttribute(nodeColors, 3));
    synapseNodesGeometry.setAttribute('size', new THREE.BufferAttribute(nodeSizes, 1));
    synapseNodesMaterial = new THREE.ShaderMaterial({
      uniforms: {
        time: { value: 0 },
        pointTexture: { value: generateStarTexture() },
        scrollZ: { value: 0 },
        blackHoleStrength: { value: 0 },
        blackHoleAngle: { value: 0 },
      },
      vertexShader: SYNAPSE_NODE_VERT,
      fragmentShader: SYNAPSE_NODE_FRAG,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      transparent: true,
    });
    scene.add(new THREE.Points(synapseNodesGeometry, synapseNodesMaterial));

    // --- Sinaps hatları (tek LineSegments) ---
    const m = layout.edges.length;
    const edgePositions = new Float32Array(m * 6);
    const endpoint = new Float32Array(m * 2);
    const midZ = new Float32Array(m * 2);
    const pulseStart = new Float32Array(m * 2).fill(-1);
    const pulseDuration = new Float32Array(m * 2);
    const pulseDir = new Float32Array(m * 2).fill(1);
    layout.edges.forEach((e, i) => {
      const a = layout.nodes[e.sourceIndex];
      const b = layout.nodes[e.targetIndex];
      edgePositions[i * 6] = a.x; edgePositions[i * 6 + 1] = a.y; edgePositions[i * 6 + 2] = a.z;
      edgePositions[i * 6 + 3] = b.x; edgePositions[i * 6 + 4] = b.y; edgePositions[i * 6 + 5] = b.z;
      endpoint[i * 2] = 0; endpoint[i * 2 + 1] = 1;
      const mz = (a.z + b.z) / 2;
      midZ[i * 2] = mz; midZ[i * 2 + 1] = mz;
    });
    synapsePulseArrays = { start: pulseStart, duration: pulseDuration, dir: pulseDir };
    synapseEdgesGeometry = new THREE.BufferGeometry();
    synapseEdgesGeometry.setAttribute('position', new THREE.BufferAttribute(edgePositions, 3));
    synapseEdgesGeometry.setAttribute('aEndpoint', new THREE.BufferAttribute(endpoint, 1));
    synapseEdgesGeometry.setAttribute('aMidZ', new THREE.BufferAttribute(midZ, 1));
    synapseEdgesGeometry.setAttribute('aPulseStart', new THREE.BufferAttribute(pulseStart, 1));
    synapseEdgesGeometry.setAttribute('aPulseDuration', new THREE.BufferAttribute(pulseDuration, 1));
    synapseEdgesGeometry.setAttribute('aPulseDir', new THREE.BufferAttribute(pulseDir, 1));
    synapseEdgesMaterial = new THREE.ShaderMaterial({
      uniforms: {
        time: { value: 0 },
        scrollZ: { value: 0 },
        blackHoleStrength: { value: 0 },
        blackHoleAngle: { value: 0 },
        edgeOpacity: { value: SYNAPSE_STYLE.edgeOpacity },
        pulseGlowBoost: { value: SYNAPSE_STYLE.pulseGlowBoost },
      },
      vertexShader: SYNAPSE_EDGE_VERT,
      fragmentShader: SYNAPSE_EDGE_FRAG,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      transparent: true,
    });
    scene.add(new THREE.LineSegments(synapseEdgesGeometry, synapseEdgesMaterial));
  };

  // Şema fetch sonuçlanınca katman BİR KEZ kurulur (spec: ara swap yok);
  // hata/boş → prosedürel fallback. Arka plan uygulamayı asla bozamaz.
  apiService
    .getSchema(false)
    .then((schema) => buildSynapseGraph(schema?.graph ?? null, SYNAPSE_STYLE.maxNodes))
    .catch(() => buildSynapseGraph(null))
    .then((graph) => {
      if (isDisposed) return;
      try {
        initSynapseLayer(graph);
      } catch (err) {
        console.warn('[SpaceSpiderweb] Sinaps katmanı kurulamadı:', err);
      }
    });
```

Not: tablo adı → node eşlemesi için ayrı bir map TUTULMAZ — `PulseScheduler.fire` bilinmeyen id'leri zaten sessizce atlar; kullanılmayan değişken `noUnusedLocals` ile yeni vue-tsc hatası yaratırdı.

- [ ] **Step 4: Render döngüsünü güncelle**

Eski satır 370 `const clock = new THREE.Clock();` → `sceneClock = new THREE.Clock(); const clock = sceneClock;`

Tick içindeki tünel uniform blokları (eski satır 397-405: `coreMaterial...` ve `innerMaterial...`) ve `innerMesh` rotasyonları (eski satır 409-410) SİLİNİR; yerine:

```ts
    if (synapseNodesMaterial) {
      synapseNodesMaterial.uniforms.time.value = elapsedTime;
      synapseNodesMaterial.uniforms.scrollZ.value = virtualScroll;
      synapseNodesMaterial.uniforms.blackHoleStrength.value = blackHoleState.strength;
      synapseNodesMaterial.uniforms.blackHoleAngle.value = blackHoleAngle;
    }
    if (synapseEdgesMaterial && synapseEdgesGeometry && pulseScheduler && synapsePulseArrays) {
      synapseEdgesMaterial.uniforms.time.value = elapsedTime;
      synapseEdgesMaterial.uniforms.scrollZ.value = virtualScroll;
      synapseEdgesMaterial.uniforms.blackHoleStrength.value = blackHoleState.strength;
      synapseEdgesMaterial.uniforms.blackHoleAngle.value = blackHoleAngle;

      const pulses = pulseScheduler.tick(elapsedTime);
      synapsePulseArrays.start.fill(-1);
      for (const p of pulses) {
        const i0 = p.edgeIndex * 2;
        synapsePulseArrays.start[i0] = p.startTime;
        synapsePulseArrays.start[i0 + 1] = p.startTime;
        synapsePulseArrays.duration[i0] = p.duration;
        synapsePulseArrays.duration[i0 + 1] = p.duration;
        synapsePulseArrays.dir[i0] = p.direction;
        synapsePulseArrays.dir[i0 + 1] = p.direction;
      }
      (synapseEdgesGeometry.attributes.aPulseStart as THREE.BufferAttribute).needsUpdate = true;
      (synapseEdgesGeometry.attributes.aPulseDuration as THREE.BufferAttribute).needsUpdate = true;
      (synapseEdgesGeometry.attributes.aPulseDir as THREE.BufferAttribute).needsUpdate = true;
    }
```

- [ ] **Step 5: `fireSignal` kancasını ekle (Faz 2 arayüzü) ve cleanup'ı güncelle**

`watch` bloğundan sonra (onMounted DIŞINDA):

```ts
// Faz 2 kancası: sorgu pipeline'ı ilgili tablo adlarıyla çağıracak.
// Faz 1'de çağıran yok; bilinmeyen tablo adları PulseScheduler'da sessizce atlanır.
const fireSignal = (tableNames: string[]) => {
  if (!pulseScheduler || !sceneClock) return;
  pulseScheduler.fire(tableNames, sceneClock.getElapsedTime());
};
defineExpose({ fireSignal });
```

`onUnmounted` içinde tünel dispose'ları (eski satır 436-439) yerine:

```ts
    isDisposed = true;
    synapseNodesGeometry?.dispose();
    synapseNodesMaterial?.dispose();
    synapseEdgesGeometry?.dispose();
    synapseEdgesMaterial?.dispose();
```

- [ ] **Step 6: Build + regresyon doğrulaması**

```bash
cd frontend
npx vite build          # Expected: "✓ built in ..s" (chunk-size uyarısı önceden var, kabul)
node --experimental-strip-types tests/seededRandom.test.ts
node --experimental-strip-types tests/synapseNetwork.test.ts
node --experimental-strip-types tests/synapseLayout.test.ts
node --experimental-strip-types tests/synapsePulse.test.ts
node --experimental-strip-types tests/graphSelection.test.ts
```
Expected: build temiz + 5 dosyada da `Tüm testler geçti`.
Ek kontrol — yeni vue-tsc hatası eklenmediğini doğrula: `npx vue-tsc -b 2>&1 | grep -c error` çıktısı main'deki 7 satırla aynı kalmalı (SpaceSpiderweb kaynaklı yeni satır YOK).

- [ ] **Step 7: Manuel görsel doğrulama (dev server)**

Backend + frontend'i başlat (`backend: venv\Scripts\uvicorn app.main:app --port 8000`, `frontend: npm run dev`), `http://localhost:5173` aç ve şunları gözle doğrula:
1. Arka planda tünel yok; loş indigo hatlı, zinc-beyaz/amber node'lu sinaps ağı var; yıldızlar duruyor.
2. ~2-4 sn'de bir cyan darbe bir hat boyunca ilerliyor, komşuya sıçrıyor.
3. Scroll ile ağ derinlikte akıyor (streak/kopma artefaktı yok).
4. Şema sekmesine geçince ağ kara deliğe doğru bükülüyor (yıldızlarla birlikte), çıkınca düzeliyor.
5. Console'da hata yok. Backend kapalıyken sayfa yenilenince fallback ağ çiziliyor (console'da yalnız warn olabilir).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/SpaceSpiderweb.vue
git commit -m "feat(frontend): replace geodesic tunnel with schema-driven synapse background layer"
```

---

### Task 6: Dokümantasyon + kapanış doğrulaması

**Files:**
- Modify: `CHANGELOG.md` (Unreleased bölümü — `### Fixed`'ten önce `### Changed` alt bölümü eklenir; yoksa oluşturulur)

**Interfaces:**
- Consumes: Task 1-5 çıktıları (tamamlanmış feature).
- Produces: —

- [ ] **Step 1: CHANGELOG girdisi ekle**

`CHANGELOG.md` Unreleased bölümünde `### Fixed` başlığından HEMEN ÖNCE ekle:

```markdown
### Changed
- **Arka plan: Canlı Şema Sinapsı (Faz 1)** (2026-07-02 · ara iş, sprint dışı):
  `SpaceSpiderweb.vue`'daki jenerik geodesic wireframe tünel, gerçek veritabanı
  şemasından beslenen sinaptik ağ katmanıyla değiştirildi — node'lar bağlantılı
  tablolar (`graphSelection.selectGraphData` yeniden kullanımı, üst sınır 150),
  hatlar gerçek FK ilişkileri; 2-4 sn'de bir sinaps hatları boyunca ilerleyen
  ambient sinyal darbeleri (cyan), en bağlantılı ~%10 tablo amber hub. Yerleşim
  deterministik (tablo-adı hash seed'li force layout — her açılışta aynı
  takımyıldız); şema yoksa prosedürel fallback ağ. Yıldız katmanı ve kara delik
  warp senkronu korunur (uniform sözleşmesi devralındı). `prefers-reduced-motion`
  → darbeler kapalı. Faz 2 kancası `fireSignal(tableNames)` expose edildi (canlı
  sorgu tetiklemesi ileride). Saf modüller TDD ile: `frontend/src/utils/
  {seededRandom,synapseNetwork,synapseLayout,synapsePulse}.ts` +
  `frontend/tests/*.test.ts`. Spec: `docs/superpowers/specs/
  2026-07-02-living-schema-synapse-background-design.md`.
```

- [ ] **Step 2: Tam doğrulama süiti**

```bash
cd frontend
for f in tests/*.test.ts; do node --experimental-strip-types "$f" || exit 1; done
npx vite build
```
Expected: tüm test dosyaları `Tüm testler geçti`, build `✓ built`.

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: changelog entry for living schema synapse background (phase 1)"
```

Plan biter; merge/PR kararı kullanıcıya sorulur (`superpowers:finishing-a-development-branch`). PUSH/PR kullanıcı onayı olmadan YAPILMAZ.
