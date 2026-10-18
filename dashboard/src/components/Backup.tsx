import React, { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppIcon } from "../icons/IconMap";
import { apiErrorMessage, downloadBackup, exportData, fetchBackup } from "../services/api";
import type { BackupFile, ImportResult } from "../services/types";
import { saveBlob } from "../lib/download";
import { useBackupNow, useBackups, useImportData } from "../hooks/useBackup";
import BusyOverlay from "./BusyOverlay";
import "../styles/styles.css";

const SCHEDULE_TEXT: Record<ImportResult["schedule"], string> = {
  replace: "Zeitplan für das automatische Umschalten",
  clear: "kein Zeitplan (automatisches Umschalten wird entfernt)",
  keep: "ohne Zeitplan (der bestehende bleibt)",
};

function summary(result: ImportResult): string {
  return `${result.rooms} Räume, ${result.profiles} Profile, ${result.names} Profilnamen, ` +
    `${result.valve_rooms} Ventil-Zuordnungen, ${SCHEDULE_TEXT[result.schedule]}`;
}

function formatWhen(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
}

function formatSize(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${Math.round(bytes / 1024)} KB`;
}

export default function Backup() {
  const navigate = useNavigate();
  const fileInput = useRef<HTMLInputElement>(null);

  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");

  const importer = useImportData();
  const [fileName, setFileName] = useState("");
  const [doc, setDoc] = useState<unknown>(null);
  const [check, setCheck] = useState<ImportResult | null>(null);
  const [done, setDone] = useState<ImportResult | null>(null);
  const [fileError, setFileError] = useState("");
  const importCard = useRef<HTMLDivElement>(null);

  const { data: backups, error: backupsError } = useBackups();
  const saveNow = useBackupNow();
  const [listError, setListError] = useState("");

  async function downloadExport() {
    if (exporting) return;
    setExporting(true);
    setExportError("");
    try {
      const { blob, filename } = await exportData();
      saveBlob(blob, filename);
    } catch (err: unknown) {
      setExportError(apiErrorMessage(err));
    } finally {
      setExporting(false);
    }
  }

  function reset() {
    setDoc(null);
    setCheck(null);
    setFileName("");
    setFileError("");
    importer.reset();
    if (fileInput.current) fileInput.current.value = "";
  }

  async function pickFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    reset();
    setDone(null);
    setFileName(file.name);
    let parsed: unknown;
    try {
      parsed = JSON.parse(await file.text());
    } catch {
      setFileError("Die Datei ist kein gültiges JSON.");
      return;
    }
    startCheck(parsed);
  }

  function startCheck(parsed: unknown) {
    setDoc(parsed);
    importer.mutate({ doc: parsed, apply: false }, { onSuccess: setCheck });
  }

  async function download(file: BackupFile) {
    setListError("");
    try {
      saveBlob(await downloadBackup(file.name), file.name);
    } catch (err: unknown) {
      setListError(apiErrorMessage(err));
    }
  }

  /** Load a stored backup into the import check, as if picked from disk. */
  async function restore(file: BackupFile) {
    setListError("");
    reset();
    setDone(null);
    setFileName(file.name);
    try {
      startCheck(await fetchBackup(file.name));
    } catch (err: unknown) {
      setListError(apiErrorMessage(err));
      return;
    }
    importCard.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function applyImport() {
    if (!check?.valid || importer.isPending) return;
    importer.mutate(
      { doc, apply: true },
      {
        onSuccess: (result) => {
          reset();
          setDone(result);
        },
      },
    );
  }

  return (
    <div className="room-grid equal-height">
      {importer.isPending && (
        <BusyOverlay text={check ? "Daten werden importiert…" : "Datei wird geprüft…"} />
      )}

      <div className="back-card" onClick={() => navigate("/settings")} style={{ cursor: "pointer" }}>
        <span className="back-left"><AppIcon name="arrowleft" /></span>
        <span className="back-center">Datensicherung</span>
        <span className="back-right"><AppIcon name="backup" /></span>
      </div>

      <div className="room-card" style={{ gap: "0.6rem" }}>
        <div className="room-header-left">
          <span className="room-icon"><AppIcon name="backup" /></span>
          <span className="setting-name">Export</span>
        </div>
        <div className="room-subtitle">
          Alle Daten der App als Datei: Heiz- und Kühlprofile, Profilnamen, Ventil-Zuordnung,
          Zeitplan für das automatische Umschalten und Änderungshistorie. Ohne
          CCU-Zugangsdaten.
        </div>
        <button
          className="profile-mini-card-vertical"
          style={{ textAlign: "center", marginTop: "auto" }}
          onClick={downloadExport}
          disabled={exporting}
        >
          {exporting ? "Wird erstellt…" : "Export herunterladen"}
        </button>
        {exportError && <div className="validation-error">{exportError}</div>}
      </div>

      <div ref={importCard} className={`room-card ${check || done ? "card-wide" : ""}`} style={{ gap: "0.6rem" }}>
        <div className="room-header-left">
          <span className="room-icon"><AppIcon name="import" /></span>
          <span className="setting-name">Import</span>
        </div>
        <div className="room-subtitle">
          Liest eine Export-Datei ein. Sie wird zuerst vollständig geprüft; übernommen wird
          erst nach Bestätigung. Ersetzt Profile, Profilnamen, Ventil-Zuordnung und den
          Zeitplan für das automatische Umschalten und löscht die Änderungshistorie. Der
          bisherige Stand wird vorher im Datenordner gesichert.
        </div>

        <input
          ref={fileInput}
          type="file"
          accept=".json,application/json"
          onChange={pickFile}
          style={{ display: "none" }}
        />
        {!check && (
          <button
            className="profile-mini-card-vertical"
            style={{ textAlign: "center", marginTop: "auto" }}
            onClick={() => fileInput.current?.click()}
            disabled={importer.isPending}
          >
            Datei auswählen…
          </button>
        )}

        {fileError && <div className="validation-error">{fileName}: {fileError}</div>}
        {importer.isError && (
          <div className="validation-error">{apiErrorMessage(importer.error)}</div>
        )}

        {check && (
          <div className="backup-result">
            <div className="setting-name">{fileName}</div>
            {check.valid ? (
              <div className="room-subtitle">Datei ist gültig: {summary(check)}.</div>
            ) : (
              <>
                <div className="validation-error">
                  Die Datei kann nicht importiert werden ({check.errors.length} Fehler).
                  Es wurde nichts verändert.
                </div>
                <ul className="backup-list backup-errors">
                  {check.errors.map((text) => <li key={text}>{text}</li>)}
                </ul>
              </>
            )}
            {check.warnings.length > 0 && (
              <>
                <div className="room-subtitle">Hinweise:</div>
                <ul className="backup-list">
                  {check.warnings.map((text) => <li key={text}>{text}</li>)}
                </ul>
              </>
            )}
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button
                className="profile-mini-card-vertical"
                style={{ flex: 1, textAlign: "center" }}
                onClick={reset}
                disabled={importer.isPending}
              >
                {check.valid ? "Abbrechen" : "Schließen"}
              </button>
              {check.valid && (
                <button
                  className="profile-mini-card-vertical active-profile"
                  style={{ flex: 1, textAlign: "center" }}
                  onClick={applyImport}
                  disabled={importer.isPending}
                >
                  Import übernehmen
                </button>
              )}
            </div>
          </div>
        )}

        {done && (
          <div className="backup-result">
            <div style={{ color: "var(--color-primary)" }}>
              Import übernommen ({summary(done)}).
              {done.transfer_started &&
                " Die Profile werden im Hintergrund auf die Thermostate übertragen, Fortschritt oben im Hinweis."}
            </div>
            {done.backup_file && (
              <div className="room-subtitle">
                Bisheriger Stand gesichert als {done.backup_file} im Datenordner.
              </div>
            )}
            {done.warnings.length > 0 && (
              <ul className="backup-list">
                {done.warnings.map((text) => <li key={text}>{text}</li>)}
              </ul>
            )}
          </div>
        )}
      </div>

      <div className="room-card card-wide" style={{ gap: "0.6rem" }}>
        <div className="room-header-left">
          <span className="room-icon"><AppIcon name="history" /></span>
          <span className="setting-name">Gespeicherte Sicherungen</span>
        </div>
        <div className="room-subtitle">
          {backups
            ? `Jede Nacht ab ${String(backups.hour).padStart(2, "0")}:00 legt die App automatisch eine Sicherung im Datenordner an (data/backups); die letzten ${backups.keep} bleiben erhalten. Dazu kommen die Kopien, die vor jedem Import entstehen.`
            : "…"}
        </div>
        {backups?.last_error && (
          <div className="validation-error" style={{ textAlign: "left" }}>
            Letzte automatische Sicherung fehlgeschlagen: {backups.last_error}
          </div>
        )}
        {backupsError && <div className="validation-error">{apiErrorMessage(backupsError)}</div>}
        {listError && <div className="validation-error">{listError}</div>}

        {backups && backups.files.length === 0 && (
          <div className="room-subtitle">Noch keine Sicherung vorhanden.</div>
        )}
        {backups && backups.files.length > 0 && (
          <div className="backup-files">
            {backups.files.map((file) => (
              <div key={file.name} className="backup-file">
                <div className="backup-file-info">
                  <span className="dew-value">{formatWhen(file.modified)}</span>
                  <span className="room-subtitle">
                    {file.kind === "auto" ? "automatisch" : "vor einem Import"} · {formatSize(file.size)}
                  </span>
                </div>
                <div className="backup-file-actions">
                  <button className="profile-mini-card-vertical" onClick={() => download(file)}>
                    Herunterladen
                  </button>
                  <button
                    className="profile-mini-card-vertical"
                    onClick={() => restore(file)}
                    disabled={importer.isPending}
                  >
                    Einspielen…
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <button
          className="profile-mini-card-vertical"
          style={{ textAlign: "center" }}
          onClick={() => saveNow.mutate()}
          disabled={saveNow.isPending}
        >
          {saveNow.isPending ? "Wird gesichert…" : "Jetzt sichern"}
        </button>
        {saveNow.isError && <div className="validation-error">{apiErrorMessage(saveNow.error)}</div>}
      </div>
    </div>
  );
}
