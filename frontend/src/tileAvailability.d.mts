export function getBlockedTileStreams(
  accConnected: boolean,
  dependencies: readonly string[],
  freshness: Record<string, { state?: string } | undefined>,
): string[];
