import React from "react";
import { valvePercent } from "../lib/format";

// Closed = muted blue-grey, open = warm orange, so a glance at the room list
// shows which rooms are actually heating.
function valveColor(percent: number): string {
  const hue = 215 - (215 - 24) * (percent / 100);
  const saturation = 18 + 72 * (percent / 100);
  const lightness = 56 - 4 * (percent / 100);
  return `hsl(${hue.toFixed(0)}, ${saturation.toFixed(0)}%, ${lightness.toFixed(0)}%)`;
}

/** Valve opening as a small bar plus percentage. `value` is the CCU's 0..1 LEVEL. */
export default function ValveBar({ value }: { value: number | null | undefined }) {
  const percent = valvePercent(value);
  return (
    <div className="valve-bar" title="Ventilöffnung">
      <span className="valve-label">Ventil</span>
      <div className="valve-track">
        {percent !== null && (
          <div
            className="valve-fill"
            style={{ width: `${percent}%`, background: valveColor(percent) }}
          />
        )}
      </div>
      <span className="valve-percent">{percent === null ? "–" : `${percent} %`}</span>
    </div>
  );
}
