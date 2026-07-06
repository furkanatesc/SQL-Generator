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
