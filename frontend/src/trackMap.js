/** Pure geometry helpers for ACC's learned world-coordinate track maps. */

/**
 * @param {unknown} value
 * @returns {string}
 */
export function normalizeTrackPart(value) {
  if (typeof value !== "string") return "";
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

/**
 * Track and configuration are separate identity components. An empty
 * configuration is deliberately represented as "default", never wildcarded.
 * @param {unknown} track
 * @param {unknown} configuration
 * @returns {string | null}
 */
export function createTrackIdentity(track, configuration) {
  const trackPart = normalizeTrackPart(track);
  if (!trackPart || trackPart === "unknown-track" || trackPart === "unknown") return null;
  const configurationPart = normalizeTrackPart(configuration) || "default";
  return `${trackPart}--${configurationPart}`;
}

/**
 * Project a world-coordinate polyline into a fixed SVG viewBox while
 * preserving the circuit's aspect ratio.
 * @param {{progress:number,x:number,z:number}[]} points
 * @param {number} width
 * @param {number} height
 * @param {number} padding
 */
export function projectTrackMap(points, width = 360, height = 180, padding = 16) {
  if (!Array.isArray(points) || points.length < 2) return null;
  const valid = points.filter((point) =>
    point && Number.isFinite(point.x) && Number.isFinite(point.z)
  );
  if (valid.length < 2) return null;

  const minX = Math.min(...valid.map((point) => point.x));
  const maxX = Math.max(...valid.map((point) => point.x));
  const minZ = Math.min(...valid.map((point) => point.z));
  const maxZ = Math.max(...valid.map((point) => point.z));
  const rangeX = maxX - minX;
  const rangeZ = maxZ - minZ;
  if (rangeX < 0.01 || rangeZ < 0.01) return null;

  const usableWidth = Math.max(1, width - padding * 2);
  const usableHeight = Math.max(1, height - padding * 2);
  const scale = Math.min(usableWidth / rangeX, usableHeight / rangeZ);
  const drawnWidth = rangeX * scale;
  const drawnHeight = rangeZ * scale;
  const offsetX = (width - drawnWidth) / 2;
  const offsetY = (height - drawnHeight) / 2;
  const bounds = { minX, minZ, scale, offsetX, offsetY, width, height };

  const projected = valid.map((point) => projectWorldPoint({ x: point.x, z: point.z }, bounds));
  return {
    bounds,
    points: projected.map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(" "),
  };
}

/**
 * @param {{x:number,z:number}} point
 * @param {{minX:number,minZ:number,scale:number,offsetX:number,offsetY:number,width:number,height:number}} bounds
 */
export function projectWorldPoint(point, bounds) {
  return {
    x: bounds.offsetX + (point.x - bounds.minX) * bounds.scale,
    y: bounds.height - (bounds.offsetY + (point.z - bounds.minZ) * bounds.scale),
  };
}

/**
 * Validate cached geometry before using it as a track layout.
 * @param {any} value
 * @param {string} expectedKey
 */
export function isTrackLayout(value, expectedKey) {
  return Boolean(
    value &&
    value.version === 2 &&
    value.key === expectedKey &&
    typeof value.track === "string" &&
    typeof value.configuration === "string" &&
    Array.isArray(value.points) &&
    value.points.length >= 80 &&
    value.points.every((point) =>
      point &&
      Number.isFinite(point.progress) &&
      Number.isFinite(point.x) &&
      Number.isFinite(point.z)
    )
  );
}
