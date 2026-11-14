export function getStreamDisplayState(accConnected, streamState) {
  if (!accConnected) return "waiting";
  return streamState ?? "missing";
}
