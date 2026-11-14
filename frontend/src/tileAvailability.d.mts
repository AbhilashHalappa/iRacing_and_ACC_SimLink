export function getBlockedTileStreams<K extends string>(
  accConnected: boolean,
  dependencies: readonly K[],
  freshness: Partial<Record<K, { state?: string } | undefined>>,
): K[];
