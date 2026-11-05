// Execute the actual TypeScript parser and source-offset helper with copy isolated.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const source = fs.readFileSync(new URL('../src/review-values.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2023, module: ts.ModuleKind.CommonJS } }).outputText;
const exports = {};
vm.runInNewContext(compiled, { exports, Intl, require: () => ({ copy: key => key }) });
const { correctedValue, sourceSlices } = exports;
assert.equal(correctedValue('price_cents', '142.00'), 14200);
assert.equal(correctedValue('price_cents', '0.29'), 29);
assert.equal(correctedValue('shipping_cents', '0'), 0);
assert.equal(correctedValue('shipping_cents', '1000000000'), 100000000000);
assert.equal(correctedValue('tax_included', 'false'), false);
assert.equal(correctedValue('available_units', '0'), 0);
assert.equal(correctedValue('sell_unit_size', '10000'), 10000);
for (const text of ['1e2', '0x10', '-1', '1.001', ' 2', '2 ', 'NaN', 'Infinity', '1,000.00', '1000000.01']) assert.throws(() => correctedValue('price_cents', text));
for (const [kind, text] of [['min_sell_units', '0'], ['sell_unit_size', '10001'], ['available_units', '100000001'], ['tax_included', '1'], ['coverage', 'yes'], ['latest_arrival', '2026-11-12T18:00:00']]) assert.throws(() => correctedValue(kind, text));
assert.equal(correctedValue('latest_arrival', '2026-11-12T18:00:00Z'), '2026-11-12T18:00:00Z');
const text = 'A\u{1F600} price $142.00 and $129.00';
const points = Array.from(text);
const start = points.join('').indexOf('price') - 1; // UTF-16 index includes the extra surrogate.
const slices = sourceSlices(text, [{ start, end: start + 13 }, { start: start + 6, end: start + 13 }]);
assert.equal(slices.map(slice => slice.text).join(''), text);
assert.equal(slices.filter(slice => slice.marked).map(slice => slice.text).join(''), 'price $142.00');
console.log('Actual correction parser and Unicode source-offset boundaries passed.');
