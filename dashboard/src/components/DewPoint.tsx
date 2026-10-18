import React from "react";
import { useNavigate } from "react-router-dom";
import { AppIcon, getIcon } from "../icons/IconMap";
import { apiErrorMessage } from "../services/api";
import type { DewFlow } from "../services/types";
import { useDewPoint } from "../hooks/useDewPoint";
import { DEW_STATUS_LABEL, formatAge, formatCelsius, formatKelvin } from "../lib/dewPoint";
import "../styles/styles.css";

function flowSource(flow: DewFlow, cooling: boolean | null): string {
  if (!cooling) return "Vergleich nur im Kühlbetrieb (beim Heizen fließt warmes Wasser)";
  if (flow.source === "live") return "aktueller Messwert (Wasser fließt)";
  if (flow.source === "last_valid") {
    return `letzter gültiger Wert, gemessen ${formatAge(flow.last_valid_at)} (Ventile erst kurz offen oder zu)`;
  }
  return "noch kein gültiger Wert: der Sensor gilt erst nach 10 Minuten Durchfluss";
}

export default function DewPoint() {
  const navigate = useNavigate();
  const { data, error, isLoading } = useDewPoint();

  return (
    <div className="room-grid equal-height">
      <div className="back-card" onClick={() => navigate("/settings")} style={{ cursor: "pointer" }}>
        <span className="back-left"><AppIcon name="arrowleft" /></span>
        <span className="back-center">Taupunkt</span>
        <span className="back-right"><AppIcon name="taupunkt" /></span>
      </div>

      {error && <div className="room-card card-wide validation-error">{apiErrorMessage(error)}</div>}
      {isLoading && <div className="room-card card-wide room-subtitle">Lade…</div>}

      {data && (
        <>
          <div className={`room-card card-wide dew-summary dew-border-${data.level}`}>
            <div className="setting-name">{data.message}</div>
            <div className="room-subtitle">
              {data.cooling === null
                ? "Betriebsart noch unbekannt."
                : data.cooling
                ? `Kühlbetrieb. Ampel: ab ${formatKelvin(data.warn_margin)} Abstand ok, darunter knapp, unter ${formatKelvin(data.alarm_margin)} Kondensgefahr.`
                : "Taupunkte nur zur Information."}
            </div>
            <div className="dew-flow">
              <div>
                <span className="dew-key">{data.cooling ? "Vorlauf (Vergleichswert)" : "Vorlauf (Sensor)"}</span>
                <span className="dew-value">
                  {formatCelsius(data.cooling ? data.flow.effective : data.flow.value)}
                </span>
              </div>
              <div className="room-subtitle">{flowSource(data.flow, data.cooling)}</div>
              <div className="room-subtitle">
                Sensor: {data.flow.configured ? data.flow.connection : "nicht eingerichtet (MQTT in backend/.env)"}
                {data.flow.configured && (
                  <> · zuletzt {formatCelsius(data.flow.value)} {formatAge(data.flow.received_at)}
                    {data.flow.stale && data.flow.received_at != null && " (veraltet)"}</>
                )}
              </div>
            </div>
            <div className="room-subtitle">
              Überwachung, kein Schutzgerät: Die App warnt, sie schaltet nichts ab.
              Stand {formatAge(data.at)}.
            </div>
          </div>

          {data.rooms.map((r) => (
            <div key={r.room} className={`room-card dew-border-${r.status}`} style={{ gap: "0.4rem" }}>
              <div className="room-header-left">
                <span className="room-icon">{getIcon(r.room)}</span>
                <span className="room-name">{r.room}</span>
              </div>
              {data.cooling && (
                <div className="dew-row">
                  <span className="dew-key">Bewertung</span>
                  <span className={`dew-chip dew-chip-${r.status}`}>{DEW_STATUS_LABEL[r.status]}</span>
                </div>
              )}
              <div className="dew-row">
                <span className="dew-key">Taupunkt</span>
                <span className="dew-value">{formatCelsius(r.dew_point)}</span>
              </div>
              {data.cooling && (
                <div className="dew-row">
                  <span className="dew-key">Abstand zum Vorlauf</span>
                  <span className="dew-value">{formatKelvin(r.margin)}</span>
                </div>
              )}
              <div className="room-subtitle">
                {formatCelsius(r.temperature)} · {r.humidity ?? "–"} % · Ventil{" "}
                {r.valve == null ? "–" : `${Math.round(r.valve * 100)} %`}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
