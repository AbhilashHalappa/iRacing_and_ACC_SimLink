import test from "node:test";
import assert from "node:assert/strict";
import { penaltyTimeDisplay, sessionTimeDisplay } from "../src/timeDisplay.js";

test("session countdown is interpreted directly as seconds", () => {
  assert.equal(sessionTimeDisplay(1200), "20:00");
  assert.equal(sessionTimeDisplay(65.9), "01:05");
  assert.equal(sessionTimeDisplay(0), "00:00");
});

test("penalty duration is interpreted directly as seconds", () => {
  assert.equal(penaltyTimeDisplay(10), "10.0 s");
  assert.equal(penaltyTimeDisplay(0.5), "0.5 s");
});

test("negative, non-finite and unavailable second values are hidden", () => {
  for (const value of [-1, Number.NaN, Number.POSITIVE_INFINITY, null, undefined]) {
    assert.equal(sessionTimeDisplay(value), "—");
    assert.equal(penaltyTimeDisplay(value), "—");
  }
});
