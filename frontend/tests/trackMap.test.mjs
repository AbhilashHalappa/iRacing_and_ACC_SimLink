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
    version: 1,
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
  assert.equal(isTrackLayout(layout, "spa--endurance"), false);
  assert.equal(isTrackLayout({ ...layout, points: layout.points.slice(0, 10) }, "spa--gp"), false);
});
