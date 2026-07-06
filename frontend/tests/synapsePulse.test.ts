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
