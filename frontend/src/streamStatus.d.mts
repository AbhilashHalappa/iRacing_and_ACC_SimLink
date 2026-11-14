export type StreamState = "fresh" | "stale" | "missing" | "unavailable" | "waiting";

export function getStreamDisplayState(
  accConnected: boolean,
  streamState: StreamState | null | undefined,
): StreamState;
