// Formatting for values that can legitimately be missing (device unreachable,
// no reading yet) -- these must NEVER silently render as "0", which looks
// like a real (and alarming) reading rather than "no data".
export const formatTemp = (value: number | null | undefined): string =>
  value == null ? "–" : `${value.toFixed(1)}°C`;

export const formatHumidity = (value: number | null | undefined): string =>
  value == null ? "–" : `${value} %`;

/** Valve LEVEL is a 0..1 fraction on the CCU; show it as a percentage. */
export const valvePercent = (value: number | null | undefined): number | null =>
  value == null ? null : Math.round(Math.min(1, Math.max(0, value)) * 100);
