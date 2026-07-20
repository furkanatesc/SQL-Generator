// Backend hata envelope'undan mesaj çıkarma testleri.
// Çalıştırma: node --experimental-strip-types tests/apiError.test.ts
import assert from 'node:assert/strict';
import { extractApiErrorMessage } from '../src/utils/apiError.ts';

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

test('backend envelope mesajı çıkarılır', () => {
  const data = { error: { code: 'not_found', message: 'Kayıt bulunamadı', details: null } };
  assert.equal(extractApiErrorMessage(data, 'fallback'), 'Kayıt bulunamadı');
});

test('FastAPI varsayılan detail biçimi geriye dönük desteklenir', () => {
  assert.equal(extractApiErrorMessage({ detail: 'Doğrulama hatası' }, 'fallback'), 'Doğrulama hatası');
});

test('envelope varsa detail yerine envelope kazanır', () => {
  const data = { error: { message: 'envelope' }, detail: 'eski' };
  assert.equal(extractApiErrorMessage(data, 'fallback'), 'envelope');
});

test('boş gövdede fallback döner', () => {
  assert.equal(extractApiErrorMessage({}, 'fallback'), 'fallback');
});

test('null / undefined gövdede fallback döner', () => {
  assert.equal(extractApiErrorMessage(null, 'fallback'), 'fallback');
  assert.equal(extractApiErrorMessage(undefined, 'fallback'), 'fallback');
});

test('boş string mesaj fallback sayılır', () => {
  assert.equal(extractApiErrorMessage({ error: { message: '' } }, 'fallback'), 'fallback');
  assert.equal(extractApiErrorMessage({ detail: '' }, 'fallback'), 'fallback');
});

test('mesaj string değilse fallback döner (bozuk gövdede çökmez)', () => {
  assert.equal(extractApiErrorMessage({ error: { message: { nested: 1 } } }, 'fallback'), 'fallback');
  assert.equal(extractApiErrorMessage({ detail: ['a'] }, 'fallback'), 'fallback');
  assert.equal(extractApiErrorMessage({ error: 'düz metin' }, 'fallback'), 'fallback');
  assert.equal(extractApiErrorMessage('düz metin gövde', 'fallback'), 'fallback');
});

if (failures > 0) {
  console.error(`\n${failures} test başarısız`);
  process.exit(1);
}
console.log('\nTüm testler geçti');
