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
