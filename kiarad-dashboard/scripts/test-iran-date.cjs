// Compile the real utility in memory; no generated files or network needed.
const ts = require('typescript');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../lib/iran-date.ts'), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
const target = { exports: {} };
new Function('exports', 'module', compiled)(target.exports, target);
const date = target.exports;
let checks = 0;
function equal(actual, expected) { assert.equal(actual, expected); checks++; }
for (const value of ['2026-02-30', '2025-02-29', '2026-04-31', '2026-13-01', '2026-00-10']) {
  equal(date.iranDateInputToIso(value), null);
  equal(date.iranDateTimeInputToIso(`${value} 10:30`), null);
  equal(date.iranDateTimeInputToIso(`${value}T10:30:00Z`), null);
}
equal(date.iranDateInputToIso('2024-02-29'), '2024-02-29T08:30:00.000Z');
equal(date.iranDateInputToIso('۲۰۲۶-۱۰-۲۵'), '2026-10-25T08:30:00.000Z');
equal(date.iranDateInputToIso('۱۴۰۵/۰۸/۰۳'), '2026-10-25T08:30:00.000Z');
equal(date.iranDateInputToIso('1405/07/31'), null);
equal(date.iranDateTimeInputToIso('۱۴۰۵/۰۸/۰۳ ۱۰:۳۰'), '2026-10-25T07:00:00.000Z');
equal(date.iranDateTimeInputToIso('2026-10-25 24:00'), null);
equal(date.iranDateTimeInputToIso('2026-10-25 10:60'), null);
equal(date.iranDateTimeInputToIso('2026-10-25T10:30:00+03:30'), '2026-10-25T07:00:00.000Z');
for (const separator of ['/', '.', '-']) {
  const plain = `1405${separator}08${separator}03`;
  for (const digits of ['0123456789', '۰۱۲۳۴۵۶۷۸۹', '٠١٢٣٤٥٦٧٨٩']) {
    const localized = plain.replace(/\d/g, value => digits[Number(value)]);
    equal(date.iranDateInputToIso(localized), '2026-10-25T08:30:00.000Z');
    equal(date.iranDateTimeInputToIso(`${localized} 10:30`), '2026-10-25T07:00:00.000Z');
  }
  equal(date.iranDateInputToIso(`1405${separator}07${separator}31`), null);
  equal(date.iranDateTimeInputToIso(`1405${separator}07${separator}31 10:30`), null);
}
for (const time of ['24:00:00Z', '24:00Z', '24:00:00+03:30', '25:00:00Z', '10:60:00Z',
  '10:30:60Z', '10:30:00+24:00', '10:30:00+03:60', '1:30:00Z', '10:3:00Z', '10:30:0Z',
  '10:30:00junkZ', '10:30:00+0330', '10:30:00. Z']) {
  equal(date.iranDateTimeInputToIso(`2026-10-25T${time}`), null);
}
equal(date.iranDateTimeInputToIso('2026-10-25T00:00:00Z'), '2026-10-25T00:00:00.000Z');
equal(date.iranDateTimeInputToIso('2026-10-25T23:59:59.123Z'), '2026-10-25T23:59:59.123Z');
equal(date.iranDateTimeInputToIso('2026-10-25T10:30Z'), '2026-10-25T10:30:00.000Z');
equal(date.iranDateTimeInputToIso('2026-10-25T10:30:00-03:30'), '2026-10-25T14:00:00.000Z');
equal(date.iranDateTimeInputToIso('1405-08-03T10:30:00Z'), '1405-08-03T10:30:00.000Z');
for (const invalid of ['2026-02-30', '2025-02-29', '2026-04-31']) {
  equal(date.formatIranDate(invalid), 'تاریخ نامعتبر');
  equal(date.formatIranDateTime(invalid), 'تاریخ نامعتبر');
  equal(date.formatJalaliDateInput(invalid), '');
  equal(date.formatIranDateTimeInput(invalid), '');
}
equal(date.formatJalaliDateInput('2026-10-25'), '۱۴۰۵/۰۸/۰۳');
equal(date.formatJalaliDateInput('2024-02-29'), '۱۴۰۲/۱۲/۱۰');
equal(date.formatIranReportPeriod('2026-10-25'), date.formatIranDate('2026-10-25'));
equal(date.formatIranReportPeriod(' 2026-10-25 '), date.formatIranDate('2026-10-25'));
equal(date.formatIranReportPeriod('۱۴۰۵/۰۸/۰۳'), '۱۴۰۵/۰۸/۰۳');
equal(date.formatIranReportPeriod('از ابتدای سال'), 'از ابتدای سال');
equal(date.formatIranReportPeriod(null), '—');
equal(date.formatIranReportPeriod('  '), '—');
equal(date.formatIranReportPeriod('2026-02-30'), 'تاریخ نامعتبر');
console.log(JSON.stringify({ checks, passed: true, network: false }));
