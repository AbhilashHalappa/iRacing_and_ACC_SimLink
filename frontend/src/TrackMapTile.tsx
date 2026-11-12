import { useEffect, useMemo, useRef, useState } from "react";
import {
  createTrackIdentity,
  isTrackLayout,
  projectTrackMap,
  projectWorldPoint,
  type TrackMapPoint,
} from "./trackMap.js";

type TrackLayout = {
  version: 1;
  key: string;
  track: string;
  configuration: string;
  points: TrackMapPoint[];
};

type CaptureState = {
  key: string | null;
  previousProgress: number | null;
  capturing: boolean;
  points: TrackMapPoint[];
};

type TrackMapTileProps = {
  track: string | null | undefined;
  configuration: string | null | undefined;
  graphics: any;
};

const CACHE_PREFIX = "acc-track-map-v1:";
const MIN_LAYOUT_POINTS = 80;
const MIN_SAMPLE_PROGRESS_STEP = 0.001;

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

export default function TrackMapTile({ track, configuration, graphics }: TrackMapTileProps) {
  const trackName = typeof track === "string" ? track.trim() : "";
  const configurationName = typeof configuration === "string" ? configuration.trim() : "";
  const identity = createTrackIdentity(trackName, configurationName);
  const progress = graphics?.normalized_car_position;
  const world = graphics?.player_world_position;
  const [layout, setLayout] = useState<TrackLayout | null>(() => readTrackLayout(identity));
  const [captureProgress, setCaptureProgress] = useState<number | null>(null);
  const capture = useRef<CaptureState>({
    key: identity,
    previousProgress: null,
    capturing: false,
    points: [],
  });

  useEffect(() => {
    setLayout(readTrackLayout(identity));
    setCaptureProgress(null);
    capture.current = {
      key: identity,
      previousProgress: null,
      capturing: false,
      points: [],
    };
  }, [identity]);

  useEffect(() => {
    if (!identity || layout?.key === identity || capture.current.key !== identity) return;
    if (typeof progress !== "number" || !Number.isFinite(progress) || progress < 0 || progress > 1) return;
    const position = worldPoint(world);
    if (!position) return;

    const point: TrackMapPoint = { progress, x: position.x, z: position.z };
    const state = capture.current;
    const previousProgress = state.previousProgress;
    const crossedStartFinish = previousProgress !== null &&
      previousProgress > 0.9 && progress < 0.1;

    if (crossedStartFinish) {
      if (state.capturing && state.points.length >= MIN_LAYOUT_POINTS) {
        const candidate: TrackLayout = {
          version: 1,
          key: identity,
          track: trackName,
          configuration: configurationName,
          points: state.points,
        };
        if (candidate.points[0].progress <= 0.05 &&
            candidate.points[candidate.points.length - 1].progress >= 0.95 &&
            isTrackLayout(candidate, identity)) {
          try {
            window.localStorage.setItem(CACHE_PREFIX + identity, JSON.stringify(candidate));
          } catch {
            // Keep the learned layout for this app session if storage is unavailable.
          }
          setLayout(candidate);
        }
      }

      capture.current = {
        key: identity,
        previousProgress: progress,
        capturing: true,
        points: [point],
      };
      setCaptureProgress(0);
      return;
    }

    if (!state.capturing) {
      state.previousProgress = progress;
      return;
    }

    const last = state.points[state.points.length - 1];
    if (last && progress < last.progress - 0.02) {
      // A teleport, session reset or discontinuity invalidates this candidate lap.
      state.capturing = false;
      state.points = [];
      state.previousProgress = progress;
      setCaptureProgress(null);
      return;
    }

    if (!last || progress - last.progress >= MIN_SAMPLE_PROGRESS_STEP) {
      state.points.push(point);
    }
    state.previousProgress = progress;
    setCaptureProgress(progress);
  }, [identity, layout, progress, world, trackName, configurationName]);

  const projected = useMemo(
    () => layout?.key === identity ? projectTrackMap(layout.points) : null,
    [layout, identity],
  );
  const currentPosition = worldPoint(world);
  const marker = projected && currentPosition
    ? projectWorldPoint(currentPosition, projected.bounds)
    : null;
  const progressLabel = typeof progress === "number" && Number.isFinite(progress)
    ? `${(progress * 100).toFixed(1)}%`
    : "—";

  let status = "Waiting for ACC track identity";
  if (identity && !projected) {
    if (captureProgress !== null) {
      status = `Capturing circuit · ${Math.round(captureProgress * 100)}%`;
    } else {
      status = "Waiting for start/finish crossing · then drive one complete lap";
    }
  } else if (projected) {
    status = marker ? "LIVE CAR POSITION" : "Waiting for live car coordinates";
  }

  return (
    <div className="track-map-tile">
      {identity && <div className="track-map-identity">
        <strong>{trackName}</strong>
        <span>{configurationName || "Default layout"}</span>
      </div>}
      {projected ? (
        <svg className="track-map-svg" viewBox="0 0 360 180" role="img" aria-label={`ACC circuit map for ${trackName}`}>
          <polyline className="track-map-outline" points={projected.points}/>
          {marker && <g className="track-map-car">
            <circle cx={marker.x} cy={marker.y} r="8"/>
            <circle cx={marker.x} cy={marker.y} r="3"/>
          </g>}
        </svg>
      ) : (
        <div className="track-map-empty" role="status">
          <span className="track-map-empty-mark">⌁</span>
          <strong>{identity ? "Circuit layout not cached yet" : "Track unavailable"}</strong>
          <small>{identity
            ? "The map is learned from ACC world coordinates during a complete lap. It is then cached for this exact track configuration."
            : "ACC has not supplied a usable track identity."}</small>
        </div>
      )}
      <div className="track-map-footer">
        <span className={projected && marker ? "track-map-live-dot is-live" : "track-map-live-dot"}/>
        <b>{status}</b>
        <span className="track-map-progress">{progressLabel}</span>
      </div>
    </div>
  );
}
