import React, { useRef } from "react";

interface Props {
  value: number;
  min?: number;
  max?: number;
  step?: number;
  size?: number;
  label?: string;
  unit?: string;
  onChange?: (value: number) => void; // continuously while dragging
  onCommit?: (value: number) => void; // once on release
}

// A 270° arc with a gap at the bottom (from START, sweeping clockwise).
const START = 135;
const SWEEP = 270;

function polar(cx: number, cy: number, r: number, deg: number) {
  const rad = (deg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arcPath(cx: number, cy: number, r: number, a0: number, a1: number) {
  const p0 = polar(cx, cy, r, a0);
  const p1 = polar(cx, cy, r, a1);
  const largeArc = a1 - a0 > 180 ? 1 : 0;
  return `M ${p0.x} ${p0.y} A ${r} ${r} 0 ${largeArc} 1 ${p1.x} ${p1.y}`;
}

export default function TemperatureDial({
  value,
  min = 5,
  max = 30,
  step = 0.5,
  size = 240,
  label = "Soll",
  unit = "°C",
  onChange,
  onCommit,
}: Props) {
  const dragging = useRef(false);

  const clamped = Math.min(max, Math.max(min, value));
  const t = (clamped - min) / (max - min);
  const angle = START + t * SWEEP;

  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 20;
  const knob = polar(cx, cy, r, angle);

  function valueFromEvent(e: React.PointerEvent<SVGSVGElement>): number {
    const rect = e.currentTarget.getBoundingClientRect();
    const dx = e.clientX - rect.left - rect.width / 2;
    const dy = e.clientY - rect.top - rect.height / 2;
    let deg = (Math.atan2(dy, dx) * 180) / Math.PI;
    if (deg < 0) deg += 360;
    let rel = deg - START;
    if (rel < 0) rel += 360;
    if (rel > SWEEP) rel = rel - SWEEP < 360 - rel ? SWEEP : 0; // snap out of the gap
    const raw = min + (rel / SWEEP) * (max - min);
    return Math.min(max, Math.max(min, Math.round(raw / step) * step));
  }

  function down(e: React.PointerEvent<SVGSVGElement>) {
    e.currentTarget.setPointerCapture?.(e.pointerId);
    dragging.current = true;
    onChange?.(valueFromEvent(e));
  }
  function move(e: React.PointerEvent<SVGSVGElement>) {
    if (dragging.current) onChange?.(valueFromEvent(e));
  }
  function up(e: React.PointerEvent<SVGSVGElement>) {
    if (!dragging.current) return;
    dragging.current = false;
    onCommit?.(valueFromEvent(e));
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
      onPointerCancel={up}
      style={{ touchAction: "none", cursor: "pointer", userSelect: "none" }}
    >
      <path
        d={arcPath(cx, cy, r, START, START + SWEEP)}
        fill="none"
        stroke="var(--dial-track, #e3e3e8)"
        strokeWidth={12}
        strokeLinecap="round"
      />
      {t > 0 && (
        <path
          d={arcPath(cx, cy, r, START, angle)}
          fill="none"
          stroke="var(--dial-progress, #4f46e5)"
          strokeWidth={12}
          strokeLinecap="round"
        />
      )}
      <circle
        cx={knob.x}
        cy={knob.y}
        r={13}
        fill="#fff"
        stroke="var(--dial-progress, #4f46e5)"
        strokeWidth={3}
      />
      <text
        x={cx}
        y={cy}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize={size * 0.22}
        fontWeight={700}
        fill="var(--color-text, currentColor)"
      >
        {clamped.toFixed(1)}
      </text>
      <text
        x={cx}
        y={cy + size * 0.16}
        textAnchor="middle"
        fontSize={size * 0.075}
        fill="var(--color-text-muted, #999)"
      >
        {label} {unit}
      </text>
    </svg>
  );
}
