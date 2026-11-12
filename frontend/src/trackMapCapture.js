/** Pure lap-gated capture state for ACC-derived track geometry. */

const DEFAULT_MIN_POINTS = 80;
const DEFAULT_MIN_PROGRESS_STEP = 0.001;

function isOutLapStatus(value) {
  return ["out", "out_lap", "out-lap"].includes(String(value ?? "").trim().toLowerCase());
}

function validCandidate(candidate, expectedKey, minPoints) {
  const points = candidate?.points;
  return Boolean(
    candidate &&
    candidate.key === expectedKey &&
    candidate.validity === true &&
    candidate.outLap === false &&
    Number.isInteger(candidate.startCompletedLaps) &&
    Array.isArray(points) &&
    points.length >= minPoints &&
    points[0]?.progress <= 0.05 &&
    points[points.length - 1]?.progress >= 0.95 &&
    points.every((point) =>
      point &&
      Number.isFinite(point.progress) &&
      Number.isFinite(point.x) &&
      Number.isFinite(point.z)
    )
  );
}

/** @param {string|null} key @param {string} sessionKey */
export function createTrackMapCaptureState(key, sessionKey) {
  return {
    key,
    sessionKey,
    previousProgress: null,
    capturing: false,
    points: [],
    validity: null,
    outLap: false,
    startCompletedLaps: null,
    pendingCandidate: null,
  };
}

/**
 * Advance capture using one coherent Graphics sample.
 * A candidate is returned only after ACC increments completed_laps and reports
 * a completed lap time. Validity is latched for the entire captured lap.
 *
 * @param {ReturnType<typeof createTrackMapCaptureState>} current
 * @param {{progress:number, point:{x:number,z:number}, completedLaps:number|null, isValidLap:boolean|null, lastTimeMs:number|null, lapStatus:string|null}} sample
 * @param {{minPoints?:number,minProgressStep?:number}} [options]
 */
export function advanceTrackMapCapture(current, sample, options = {}) {
  const minPoints = options.minPoints ?? DEFAULT_MIN_POINTS;
  const minProgressStep = options.minProgressStep ?? DEFAULT_MIN_PROGRESS_STEP;
  const progress = sample.progress;
  const point = sample.point;
  if (
    !Number.isFinite(progress) || progress < 0 || progress > 1 ||
    !point || !Number.isFinite(point.x) || !Number.isFinite(point.z)
  ) {
    return { state: current, committedPoints: null, captureProgress: null };
  }

  let state = { ...current };
  let committedPoints = null;
  const outLapNow = isOutLapStatus(sample.lapStatus);
  const completedLaps = Number.isInteger(sample.completedLaps) ? sample.completedLaps : null;
  const lastTimeMs = Number.isFinite(sample.lastTimeMs) && sample.lastTimeMs > 0 ? sample.lastTimeMs : null;

  const confirmPending = () => {
    const candidate = state.pendingCandidate;
    if (!candidate) return;
    if (
      completedLaps === candidate.startCompletedLaps + 1 &&
      lastTimeMs !== null
    ) {
      if (validCandidate(candidate, state.key, minPoints)) {
        committedPoints = candidate.points;
      }
      state.pendingCandidate = null;
    } else if (
      completedLaps !== null && completedLaps > candidate.startCompletedLaps + 1
    ) {
      state.pendingCandidate = null;
    } else if (progress > 0.12) {
      // The lap counter should confirm the crossing near the start of the next lap.
      state.pendingCandidate = null;
    }
  };

  // Resolve a candidate that was waiting for ACC's completed-lap counter/time.
  confirmPending();

  const crossedStartFinish = state.previousProgress !== null &&
    state.previousProgress > 0.9 && progress < 0.1;

  if (crossedStartFinish) {
    if (state.capturing && state.points.length >= minPoints) {
      state.pendingCandidate = {
        key: state.key,
        points: state.points,
        validity: state.validity,
        outLap: state.outLap,
        startCompletedLaps: state.startCompletedLaps,
      };
      // ACC can update the lap counter and last time on this same sample.
      confirmPending();
    }

    state = {
      ...state,
      previousProgress: progress,
      capturing: true,
      points: [{ progress, x: point.x, z: point.z }],
      validity: null,
      // The crossing sample still describes the lap that just ended; begin the next lap cleanly.
      outLap: false,
      startCompletedLaps: completedLaps,
    };
    return {
      state,
      committedPoints,
      captureProgress: 0,
    };
  }

  if (!state.capturing) {
    state.previousProgress = progress;
    return { state, committedPoints, captureProgress: null };
  }

  const last = state.points[state.points.length - 1];
  if (last && progress < last.progress - 0.02) {
    // Teleport/session reset/discontinuous progress invalidates this candidate.
    state.capturing = false;
    state.points = [];
    state.validity = false;
    state.outLap = true;
    state.startCompletedLaps = null;
    state.previousProgress = progress;
    return { state, committedPoints, captureProgress: null };
  }

  if (!last || progress - last.progress >= minProgressStep) {
    state.points = [...state.points, { progress, x: point.x, z: point.z }];
  }
  if (sample.isValidLap === false) state.validity = false;
  else if (sample.isValidLap === true && state.validity === null) state.validity = true;
  if (outLapNow) state.outLap = true;
  state.previousProgress = progress;

  return { state, committedPoints, captureProgress: progress };
}
