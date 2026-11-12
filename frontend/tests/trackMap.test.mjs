import test from "node:test";
import assert from "node:assert/strict";
import { createTrackIdentity, projectTrackMap, projectWorldPoint, isTrackLayout } from "../src/trackMap.js";

test("track identity separates layouts and normalizes ACC names", () => {
  assert.equal(createTrackIdentity("Mount Panorama", "Bathurst"), "mount-panorama--bathurst");
  assert.notEqual(createTrackIdentity("Mount Panorama", "Bathurst"), createTrackIdentity("Mount Panorama", "Default"));
  assert.equal(createTrackIdentity("Spa-Francorchamps", ""), "spa-francorchamps--default");
  assert.equal(createTrackIdentity("unknown-track", ""), null);
});

test("track projection preserves aspect ratio and fits the SVG viewport", () => {
  const points = [
    { progress: 0, x: 0, z: 0 },
    { progress: 0.5, x: 100, z: 0 },
    { progress: 1, x: 100, z: 50 },
  ];
  const projected = projectTrackMap(points, 360, 180, 16);
  assert.ok(projected);
  const coords = projected.points.split(" ").map((pair) => pair.split(",").map(Number));
  for (const [x, y] of coords) {
    assert.ok(x >= 16 && x <= 344);
    assert.ok(y >= 16 && y <= 164);
  }
  assert.equal(projected.bounds.scale, Math.min(328 / 100, 148 / 50));
});

test("live world position uses the same transform as the stored circuit", () => {
  const projected = projectTrackMap([
    { progress: 0, x: -50, z: -25 },
    { progress: 1, x: 50, z: 25 },
  ]);
  assert.ok(projected);
  const start = projectWorldPoint({ x: -50, z: -25 }, projected.bounds);
  const finish = projectWorldPoint({ x: 50, z: 25 }, projected.bounds);
  assert.ok(start.x < finish.x);
  assert.ok(start.y > finish.y);
});

test("cached layouts must match the exact track/configuration identity", () => {
  const layout = {
    version: 2,
    key: "spa--gp",
    track: "spa",
    configuration: "gp",
    points: Array.from({ length: 80 }, (_, index) => ({
      progress: index / 79,
      x: Math.cos(index / 79 * Math.PI * 2) * 100,
      z: Math.sin(index / 79 * Math.PI * 2) * 50,
    })),
  };
  assert.equal(isTrackLayout(layout, "spa--gp"), true);
  assert.equal(isTrackLayout({ ...layout, version: 1 }, "spa--gp"), false);
  assert.equal(isTrackLayout(layout, "spa--endurance"), false);
  assert.equal(isTrackLayout({ ...layout, points: layout.points.slice(0, 10) }, "spa--gp"), false);
});


import {
  advanceTrackMapCapture,
  createTrackMapCaptureState,
} from "../src/trackMapCapture.js";

function captureOneLap({ invalidateAt = null, outLapAt = null } = {}) {
  let state = createTrackMapCaptureState("spa--gp", "spa--gp|session");
  const sample = (progress, overrides = {}) => {
    const result = advanceTrackMapCapture(state, {
      progress,
      point: { x: Math.cos(progress * Math.PI * 2) * 100, z: Math.sin(progress * Math.PI * 2) * 100 },
      completedLaps: 0,
      isValidLap: true,
      lastTimeMs: null,
      lapStatus: null,
      ...overrides,
    }, { minPoints: 80 });
    state = result.state;
    return result;
  };

  sample(0.95);
  sample(0.02);
  let invalidated = false;
  let outLapMarked = false;
  for (let index = 1; index <= 96; index += 1) {
    const progress = 0.02 + index * 0.01;
    const invalidate = invalidateAt !== null && !invalidated && progress >= invalidateAt;
    const outLap = outLapAt !== null && !outLapMarked && progress >= outLapAt;
    if (invalidate) invalidated = true;
    if (outLap) outLapMarked = true;
    sample(progress, {
      isValidLap: invalidate ? false : true,
      lapStatus: outLap ? "out" : null,
    });
  }
  return { state, sample };
}

