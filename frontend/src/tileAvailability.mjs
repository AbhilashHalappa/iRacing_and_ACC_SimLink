export function getBlockedTileStreams(accConnected, dependencies, freshness) {
  if (!accConnected) return [...dependencies];
  return dependencies.filter((stream) => freshness?.[stream]?.state !== "fresh");
}
