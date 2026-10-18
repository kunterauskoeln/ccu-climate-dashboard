import React, { useState } from "react";
import { apiErrorMessage } from "../services/api";
import type { ClimateSchedule, ClimateSchedulePoint } from "../services/types";
import { useClimateSchedule, useSetClimateSchedule } from "../hooks/useClimate";

const MONTHS = [
  "Januar", "Februar", "März", "April", "Mai", "Juni",
  "Juli", "August", "September", "Oktober", "November", "Dezember",
];
const DAYS_IN_MONTH = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
const HOURS = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, "0"));
const MINUTES = Array.from({ length: 12 }, (_, i) => String(i * 5).padStart(2, "0"));

const DEFAULT_HEATING: ClimateSchedulePoint = { day: 15, month: 9, time: "08:00", enabled: false };
const DEFAULT_COOLING: ClimateSchedulePoint = { day: 15, month: 5, time: "08:00", enabled: false };

function formatAt(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
}

/** One-line summary for the closed Betriebsart tile. */
export function scheduleSummary(schedule: ClimateSchedule | undefined): string {
  if (!schedule?.next) return "Automatisch umschalten: aus";
  return `Automatisch auf ${schedule.next.cooling ? "Kühlen" : "Heizen"} am ${formatAt(schedule.next.at)}`;
}

function PointRow({
  label,
  point,
  onChange,
}: {
  label: string;
  point: ClimateSchedulePoint;
  onChange: (point: ClimateSchedulePoint) => void;
}) {
  const [hour, minute] = point.time.split(":");
  const disabled = !point.enabled;
  const maxDay = DAYS_IN_MONTH[point.month - 1];
  const setMonth = (month: number) =>
    onChange({ ...point, month, day: Math.min(point.day, DAYS_IN_MONTH[month - 1]) });

  return (
    <div className="schedule-row">
      <label className="setting-toggle schedule-label">
        <input
          type="checkbox"
          checked={point.enabled}
          onChange={(e) => onChange({ ...point, enabled: e.target.checked })}
        />
        {label}
      </label>
      <div className="schedule-fields">
        <select
          aria-label={`${label}: Tag`}
          value={point.day}
          disabled={disabled}
          onChange={(e) => onChange({ ...point, day: Number(e.target.value) })}
        >
          {Array.from({ length: maxDay }, (_, i) => i + 1).map((d) => (
            <option key={d} value={d}>{d}.</option>
          ))}
        </select>
        <select
          aria-label={`${label}: Monat`}
          value={point.month}
          disabled={disabled}
          onChange={(e) => setMonth(Number(e.target.value))}
        >
          {MONTHS.map((name, i) => (
            <option key={name} value={i + 1}>{name}</option>
          ))}
        </select>
        <span className="schedule-at">um</span>
        <select
          aria-label={`${label}: Stunde`}
          value={hour}
          disabled={disabled}
          onChange={(e) => onChange({ ...point, time: `${e.target.value}:${minute}` })}
        >
          {HOURS.map((h) => <option key={h} value={h}>{h}</option>)}
        </select>
        <select
          aria-label={`${label}: Minute`}
          value={MINUTES.includes(minute) ? minute : "00"}
          disabled={disabled}
          onChange={(e) => onChange({ ...point, time: `${hour}:${e.target.value}` })}
        >
          {MINUTES.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <span className="schedule-at">Uhr</span>
      </div>
    </div>
  );
}

function Editor({ schedule }: { schedule: ClimateSchedule }) {
  const save = useSetClimateSchedule();
  const [heating, setHeating] = useState(schedule.heating ?? DEFAULT_HEATING);
  const [cooling, setCooling] = useState(schedule.cooling ?? DEFAULT_COOLING);

  const same = (a: ClimateSchedulePoint | null, b: ClimateSchedulePoint) =>
    !!a && a.day === b.day && a.month === b.month && a.time === b.time && a.enabled === b.enabled;
  const dirty = !same(schedule.heating, heating) || !same(schedule.cooling, cooling);

  return (
    <div className="schedule-box">
      <div className="setting-name">Automatisch umschalten</div>

      <PointRow label="Auf Kühlen" point={cooling} onChange={setCooling} />
      <PointRow label="Auf Heizen" point={heating} onChange={setHeating} />

      <div className="room-subtitle">
        Angehakte Zeitpunkte gelten jedes Jahr, bis du sie änderst oder den Haken entfernst.
        War der Server zum Zeitpunkt aus, wird die Umschaltung beim nächsten Start nachgeholt.
      </div>

      <button
        className="profile-mini-card-vertical active-profile"
        style={{ textAlign: "center" }}
        onClick={() => save.mutate({ heating, cooling })}
        disabled={!dirty || save.isPending}
      >
        {save.isPending ? "Wird gespeichert…" : "Zeitplan speichern"}
      </button>
      {save.isError && <div className="validation-error">{apiErrorMessage(save.error)}</div>}

      {schedule.next && !dirty && (
        <div className="room-subtitle">
          Nächste Umschaltung: auf {schedule.next.cooling ? "Kühlen" : "Heizen"} am{" "}
          {formatAt(schedule.next.at)}
        </div>
      )}
      {schedule.last_run && (
        <div
          className={schedule.last_run.result === "error" ? "validation-error" : "room-subtitle"}
          style={{ textAlign: "left", marginTop: 0 }}
        >
          Zuletzt automatisch ({formatAt(schedule.last_run.at)}): {schedule.last_run.message}
        </div>
      )}
    </div>
  );
}

/** Form for the scheduled switch, shown inside the opened Betriebsart tile. */
export default function ClimateScheduleForm() {
  const { data, error } = useClimateSchedule();
  if (error) return <div className="validation-error">{apiErrorMessage(error)}</div>;
  if (!data) return <div className="room-subtitle">…</div>;
  // re-mount on new server state, so the form starts from what is stored
  return <Editor key={JSON.stringify(data)} schedule={data} />;
}
