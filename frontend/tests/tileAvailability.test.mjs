import test from "node:test";
import assert from "node:assert/strict";
import { getBlockedTileStreams } from "../src/tileAvailability.mjs";

const allFresh = {
  physics: { state: "fresh" },
  graphics: { state: "fresh" },
  static: { state: "fresh" },
};

test("every ACC-dependent tile is blocked when ACC is disconnected", () => {
  for (const dependencies of [
    ["physics"],
    ["graphics"],
    ["static"],
    ["physics", "graphics"],
    ["graphics", "static"],
    ["physics", "graphics", "static"],
  ]) {
    assert.deepEqual(getBlockedTileStreams(false, dependencies, allFresh), dependencies);
  }
});

test("tiles without ACC dependencies remain independent", () => {
  assert.deepEqual(getBlockedTileStreams(false, [], allFresh), []);
});

test("connected ACC preserves per-stream freshness gating", () => {
  const freshness = {
    physics: { state: "fresh" },
    graphics: { state: "stale" },
    static: { state: "fresh" },
  };
  assert.deepEqual(
    getBlockedTileStreams(true, ["physics", "graphics", "static"], freshness),
    ["graphics"],
  );
});
