/** Display helpers for ACC Graphics time fields. */
export function sessionTimeDisplay(value) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "—";
  const totalSeconds = Math.floor(value);
  return `${String(Math.floor(totalSeconds / 60)).padStart(2, "0")}:${String(totalSeconds % 60).padStart(2, "0")}`;
}

/** ACC penalty_time_s is exposed in milliseconds despite its field suffix. */
export function penaltyTimeDisplay(value) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "—";
  return `${(value / 1000).toFixed(1)} s`;
}
