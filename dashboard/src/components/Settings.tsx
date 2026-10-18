import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppIcon } from "../icons/IconMap";
import { useTheme, AVAILABLE_THEMES, ELEVATION_LEVELS } from "../theme/ThemeContext";
import { apiErrorMessage } from "../services/api";
import { useClimate, useClimateSchedule, useSetClimate } from "../hooks/useClimate";
import ClimateScheduleForm, { scheduleSummary } from "./ClimateScheduleForm";
import { useDewPoint } from "../hooks/useDewPoint";
import { useDeviceHealth } from "../hooks/useDeviceHealth";
import { useAbsence } from "../hooks/useAbsence";
import { formatAbsenceTime } from "../lib/absence";
import BusyOverlay from "./BusyOverlay";
import ConfirmRow from "./ConfirmRow";
import "../styles/styles.css";

export default function Settings() {
  const navigate = useNavigate();
  const { theme, elevation } = useTheme();
  const currentThemeLabel = AVAILABLE_THEMES.find((item) => item.id === theme)?.label ?? theme;
  const elevationLabel = ELEVATION_LEVELS.find((item) => item.id === elevation)?.label ?? elevation;

  const { data: climate, error: climateLoadError } = useClimate();
  const cooling = climate?.cooling ?? null;
  const setClimate = useSetClimate();
  const { data: schedule } = useClimateSchedule();
  const { data: dew } = useDewPoint();
  const { data: health } = useDeviceHealth();
  const { data: absence } = useAbsence();
  const absenceText = !absence
    ? "…"
    : absence.phase === "geplant"
    ? `Geplant ab ${formatAbsenceTime(absence.start)}`
    : absence.phase === "aktiv"
    ? `Aktiv bis ${formatAbsenceTime(absence.end)}`
    : absence.phase === "rueckkehr"
    ? "Rückkehr läuft"
    : absence.phase === "beendet"
    ? `Zuletzt beendet am ${formatAbsenceTime(absence.end)}`
    : absence.phase === "abgebrochen"
    ? "Aus (Planung verworfen)"
    : "Aus";

  const [climateOpen, setClimateOpen] = useState(false);
  const [climatePick, setClimatePick] = useState<boolean | null>(null);
  // second step: an explicit "really?" before switching the whole house over
  const [climateConfirm, setClimateConfirm] = useState(false);
  const pickLabel = climatePick ? "Kühlen" : "Heizen";

  const climateError = setClimate.isError
    ? apiErrorMessage(setClimate.error)
    : climateLoadError
    ? apiErrorMessage(climateLoadError)
    : "";

  function openClimate() {
    setClimatePick(cooling);
    setClimateConfirm(false);
    setClimateOpen(true);
  }

  function closeClimate() {
    setClimateOpen(false);
    setClimateConfirm(false);
  }

  function switchClimate() {
    if (setClimate.isPending || climatePick === null || climatePick === cooling) return;
    setClimate.mutate(climatePick, { onSuccess: closeClimate });
  }

  return (
    <div>
      {setClimate.isPending && <BusyOverlay text="Betriebsart wird umgeschaltet…" />}
      <div className="room-grid equal-height">
      {/* Back-Kachel */}
      <div className="back-card" onClick={() => navigate("/")}>
        <span className="back-left">
          <AppIcon name="arrowleft" />
        </span>

        <span className="back-center">
          Einstellungen
        </span>

        <span className="back-right">
          <AppIcon name="zahnrad" />
        </span>
      </div>
        <div
          className="room-card"
          onClick={() => navigate("/settings/devices")}
          style={{ cursor: "pointer" }}
        >
          <div className="room-header-left">
            <span className="room-icon"><AppIcon name="devices" /></span>
            <span className="setting-name">Geräte</span>
          </div>
          {health && (
            <div className={`room-subtitle ${health.level === "warnung" ? "validation-error" : ""}`}
                 style={{ textAlign: "left", marginTop: 0 }}>
              {health.level === "warnung"
                ? `${health.problems.length} Hinweis${health.problems.length === 1 ? "" : "e"}`
                : "Alle Geräte in Ordnung"}
            </div>
          )}
        </div>
        <div
          className="room-card"
          onClick={() => navigate("/settings/heating-profiles")}
          style={{ cursor: "pointer" }}
        >
          <div className="room-header-left">
            <span className="room-icon"><AppIcon name="profile" /></span>
            <span className="setting-name">Heizprofile</span>
          </div>
        </div>
        <div
          className="room-card"
          onClick={() => navigate("/settings/history")}
          style={{ cursor: "pointer" }}
        >
          <div className="room-header-left">
            <span className="room-icon"><AppIcon name="history" /></span>
            <span className="setting-name">Änderungshistorie</span>
          </div>
        </div>

        <div className={`room-card ${climateOpen ? "card-wide" : ""}`} style={{ gap: "0.6rem" }}>
          <div
            className="room-header-left"
            style={{ cursor: "pointer" }}
            onClick={() => (climateOpen ? closeClimate() : openClimate())}
          >
            <span className="room-icon"><AppIcon name="thermometer" /></span>
            <span className="setting-name">Betriebsart</span>
          </div>

          {!climateOpen ? (
            <>
              <div className="room-subtitle">
                {cooling === null ? "…" : cooling ? "Kühlen" : "Heizen"}
              </div>
              <div className="room-subtitle">{scheduleSummary(schedule)}</div>
            </>
          ) : !climateConfirm ? (
            <>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                {[
                  { label: "Heizen", value: false },
                  { label: "Kühlen", value: true },
                ].map((opt) => (
                  <div
                    key={opt.label}
                    onClick={() => setClimatePick(opt.value)}
                    className={`profile-mini-card-vertical ${
                      climatePick === opt.value ? "active-profile" : ""
                    }`}
                    style={{ flex: 1, textAlign: "center", cursor: "pointer" }}
                  >
                    {opt.label}
                  </div>
                ))}
              </div>
              <ConfirmRow
                onCancel={closeClimate}
                onConfirm={() => setClimateConfirm(true)}
                disabled={setClimate.isPending || climatePick === null || climatePick === cooling}
              />
              <ClimateScheduleForm />
            </>
          ) : (
            <div className="climate-confirm">
              <div className="setting-name">Wirklich auf {pickLabel} umschalten?</div>
              <div className="room-subtitle">
                Das betrifft alle Räume. Danach werden die gespeicherten
                {climatePick ? " Kühlpläne" : " Heizpläne"} im Hintergrund auf die
                Thermostate übertragen, und die Profil-Änderungshistorie wird gelöscht.
              </div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button
                  className="profile-mini-card-vertical"
                  style={{ flex: 1, textAlign: "center" }}
                  onClick={() => setClimateConfirm(false)}
                  disabled={setClimate.isPending}
                >
                  Abbrechen
                </button>
                <button
                  className="profile-mini-card-vertical active-profile"
                  style={{ flex: 1, textAlign: "center" }}
                  onClick={switchClimate}
                  disabled={setClimate.isPending}
                >
                  Ja, auf {pickLabel} umschalten
                </button>
              </div>
            </div>
          )}

          {climateError && (
            <div className="validation-error" style={{ marginTop: "8px" }}>
              {climateError}
            </div>
          )}
        </div>

        <div
          className="room-card"
          onClick={() => navigate("/settings/absence")}
          style={{ cursor: "pointer" }}
        >
          <div className="room-header-left">
            <span className="room-icon"><AppIcon name="abwesenheit" /></span>
            <span className="setting-name">Abwesenheit</span>
          </div>
          <div className="room-subtitle">{absenceText}</div>
        </div>

        <div
          className="room-card"
          onClick={() => navigate("/settings/valves")}
          style={{ cursor: "pointer" }}
        >
          <div className="room-header-left">
            <span className="room-icon"><AppIcon name="verlauf" /></span>
            <span className="setting-name">Ventilverlauf</span>
          </div>
          <div className="room-subtitle">Ventilöffnung aller Räume der letzten 48 Stunden</div>
        </div>

        <div
          className="room-card"
          onClick={() => navigate("/settings/dew-point")}
          style={{ cursor: "pointer" }}
        >
          <div className="room-header-left">
            <span className="room-icon"><AppIcon name="taupunkt" /></span>
            <span className="setting-name">Taupunkt</span>
          </div>
          <div className={`room-subtitle ${dew && (dew.level === "knapp" || dew.level === "gefahr") ? "validation-error" : ""}`}
               style={{ textAlign: "left", marginTop: 0 }}>
            {dew?.message ?? "…"}
          </div>
        </div>

        <div
          className="room-card"
          onClick={() => navigate("/settings/backup")}
          style={{ cursor: "pointer" }}
        >
          <div className="room-header-left">
            <span className="room-icon"><AppIcon name="backup" /></span>
            <span className="setting-name">Datensicherung</span>
          </div>
          <div className="room-subtitle">Export und Import aller Daten der App</div>
        </div>

        <div
          className="room-card"
          onClick={() => navigate("/settings/theme")}
          style={{ cursor: "pointer" }}
        >
          <div className="room-header-left">
            <span className="room-icon"><AppIcon name="themes" /></span>
            <span className="setting-name">Design</span>
          </div>
          <div className="room-subtitle">
            Aktuelles Thema: {currentThemeLabel}
          </div>
          <div className="room-subtitle">
            Erhaben: {elevationLabel}
          </div>
        </div>
      </div>
    </div>
  );
}
