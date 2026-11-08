import assert from "node:assert/strict";
import { microphoneErrorMessage } from "../kiarad-dashboard/lib/voice-errors.ts";

const cases = [
  ["NotAllowedError", "حریم خصوصی"],
  ["NotFoundError", "میکروفون فعالی"],
  ["NotReadableError", "مشغول"],
  ["NotSupportedError", "قالب"],
  ["TimeoutError", "زمان لازم"],
  ["AbortError", "قطع"],
  ["OverconstrainedError", "تنظیمات میکروفون"],
];
for (const [name, expected] of cases) {
  assert.ok(microphoneErrorMessage({ name }).includes(expected), name);
}
assert.ok(microphoneErrorMessage({ name: "UnexpectedError" }).includes("شروع ضبط ممکن نشد"));
assert.ok(!microphoneErrorMessage({ name: "NotFoundError" }).includes("رد کرد"));
console.log("VOICE_ERROR_CHECKS", cases.length + 2, "passed");
