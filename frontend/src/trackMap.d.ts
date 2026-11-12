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
