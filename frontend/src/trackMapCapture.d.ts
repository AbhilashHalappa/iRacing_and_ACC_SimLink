import type { TrackMapPoint } from "./trackMap.js";

export type TrackMapCaptureState = {
  key: string | null;
  sessionKey: string;
  previousProgress: number | null;
  capturing: boolean;
  points: TrackMapPoint[];
  validity: boolean | null;
  outLap: boolean;
  startCompletedLaps: number | null;
  pendingCandidate: {
    key: string | null;
    points: TrackMapPoint[];
    validity: boolean | null;
    outLap: boolean;
    startCompletedLaps: number | null;
  } | null;
};
export function createTrackMapCaptureState(key: string | null, sessionKey: string): TrackMapCaptureState;
export function advanceTrackMapCapture(
  current: TrackMapCaptureState,
  sample: {
    progress: number;
    point: { x: number; z: number };
    completedLaps: number | null;
    isValidLap: boolean | null;
    lastTimeMs: number | null;
    lapStatus: string | null;
  },
  options?: { minPoints?: number; minProgressStep?: number },
): { state: TrackMapCaptureState; committedPoints: TrackMapPoint[] | null; captureProgress: number | null };
