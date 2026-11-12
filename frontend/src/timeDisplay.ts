/**
 * Display helpers for ACC Graphics time fields whose source units are seconds.
 * Keep these separate from millisecondsDisplay(), which is used for ms fields
 * such as lap gaps and must preserve negative deltas.
 */
export function sessionTimeDisplay(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "—";
  const totalSeconds = Math.floor(value);
  return `${String(Math.floor(totalSeconds / 60)).padStart(2, "0")}:${String(totalSeconds % 60).padStart(2, "0")}`;
}

export function penaltyTimeDisplay(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "—";
  return `${value.toFixed(1)} s`;
}
