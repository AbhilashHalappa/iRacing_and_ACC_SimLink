export type TrackMapPoint = { progress: number; x: number; z: number };
export type TrackMapBounds = {
  minX: number; minZ: number; scale: number;
  offsetX: number; offsetY: number; width: number; height: number;
};
export type ProjectedTrackMap = { bounds: TrackMapBounds; points: string };
export function normalizeTrackPart(value: unknown): string;
export function createTrackIdentity(track: unknown, configuration: unknown): string | null;
export function projectTrackMap(points: TrackMapPoint[], width?: number, height?: number, padding?: number): ProjectedTrackMap | null;
export function projectWorldPoint(point: {x:number;z:number}, bounds: TrackMapBounds): {x:number;y:number};
export function isTrackLayout(value: unknown, expectedKey: string): boolean;

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
