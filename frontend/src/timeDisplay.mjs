/** Display helpers for normalized Overview timing and lap-status fields. */
export function lapValidityDisplay(value) {
  if (value === true) return "VALID";
  if (value === false) return "INVALID";
  return "UNKNOWN";
}
/** Display helper for ACC Graphics time fields. */
export function sessionTimeDisplay(value) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "—";
  // ACC Graphics exposes session_time_left_s in milliseconds despite the field suffix.
  const totalSeconds = Math.floor(value / 1000);
  return `${String(Math.floor(totalSeconds / 60)).padStart(2, "0")}:${String(totalSeconds % 60).padStart(2, "0")}`;
}

/** ACC penalty_time_s is exposed in milliseconds despite its field suffix. */
export function penaltyTimeDisplay(value) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "—";
  return `${(value / 1000).toFixed(1)} s`;
}
