import React, { useMemo } from "react";
import { Line } from "react-chartjs-2";
import { useNavigate } from "react-router-dom";
import {
  Chart as ChartJS,
  LineElement,
  CategoryScale,
  LinearScale,
  PointElement,
  Tooltip,
  Filler
} from "chart.js";
import { useTheme } from "../theme/ThemeContext";
import type { TimeBlock } from "../services/types";

ChartJS.register(LineElement, CategoryScale, LinearScale, PointElement, Tooltip, Filler);

// Deutsche Wochentags-Abkürzungen
const DAY_MAP: Record<string, string> = {
  monday: "MO",
  tuesday: "DI",
  wednesday: "MI",
  thursday: "DO",
  friday: "FR",
  saturday: "SA",
  sunday: "SO"
};

const STEP_MIN = 5;
const TIMES = Array.from({ length: (24 * 60) / STEP_MIN + 1 }, (_, i) => {
  const m = i * STEP_MIN;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
});
const toMinutes = (hhmm: string) => {
  const [h, m] = hhmm.split(":");
  return Number(h) * 60 + Number(m);
};
// Beschriftung nur alle 2 h und nur als Stunde ("00".."24", sonst überlappt
// sie auf dem Handy); Gitterlinien je volle Stunde
const LABEL_EVERY = (2 * 60) / STEP_MIN;
const GRID_EVERY = 60 / STEP_MIN;

interface ProfileDayChartProps {
  day: string;
  blocks: TimeBlock[];
  roomName: string;
  profileName: string;     // Klartext-Name
  profileNumber?: number;  // P1–P6 (NEU)
  mode?: string;           // "heating" | "cooling" (Phase 2b.2) -> ?mode= weiterreichen
}

const ProfileDayChart: React.FC<ProfileDayChartProps> = ({
  day,
  blocks,
  roomName,
  profileName,
  profileNumber,
  mode
}) => {

  const navigate = useNavigate();

  const { theme } = useTheme();

  // Temperaturkurve im 5-Minuten-Raster (kleinste einstellbare Einheit), damit
  // auch Abschnitte zwischen vollen Stunden sichtbar werden. Ein Punkt gehört
  // zum Abschnitt, der ihn als Ende einschließt; zusammen mit `stepped: true`
  // ("before") füllt jeder Abschnitt genau von seinem Start bis zu seinem Ende.
  const tempCurve = TIMES.map((time, i) => {
    const t = i * STEP_MIN;
    const block =
      t === 0
        ? blocks[0]
        : blocks.find((b) => t > toMinutes(b.start) && t <= toMinutes(b.end));
    return block ? block.setpoint : null;
  });

  // Letzten Punkt erzwingen
  if (tempCurve[tempCurve.length - 1] === null) {
    tempCurve[tempCurve.length - 1] = tempCurve[tempCurve.length - 2];
  }

  const chartColors = useMemo(() => {
    if (typeof window === "undefined") {
      return {
        line: "#1e40af",
        fill: "rgba(30, 64, 175, 0.2)",
        text: "#333",
        grid: "rgba(0, 0, 0, 0.12)"
      };
    }

    const styles = getComputedStyle(document.documentElement);
    return {
      line: styles.getPropertyValue("--chart-line").trim() || "#1e40af",
      fill:
        styles.getPropertyValue("--chart-fill").trim() || "rgba(30, 64, 175, 0.2)",
      text: styles.getPropertyValue("--chart-text").trim() || "#333",
      grid:
        styles.getPropertyValue("--chart-grid").trim() || "rgba(0, 0, 0, 0.12)"
    };
    // theme ist Auslöser: die CSS-Variablen ändern sich mit dem Theme
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);

  const data = {
    labels: TIMES,
    datasets: [
      {
        label: DAY_MAP[day] ?? day.toUpperCase().slice(0, 2),
        data: tempCurve,
        fill: true,
        borderColor: chartColors.line,
        backgroundColor: chartColors.fill,
        tension: 0,
        stepped: true,
        pointRadius: 0
      }
    ]
  };

  const options = {
    responsive: true,
    scales: {
      x: {
        ticks: {
          autoSkip: false,
          maxRotation: 0,
          callback: (_value: string | number, index: number) =>
            index % LABEL_EVERY === 0 ? TIMES[index].slice(0, 2) : "",
          color: chartColors.text
        },
        grid: {
          color: (ctx: { index: number }) =>
            ctx.index % GRID_EVERY === 0 ? chartColors.grid : "transparent"
        }
      },
      y: {
        min: 15,
        max: 30,
        ticks: {
          stepSize: 5,
          callback: (value: number) => {
            if (value === 15 || value === 25) return value + "°C";
            return "";
          },
          color: chartColors.text
        },
        grid: {
          color: chartColors.grid
        }
      }
    }
  };

  // Korrekte Navigation: P1–P6 statt Klartext
  const profileRoute = profileNumber
    ? `P${profileNumber}`
    : profileName; // Fallback

  return (
    <div
      className="profile-day-chart-card"
      onClick={() =>
        navigate(
          `/settings/heating-profiles/${roomName}/${profileRoute}/${day}` +
            (mode ? `?mode=${mode}` : "")
        )
      }
    >
      <h3 className="profile-day-chart-title">{DAY_MAP[day]}</h3>
      <Line data={data} options={options} />
    </div>
  );
};

export default ProfileDayChart;