test("track map is committed only after ACC confirms a completed valid lap", () => {
  const { state: capturedState } = captureOneLap();
  let state = capturedState;
  const result = advanceTrackMapCapture(state, {
    progress: 0.01,
    point: { x: Math.cos(0.01 * Math.PI * 2) * 100, z: Math.sin(0.01 * Math.PI * 2) * 100 },
    completedLaps: 1,
    isValidLap: true,
    lastTimeMs: 91234,
    lapStatus: null,
  }, { minPoints: 80 });
  assert.ok(result.committedPoints);
  assert.ok(result.committedPoints.length >= 80);
  assert.equal(result.state.capturing, true);
});

test("invalidity is latched for the whole lap and prevents map replacement", () => {
  const { state } = captureOneLap({ invalidateAt: 0.45 });
  const result = advanceTrackMapCapture(state, {
    progress: 0.01,
    point: { x: 1, z: 0 },
    completedLaps: 1,
    isValidLap: true,
    lastTimeMs: 91234,
    lapStatus: null,
  }, { minPoints: 80 });
  assert.equal(result.committedPoints, null);
});

test("out-laps cannot produce a cached track layout", () => {
  const { state } = captureOneLap({ outLapAt: 0.4 });
  const result = advanceTrackMapCapture(state, {
    progress: 0.01,
    point: { x: 1, z: 0 },
    completedLaps: 1,
    isValidLap: true,
    lastTimeMs: 91234,
    lapStatus: null,
  }, { minPoints: 80 });
  assert.equal(result.committedPoints, null);
});

test("map candidate waits for ACC completed-lap confirmation", () => {
  const { state } = captureOneLap();
  const crossing = advanceTrackMapCapture(state, {
    progress: 0.01,
    point: { x: 1, z: 0 },
    completedLaps: 0,
    isValidLap: true,
    lastTimeMs: null,
    lapStatus: null,
  }, { minPoints: 80 });
  assert.equal(crossing.committedPoints, null);
  const confirmed = advanceTrackMapCapture(crossing.state, {
    progress: 0.025,
    point: { x: Math.cos(0.025 * Math.PI * 2) * 100, z: Math.sin(0.025 * Math.PI * 2) * 100 },
    completedLaps: 1,
    isValidLap: true,
    lastTimeMs: 91234,
    lapStatus: null,
  }, { minPoints: 80 });
  assert.ok(confirmed.committedPoints);
});

test("teleport or incomplete progress cannot be committed as a lap", () => {
  let state = createTrackMapCaptureState("spa--gp", "session");
  const step = (progress) => {
    const result = advanceTrackMapCapture(state, {
      progress,
      point: { x: progress * 10, z: progress * 5 },
      completedLaps: 0,
      isValidLap: true,
      lastTimeMs: null,
      lapStatus: null,
    }, { minPoints: 5 });
    state = result.state;
    return result;
  };
  step(0.95);
  step(0.02);
  step(0.2);
  const teleported = step(0.1);
  assert.equal(teleported.state.capturing, false);
  assert.equal(teleported.committedPoints, null);
});


test("world-coordinate teleport cannot masquerade as a start-finish crossing", () => {
  let state = createTrackMapCaptureState("spa--gp", "session");
  const step = (progress, x, z) => {
    const result = advanceTrackMapCapture(state, {
      progress,
      point: { x, z },
      completedLaps: 0,
      isValidLap: true,
      lastTimeMs: null,
      lapStatus: null,
    }, { minPoints: 5 });
    state = result.state;
    return result;
  };
  step(0.95, 0, 0);
  step(0.02, 4, 2);
  step(0.2, 20, 10);
  const teleported = step(0.03, 500, 500);
  assert.equal(teleported.state.capturing, false);
  assert.equal(teleported.state.pendingCandidate, null);
  assert.equal(teleported.committedPoints, null);
});
