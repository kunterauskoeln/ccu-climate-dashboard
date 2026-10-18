import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppIcon } from "../icons/IconMap";
import { apiErrorMessage } from "../services/api";
import type { AbsenceState } from "../services/types";
import { useAbsence, useCancelAbsence, useSetAbsence } from "../hooks/useAbsence";
import { useProfileNames } from "../hooks/useProfileNames";
import { formatAbsenceTime, toLocalInput } from "../lib/absence";
import "../styles/styles.css";

const PHASE_TITLE: Record<AbsenceState["phase"], string> = {
  aus: "Keine Abwesenheit",
  geplant: "Abwesenheit geplant",
  aktiv: "Abwesenheit läuft",
  rueckkehr: "Rückkehr läuft",
  beendet: "Letzte Abwesenheit beendet",
  abgebrochen: "Planung abgebrochen",
};

function Form({ current }: { current: AbsenceState }) {
  const { data: names = {} } = useProfileNames();
  const save = useSetAbsence();
  const cancel = useCancelAbsence();
  const running = current.phase === "aktiv";
  const planned = current.phase === "geplant";
  const editing = running || planned;

  const [profile, setProfile] = useState<number>(editing && current.profile ? current.profile : 1);
  const [startNow, setStartNow] = useState(!planned);
  const [start, setStart] = useState(planned && current.start ? toLocalInput(current.start) : "");
  // default end: this time tomorrow (initializer runs once, not on every render)
  const [end, setEnd] = useState(() =>
    editing && current.end
      ? toLocalInput(current.end)
      : toLocalInput(new Date(Date.now() + 24 * 3600 * 1000).toISOString()),
  );
  const [confirmReturn, setConfirmReturn] = useState(false);

  function submit() {
    save.mutate({ profile, start: running || startNow ? null : start, end });
  }

  return (
    <div className="room-card card-wide" style={{ gap: "0.7rem" }}>
      <div className="setting-name">
        {running ? "Laufende Abwesenheit ändern" : planned ? "Planung ändern" : "Abwesenheit planen"}
      </div>

      <label className="absence-field">
        <span className="dew-key">Profil für alle Räume</span>
        <select value={profile} onChange={(e) => setProfile(Number(e.target.value))}>
          {[1, 2, 3, 4, 5, 6].map((p) => (
            <option key={p} value={p}>P{p}{names[String(p)] ? ` – ${names[String(p)]}` : ""}</option>
          ))}
        </select>
      </label>

      {!running && (
        <div className="absence-field">
          <span className="dew-key">Beginn</span>
          <div className="absence-start">
            <label className="setting-toggle" style={{ marginTop: 0 }}>
              <input type="radio" checked={startNow} onChange={() => setStartNow(true)} />
              sofort
            </label>
            <label className="setting-toggle" style={{ marginTop: 0 }}>
              <input type="radio" checked={!startNow} onChange={() => setStartNow(false)} />
              am
            </label>
            <input
              type="datetime-local"
              value={start}
              disabled={startNow}
              onChange={(e) => { setStart(e.target.value); setStartNow(false); }}
            />
          </div>
        </div>
      )}

      <label className="absence-field">
        <span className="dew-key">Ende (danach zurück auf das vorherige Profil je Raum)</span>
        <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
      </label>

      <button
        className="profile-mini-card-vertical active-profile"
        style={{ textAlign: "center" }}
        onClick={submit}
        disabled={save.isPending || !end || (!running && !startNow && !start)}
      >
        {save.isPending ? "Wird gespeichert…" : editing ? "Änderungen speichern" : "Abwesenheit planen"}
      </button>
      {save.isError && <div className="validation-error">{apiErrorMessage(save.error)}</div>}

      {planned && (
        <button className="profile-mini-card-vertical" style={{ textAlign: "center" }}
                onClick={() => cancel.mutate()} disabled={cancel.isPending}>
          Planung verwerfen
        </button>
      )}
      {running && !confirmReturn && (
        <button className="profile-mini-card-vertical" style={{ textAlign: "center" }}
                onClick={() => setConfirmReturn(true)}>
          Jetzt zurückkehren…
        </button>
      )}
      {running && confirmReturn && (
        <div className="climate-confirm">
          <div className="setting-name">Abwesenheit jetzt beenden?</div>
          <div className="room-subtitle">
            Alle Räume gehen auf das Profil zurück, das sie vor der Abwesenheit hatten.
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button className="profile-mini-card-vertical" style={{ flex: 1, textAlign: "center" }}
                    onClick={() => setConfirmReturn(false)}>
              Abbrechen
            </button>
            <button className="profile-mini-card-vertical active-profile"
                    style={{ flex: 1, textAlign: "center" }}
                    onClick={() => cancel.mutate(undefined, { onSuccess: () => setConfirmReturn(false) })}
                    disabled={cancel.isPending}>
              Ja, jetzt zurückkehren
            </button>
          </div>
        </div>
      )}
      {cancel.isError && <div className="validation-error">{apiErrorMessage(cancel.error)}</div>}
    </div>
  );
}

export default function Absence() {
  const navigate = useNavigate();
  const { data, error } = useAbsence();
  const { data: names = {} } = useProfileNames();
  const label = (p: number) => `P${p}${names[String(p)] ? ` (${names[String(p)]})` : ""}`;

  return (
    <div className="room-grid equal-height">
      <div className="back-card" onClick={() => navigate("/settings")} style={{ cursor: "pointer" }}>
        <span className="back-left"><AppIcon name="arrowleft" /></span>
        <span className="back-center">Abwesenheit</span>
        <span className="back-right"><AppIcon name="abwesenheit" /></span>
      </div>

      {error && <div className="room-card card-wide validation-error">{apiErrorMessage(error)}</div>}

      {data && (
        <>
          <div className="room-card card-wide" style={{ gap: "0.4rem" }}>
            <div className="setting-name">{PHASE_TITLE[data.phase]}</div>
            {data.phase !== "aus" && data.profile != null && (
              <div className="room-subtitle">
                Alle Räume auf {label(data.profile)} vom {formatAbsenceTime(data.start)} bis{" "}
                {formatAbsenceTime(data.end)}
              </div>
            )}
            {data.message && <div className="room-subtitle">{data.message}</div>}
            {Object.keys(data.previous).length > 0 && (
              <div className="room-subtitle">
                Zurück auf:{" "}
                {Object.entries(data.previous).map(([room, p]) => `${room} ${label(p)}`).join(" · ")}
              </div>
            )}
            {data.phase === "aus" && (
              <div className="room-subtitle">
                Während einer Abwesenheit laufen alle Räume auf einem gewählten Profil, zum Beispiel
                „Urlaub“. Zum Ende bekommt jeder Raum automatisch das Profil zurück, das er vorher
                hatte. Umgeschaltet wird wie bei „Wohnung“, Raum für Raum im Hintergrund.
              </div>
            )}
          </div>

          {data.phase !== "rueckkehr" && (
            // re-mount on server changes so the form starts from what is stored
            <Form key={`${data.phase}|${data.start}|${data.end}|${data.profile}`} current={data} />
          )}
        </>
      )}
    </div>
  );
}
