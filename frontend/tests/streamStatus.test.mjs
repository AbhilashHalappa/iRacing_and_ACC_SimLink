import test from "node:test";
import assert from "node:assert/strict";
import { getStreamDisplayState } from "../src/streamStatus.mjs";

test("all stream indicators wait while ACC is disconnected", () => {
  for (const state of ["fresh", "stale", "unavailable", "missing"]) {
    assert.equal(getStreamDisplayState(false, state), "waiting");
  }
});

test("connected ACC preserves each stream's independent health state", () => {
  assert.equal(getStreamDisplayState(true, "fresh"), "fresh");
  assert.equal(getStreamDisplayState(true, "stale"), "stale");
  assert.equal(getStreamDisplayState(true, "unavailable"), "unavailable");
  assert.equal(getStreamDisplayState(true, null), "missing");
});
