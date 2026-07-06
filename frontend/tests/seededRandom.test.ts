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
