import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppIcon } from "../icons/IconMap";
import { apiErrorMessage } from "../services/api";
import type { HistoryEntry, RestoreResult } from "../services/types";
import { useHistory, useRestoreHistory } from "../hooks/useHistory";
import { useProfileNames } from "../hooks/useProfileNames";
import BusyOverlay from "./BusyOverlay";
import ConfirmRow from "./ConfirmRow";
import "../styles/styles.css";

const MODE_LABEL: Record<string, string> = { heating: "Heizen", cooling: "Kühlen" };

function formatWhen(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
}

function resultText(result: RestoreResult): string {
  if (!result.background) return "Zurückgesetzt.";
  const rest = result.deferred > 0
    ? ` ${result.deferred} Profil-Tag(e) sind danach noch offen – dann denselben Eintrag erneut zurücksetzen.`
    : "";
  return `Wird auf die Thermostate übertragen (${result.days} Profil-Tag(e)), Fortschritt oben im Hinweis.${rest}`;
}

export default function ChangeHistory() {
  const navigate = useNavigate();
  const { data: entries = [], isLoading, error } = useHistory();
  const { data: profileNames } = useProfileNames();
  const restore = useRestoreHistory();
  const [selected, setSelected] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  const profileLabel = (entry: HistoryEntry) =>
    profileNames?.[String(entry.profile)] ?? `P${entry.profile}`;

  function confirm(entry: HistoryEntry) {
    setMessage("");
    restore.mutate(entry.id, {
      onSuccess: (result) => {
        setSelected(null);
        setMessage(resultText(result));
      },
    });
  }

  return (
    <div className="room-grid">
      {restore.isPending && <BusyOverlay text="Wird zurückgesetzt…" />}

      <div className="back-card" onClick={() => navigate("/settings")} style={{ cursor: "pointer" }}>
        <span className="back-left"><AppIcon name="arrowleft" /></span>
        <span className="back-center">Änderungshistorie</span>
        <span className="back-right"><AppIcon name="history" /></span>
      </div>

      <div className="room-card history-list">
        <div className="room-subtitle">
          Erfasst werden Änderungen an Heizprofilen im aktiven Modus und Umbenennungen von
          Profilen. Beim Wechsel zwischen Heizen und Kühlen wird die Profil-Änderungshistorie
          gelöscht, die Historie der Profil-Umbenennungen bleibt erhalten.
          „Bis hierhin zurücksetzen“ nimmt den gewählten Eintrag und alle neueren zurück.
        </div>

        {message && <div style={{ color: "var(--color-primary)" }}>{message}</div>}
        {restore.isError && (
          <div className="validation-error">{apiErrorMessage(restore.error)}</div>
        )}
        {error && <div className="validation-error">{apiErrorMessage(error)}</div>}

        {isLoading ? (
          <div className="room-subtitle">Lade…</div>
        ) : entries.length === 0 ? (
          <div className="room-subtitle">Noch keine Änderungen erfasst.</div>
        ) : (
          entries.map((entry, index) => {
            const open = selected === entry.id;
            return (
              <div key={entry.id} className={`history-row ${open ? "open" : ""}`}>
                <div
                  className="history-head"
                  onClick={() => {
                    setMessage("");
                    setSelected(open ? null : entry.id);
                  }}
                >
                  <div className="history-meta">
                    <span>{formatWhen(entry.at)}</span>
                    <span className="history-chip">
                      {entry.kind === "name" ? "Name" : MODE_LABEL[entry.mode ?? ""] ?? entry.mode}
                    </span>
                  </div>
                  <div className="history-title">
                    {entry.kind === "name"
                      ? `Profilname P${entry.profile}`
                      : `${entry.room} – ${profileLabel(entry)}`}
                  </div>
                  <div className="history-summary">{entry.summary}</div>
                </div>

                {open && (
                  <div className="history-confirm">
                    <div className="room-subtitle">
                      Bis hierhin zurücksetzen?{" "}
                      {index === 0
                        ? "Nimmt diese Änderung zurück."
                        : `Nimmt diese und ${index} neuere Änderung(en) zurück.`}
                    </div>
                    <ConfirmRow
                      onCancel={() => setSelected(null)}
                      onConfirm={() => confirm(entry)}
                      disabled={restore.isPending}
                    />
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
