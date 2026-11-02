import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
  type ScriptableContext,
} from "chart.js";
import { AppIcon } from "../icons/IconMap";
import { apiErrorMessage } from "../services/api";
import { useRoomHistory } from "../hooks/useRoomHistory";
import { useRooms } from "../hooks/useRooms";
import { CHART_RANGES, tickIndices, timeLabel } from "../lib/chartTime";
import { useTheme } from "../theme/ThemeContext";
import "../styles/styles.css";

ChartJS.register(LineElement, CategoryScale, LinearScale, PointElement, Tooltip, Legend, Filler);

const VALVE_LABEL = "Ventil";

/** A value without a neighbour draws no line: show it as a dot (first sample, after a pause). */
function isolatedPointRadius(ctx: ScriptableContext<"line">): number {
  const values = ctx.dataset.data;
  return values[ctx.dataIndex - 1] == null && values[ctx.dataIndex + 1] == null ? 3 : 0;
}

export default function RoomHistory() {
  const navigate = useNavigate();
  const [hours, setHours] = useState(48);
  const [picked, setPicked] = useState<string | null>(null);
  const { data: rooms = [] } = useRooms();
  const room = picked ?? rooms[0]?.room ?? null;
  const { data, error, isLoading } = useRoomHistory(room, hours);
  const { theme } = useTheme();

  const colors = useMemo(() => {
    const styles = getComputedStyle(document.documentElement);
    const read = (name: string, fallback: string) =>
      styles.getPropertyValue(name).trim() || fallback;
    return {
      text: read("--chart-text", "#333"),
      grid: read("--chart-grid", "rgba(0, 0, 0, 0.12)"),
      plan: read("--chart-plan", "#2563eb"),
      temperature: read("--chart-temperature", "#ea580c"),
      valve: read("--chart-valve", "#0d9488"),
    };
    // theme ist Auslöser: die CSS-Variablen ändern sich mit dem Theme
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);

  const labels = data ? data.times.map(timeLabel) : [];
  // fewer, shorter axis labels on a phone so they do not overlap
  const narrow = typeof window !== "undefined" && window.innerWidth < 600;
  const every = narrow ? (hours > 24 ? 12 : 6) : (hours > 24 ? 6 : 3);
  const ticks = data ? tickIndices(data.times, every) : new Set<number>();

  const chartData = {
    labels,
    datasets: [
      {
        label: "Plan",
        data: data?.plan ?? [],
        yAxisID: "temperature",
        borderColor: colors.plan,
        backgroundColor: colors.plan,
        borderWidth: 2,
        pointRadius: isolatedPointRadius,
        stepped: true as const,
        spanGaps: false,
      },
      {
        label: "Temperatur",
        data: data?.temperature ?? [],
        yAxisID: "temperature",
        borderColor: colors.temperature,
        backgroundColor: colors.temperature,
        borderWidth: 2,
        pointRadius: isolatedPointRadius,
        tension: 0.2,
        spanGaps: false,
      },
      {
        label: VALVE_LABEL,
        data: data?.valve ?? [],
        yAxisID: "valve",
        borderColor: colors.valve,
        backgroundColor: `color-mix(in srgb, ${colors.valve} 22%, transparent)`,
        borderWidth: 1,
        pointRadius: isolatedPointRadius,
        stepped: true as const,
        fill: "origin" as const,
        spanGaps: false,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false as const,
    interaction: { mode: "index" as const, intersect: false },
    plugins: {
      legend: {
        position: "bottom" as const,
        labels: { color: colors.text, boxWidth: 14, usePointStyle: true },
      },
      tooltip: {
        callbacks: {
          label: (ctx: { dataset: { label?: string }; parsed: { y: number | null } }) => {
            const y = ctx.parsed.y;
            if (y == null) return `${ctx.dataset.label}: –`;
            return ctx.dataset.label === VALVE_LABEL
              ? `${ctx.dataset.label}: ${y} %`
              : `${ctx.dataset.label}: ${y.toFixed(1)} °C`;
          },
        },
      },
    },
    scales: {
      x: {
        ticks: {
          autoSkip: false,
          maxRotation: 0,
          color: colors.text,
          callback: (_v: string | number, index: number) =>
            ticks.has(index) ? (narrow ? labels[index].slice(0, 5) : labels[index]) : "",
        },
        grid: {
          color: (ctx: { index: number }) => (ticks.has(ctx.index) ? colors.grid : "transparent"),
        },
      },
      temperature: {
        position: "left" as const,
        grace: "5%",
        ticks: {
          color: colors.text,
          callback: (v: string | number) => `${Number(Number(v).toFixed(1))} °C`,
        },
        grid: { color: colors.grid },
      },
      valve: {
        position: "right" as const,
        min: 0,
        max: 100,
        ticks: { stepSize: 25, color: colors.text, callback: (v: string | number) => `${v} %` },
        grid: { drawOnChartArea: false },
      },
    },
  };

  return (
    <div className="room-grid">
      <div className="back-card" onClick={() => navigate("/settings")} style={{ cursor: "pointer" }}>
        <span className="back-left"><AppIcon name="arrowleft" /></span>
        <span className="back-center">Raumverlauf</span>
        <span className="back-right"><AppIcon name="thermometer" /></span>
      </div>

      <div className="room-card card-wide" style={{ gap: "0.6rem" }}>
        <div className="valve-range">
          {CHART_RANGES.map((h) => (
            <button
              key={h}
              className={`profile-mini-card-vertical ${h === hours ? "active-profile" : ""}`}
              onClick={() => setHours(h)}
            >
              {h} h
            </button>
          ))}
        </div>

        {error && <div className="validation-error">{apiErrorMessage(error)}</div>}
        {isLoading && <div className="room-subtitle">Lade…</div>}
        {data && data.times.length === 0 && (
          <div className="room-subtitle">
            Für {room} gibt es noch keine Aufzeichnung. Die App speichert alle 5 Minuten Plan,
            Temperatur und Ventilstellung; die ersten Werte erscheinen kurz nach dem Start.
          </div>
        )}
        {data && data.times.length > 0 && (
          <div className="valve-chart">
            <Line data={chartData} options={options} />
          </div>
        )}

        <div className="valve-range">
          {rooms.map((r) => (
            <button
              key={r.room}
              className={`profile-mini-card-vertical ${r.room === room ? "active-profile" : ""}`}
              aria-pressed={r.room === room}
              onClick={() => setPicked(r.room)}
            >
              {r.room}
            </button>
          ))}
        </div>

        <div className="room-subtitle">
          Plan und Temperatur gehören zur linken Achse, die Ventilöffnung zur rechten. Alle 5
          Minuten aufgezeichnet, bis zu 3 Tage. Der Plan zeigt, was das zu diesem Zeitpunkt aktive
          Profil vorsah; von Hand gesetzte Werte erscheinen nicht. Lücken bedeuten, dass die App in
          dieser Zeit nicht lief.
        </div>
      </div>
    </div>
  );
}
