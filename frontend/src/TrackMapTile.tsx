import { useEffect, useMemo, useRef, useState } from "react";
import {
  createTrackIdentity,
  isTrackLayout,
  projectTrackMap,
  projectWorldPoint,
  type TrackMapPoint,
} from "./trackMap.js";
import {
  advanceTrackMapCapture,
  createTrackMapCaptureState,
} from "./trackMapCapture.js";

type TrackLayout = {
  version: 2;
  key: string;
  track: string;
  configuration: string;
  points: TrackMapPoint[];
};

type TrackMapTileProps = {
  track: string | null | undefined;
  configuration: string | null | undefined;
  graphics: any;
  lapStatus?: string | null;
};

const CACHE_PREFIX = "acc-track-map-v2:";
const MIN_LAYOUT_POINTS = 80;

function readTrackLayout(key: string | null): TrackLayout | null {
  if (!key) return null;
  try {
    const raw = window.localStorage.getItem(CACHE_PREFIX + key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return isTrackLayout(parsed, key) ? parsed as TrackLayout : null;
  } catch {
    return null;
  }
}

function worldPoint(value: unknown): { x: number; z: number } | null {
  if (!Array.isArray(value) || value.length < 3) return null;
  const x = value[0];
  const z = value[2];
  return typeof x === "number" && Number.isFinite(x) &&
    typeof z === "number" && Number.isFinite(z)
    ? { x, z }
    : null;
}

export default function TrackMapTile({
  track,
  configuration,
  graphics,
  lapStatus,
}: TrackMapTileProps) {
  const trackName = typeof track === "string" ? track.trim() : "";
  const configurationName = typeof configuration === "string" ? configuration.trim() : "";
  const identity = createTrackIdentity(trackName, configurationName);
  const progress = graphics?.normalized_car_position;
  const world = graphics?.player_world_position;
  const completedLaps = graphics?.completed_laps;
  const isValidLap = graphics?.is_valid_lap;
  const lastTimeMs = graphics?.last_time_ms;
  const sessionKey = [
    identity ?? "",
    graphics?.session_index ?? "",
    graphics?.session ?? "",
  ].join("|");

  const [layout, setLayout] = useState<TrackLayout | null>(() => readTrackLayout(identity));
  const capture = useRef(createTrackMapCaptureState(identity, sessionKey));

  useEffect(() => {
    setLayout(readTrackLayout(identity));
    capture.current = createTrackMapCaptureState(identity, sessionKey);
  }, [identity, sessionKey]);

  useEffect(() => {
    if (!identity || capture.current.key !== identity || capture.current.sessionKey !== sessionKey) return;
    if (typeof progress !== "number" || !Number.isFinite(progress) || progress < 0 || progress > 1) return;
    const position = worldPoint(world);
    if (!position) return;

    const result = advanceTrackMapCapture(capture.current, {
      progress,
      point: position,
      completedLaps: typeof completedLaps === "number" ? completedLaps : null,
      isValidLap: typeof isValidLap === "boolean" ? isValidLap : null,
      lastTimeMs: typeof lastTimeMs === "number" ? lastTimeMs : null,
      lapStatus: typeof lapStatus === "string" ? lapStatus : null,
    }, { minPoints: MIN_LAYOUT_POINTS });

    capture.current = result.state;

    if (result.committedPoints) {
      const candidate: TrackLayout = {
        version: 2,
        key: identity,
        track: trackName,
        configuration: configurationName,
        points: result.committedPoints,
      };
      if (isTrackLayout(candidate, identity)) {
        try {
          window.localStorage.setItem(CACHE_PREFIX + identity, JSON.stringify(candidate));
        } catch {
          // Keep the confirmed valid layout in memory if browser storage is unavailable.
        }
        setLayout(candidate);
      }
    }
  }, [
    identity,
    sessionKey,
    progress,
    world,
    completedLaps,
    isValidLap,
    lastTimeMs,
    lapStatus,
    trackName,
    configurationName,
  ]);

  const projected = useMemo(
    () => layout?.key === identity ? projectTrackMap(layout.points) : null,
    [layout, identity],
  );
  const currentPosition = worldPoint(world);
  const marker = projected && currentPosition
    ? projectWorldPoint(currentPosition, projected.bounds)
    : null;
  const learned = Boolean(projected);

  return (
    <div className="track-map-tile">
      <div className="track-map-identity">
        <div className="track-map-name">
          <strong>{trackName || "Track unavailable"}</strong>
          {identity && <span>{configurationName || "Default layout"}</span>}
        </div>
        {identity && <span className={learned ? "track-map-state is-learned" : "track-map-state is-learning"}>
          {learned ? "LEARNED" : "LEARNING"}
        </span>}
      </div>
      {projected ? (
        <svg className="track-map-svg" viewBox="0 0 360 180" role="img" aria-label={`ACC learned circuit for ${trackName}`}>
          <polyline className="track-map-outline" points={`${projected.points} ${projected.points.split(" ")[0]}`}/>
          {marker && <g className="track-map-car" aria-label="Live car position">
            <circle cx={marker.x} cy={marker.y} r="6.5"/>
            <circle cx={marker.x} cy={marker.y} r="2.3"/>
          </g>}
        </svg>
      ) : (
        <div className="track-map-empty" role="status">
          <span className="track-map-empty-mark">⌁</span>
          <strong>{identity ? "Complete a valid lap to learn this circuit" : "Waiting for ACC track identity"}</strong>
        </div>
      )}
    </div>
  );
}
