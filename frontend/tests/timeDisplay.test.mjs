import test from "node:test";
import assert from "node:assert/strict";
import { lapValidityDisplay, penaltyTimeDisplay, sessionTimeDisplay } from "../src/timeDisplay.mjs";

test("session countdown converts ACC milliseconds to mm:ss", () => {
  assert.equal(sessionTimeDisplay(1200000), "20:00");
  assert.equal(sessionTimeDisplay(65900), "01:05");
  assert.equal(sessionTimeDisplay(892512), "14:52");
  assert.equal(sessionTimeDisplay(0), "00:00");
});

test("penalty duration converts ACC milliseconds to seconds", () => {
  assert.equal(penaltyTimeDisplay(20000), "20.0 s");
  assert.equal(penaltyTimeDisplay(10000), "10.0 s");
  assert.equal(penaltyTimeDisplay(500), "0.5 s");
});

test("negative, non-finite and unavailable values are hidden", () => {
  for (const value of [-1, Number.NaN, Number.POSITIVE_INFINITY, null, undefined]) {
    assert.equal(sessionTimeDisplay(value), "—");
    assert.equal(penaltyTimeDisplay(value), "—");
  }
});

test("lap validity distinguishes known and unavailable states", () => {
  assert.equal(lapValidityDisplay(true), "VALID");
  assert.equal(lapValidityDisplay(false), "INVALID");
  for (const value of [null, undefined, "unknown", 0]) {
    assert.equal(lapValidityDisplay(value), "UNKNOWN");
  }
});
