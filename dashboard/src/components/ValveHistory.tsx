import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import { AppIcon } from "../icons/IconMap";
import { apiErrorMessage } from "../services/api";
import { useValveHistory } from "../hooks/useValveHistory";
import { useTheme } from "../theme/ThemeContext";
import "../styles/styles.css";

ChartJS.register(LineElement, CategoryScale, LinearScale, PointElement, Tooltip, Legend);

// Gut unterscheidbare Farben, fest je Raum (alphabetische Reihenfolge)
const PALETTE = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#00a6a6", "#c9a400",
  "#f032e6", "#7f7f7f", "#9a6324"];
const WEEKDAY = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
const RANGES = [12, 24, 48, 72];

function label(epoch: number): string {
  const d = new Date(epoch * 1000);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${WEEKDAY[d.getDay()]} ${hh}:${mm}`;
}

/** Index of the first sample at or after every full 6 hours (axis labels). */
function tickIndices(times: number[], everyHours: number): Set<number> {
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

export default function ValveHistory() {
  const navigate = useNavigate();
  const [hours, setHours] = useState(48);
  const { data, error, isLoading } = useValveHistory(hours);
  const { theme } = useTheme();

  const colors = useMemo(() => {
    const styles = getComputedStyle(document.documentElement);
    return {
      text: styles.getPropertyValue("--chart-text").trim() || "#333",
      grid: styles.getPropertyValue("--chart-grid").trim() || "rgba(0, 0, 0, 0.12)",
    };
    // theme ist Auslöser: die CSS-Variablen ändern sich mit dem Theme
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);

  const rooms = data ? Object.keys(data.rooms).sort() : [];
  const labels = data ? data.times.map(label) : [];
  // fewer, shorter axis labels on a phone so they do not overlap
  const narrow = typeof window !== "undefined" && window.innerWidth < 600;
  const every = narrow ? (hours > 24 ? 12 : 6) : (hours > 24 ? 6 : 3);
  const ticks = data ? tickIndices(data.times, every) : new Set<number>();

  const chartData = {
    labels,
    datasets: rooms.map((room, i) => ({
      label: room,
      data: data!.rooms[room],
      borderColor: PALETTE[i % PALETTE.length],
      backgroundColor: PALETTE[i % PALETTE.length],
      borderWidth: 2,
      pointRadius: 0,
      tension: 0,
      stepped: true as const,
      spanGaps: false,
    })),
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
          label: (ctx: { dataset: { label?: string }; parsed: { y: number | null } }) =>
            `${ctx.dataset.label}: ${ctx.parsed.y ?? "–"} %`,
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
      y: {
        min: 0,
        max: 100,
        ticks: { stepSize: 25, color: colors.text, callback: (v: string | number) => `${v} %` },
        grid: { color: colors.grid },
      },
    },
  };

  return (
    <div className="room-grid">
      <div className="back-card" onClick={() => navigate("/settings")} style={{ cursor: "pointer" }}>
        <span className="back-left"><AppIcon name="arrowleft" /></span>
        <span className="back-center">Ventilverlauf</span>
        <span className="back-right"><AppIcon name="verlauf" /></span>
      </div>

      <div className="room-card card-wide" style={{ gap: "0.6rem" }}>
        <div className="valve-range">
          {RANGES.map((h) => (
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
            Noch keine Aufzeichnung. Die App speichert alle 5 Minuten die Ventilstellung jedes
            Raums; die ersten Werte erscheinen kurz nach dem Start.
          </div>
        )}
        {data && data.times.length > 0 && (
          <div className="valve-chart">
            <Line data={chartData} options={options} />
          </div>
        )}
        <div className="room-subtitle">
          Ventilöffnung je Raum (Mittel über seine Heizkreise), alle 5 Minuten aufgezeichnet,
          bis zu 3 Tage. Ein Tipp auf einen Raum in der Legende blendet ihn aus oder ein;
          Fahren über die Grafik zeigt die Werte zu diesem Zeitpunkt. Lücken bedeuten, dass die
          App in dieser Zeit nicht lief.
        </div>
      </div>
    </div>
  );
}
