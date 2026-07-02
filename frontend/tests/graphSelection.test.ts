// Şema graph node/edge seçim mantığı testleri.
// Çalıştırma: node --experimental-strip-types tests/graphSelection.test.ts
import assert from 'node:assert/strict';
import { selectGraphData } from '../src/utils/graphSelection.ts';

type Edge = { source: string; target: string; source_col: string; target_col: string; type?: string };

const edge = (source: string, target: string): Edge => ({
  source,
  target,
  source_col: `${source}_ID`,
  target_col: `${target}_ID`,
});

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

test('izole tablolar (ilişkisi olmayanlar) graph dışında bırakılır', () => {
  const nodes = ['A', 'B', 'IZOLE1', 'IZOLE2'];
  const edges = [edge('A', 'B')];
  const result = selectGraphData(nodes, edges, 0);
  assert.deepEqual(new Set(result.nodes), new Set(['A', 'B']));
  assert.equal(result.edges.length, 1);
  assert.equal(result.isolatedCount, 2);
  assert.equal(result.totalConnected, 2);
});

test('maxNodes=0 tüm bağlantılı tabloları ve tüm ilişkileri döndürür', () => {
  const nodes = ['A', 'B', 'C', 'D', 'IZOLE'];
  const edges = [edge('A', 'B'), edge('B', 'C'), edge('C', 'D')];
  const result = selectGraphData(nodes, edges, 0);
  assert.equal(result.nodes.length, 4);
  assert.equal(result.edges.length, 3);
});

test('maxNodes>0 en çok bağlantılı (hub) tablolarla sınırlar', () => {
  // B degree=3 (hub), A/C/D degree=1
  const nodes = ['A', 'B', 'C', 'D'];
  const edges = [edge('A', 'B'), edge('B', 'C'), edge('B', 'D')];
  const result = selectGraphData(nodes, edges, 2);
  assert.equal(result.nodes.length, 2);
  assert.equal(result.nodes[0], 'B'); // en yüksek degree önce
  // seçilen 2 node arasında kalan edge'ler korunur
  for (const e of result.edges) {
    assert.ok(result.nodes.includes(e.source) && result.nodes.includes(e.target));
  }
});

test('limit uygulansa bile izole tablolar hub havuzuna giremez', () => {
  // Eski bug: top-N tüm tablolar arasından seçilince izole tablolar da giriyordu
  const nodes = ['IZOLE1', 'IZOLE2', 'IZOLE3', 'A', 'B'];
  const edges = [edge('A', 'B')];
  const result = selectGraphData(nodes, edges, 4);
  assert.deepEqual(new Set(result.nodes), new Set(['A', 'B']));
  assert.equal(result.edges.length, 1);
});

test('edge tipi ve kolon bilgileri korunur', () => {
  const nodes = ['A', 'B'];
  const edges: Edge[] = [{ source: 'A', target: 'B', source_col: 'X', target_col: 'Y', type: 'implicit' }];
  const result = selectGraphData(nodes, edges, 0);
  assert.equal(result.edges[0].type, 'implicit');
  assert.equal(result.edges[0].source_col, 'X');
  assert.equal(result.edges[0].target_col, 'Y');
});

test('node listesinde olmayan tabloya işaret eden edge güvenle atlanır', () => {
  const nodes = ['A', 'B'];
  const edges = [edge('A', 'B'), edge('A', 'GIZLI_TABLO')];
  const result = selectGraphData(nodes, edges, 0);
  assert.deepEqual(new Set(result.nodes), new Set(['A', 'B']));
  assert.equal(result.edges.length, 1);
});

test('döndürülen edge objeleri girdinin kopyasıdır (D3 mutasyonundan korunma)', () => {
  const nodes = ['A', 'B'];
  const input = [edge('A', 'B')];
  const result = selectGraphData(nodes, input, 0);
  assert.notEqual(result.edges[0], input[0]);
  (result.edges[0] as any).source = { id: 'A' }; // D3 forceLink davranışı
  assert.equal(input[0].source, 'A');
});

test('boş graph çökmez', () => {
  const result = selectGraphData([], [], 0);
  assert.deepEqual(result.nodes, []);
  assert.deepEqual(result.edges, []);
  assert.equal(result.isolatedCount, 0);
});

if (failures > 0) {
  console.error(`\n${failures} test başarısız`);
  process.exit(1);
}
console.log('\nTüm testler geçti');
