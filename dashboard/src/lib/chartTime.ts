// Time axis shared by the history charts (Ventilverlauf, Raumverlauf).
const WEEKDAY = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];

export const CHART_RANGES = [12, 24, 48, 72];

export function timeLabel(epoch: number): string {
  const d = new Date(epoch * 1000);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${WEEKDAY[d.getDay()]} ${hh}:${mm}`;
}

/** Index of the first sample at or after every full 6 hours (axis labels). */
export function tickIndices(times: number[], everyHours: number): Set<number> {
  const out = new Set<number>();
  let lastBucket = -1;
  times.forEach((t, i) => {
    const d = new Date(t * 1000);
    const bucket = Math.floor((d.getDate() * 24 + d.getHours()) / everyHours);
    if (bucket !== lastBucket && d.getHours() % everyHours === 0) out.add(i);
    lastBucket = bucket;
  });
  return out;
}
