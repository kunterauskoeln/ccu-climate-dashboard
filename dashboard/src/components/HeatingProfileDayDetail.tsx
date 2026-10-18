import React, { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import ProfileDayChart from "./ProfileDayChart";
import BusyOverlay from "./BusyOverlay";
import ConfirmRow from "./ConfirmRow";
import { AppIcon, getIcon } from "../icons/IconMap";
import { apiErrorMessage, logApiError } from "../services/api";
import type { ClimateMode } from "../services/types";
import { useProfile, useCopyProfile } from "../hooks/useProfiles";
import { useProfileNames } from "../hooks/useProfileNames";
import "../styles/styles.css";

const DAYS = [
  ["MONDAY", "Montag"],
  ["TUESDAY", "Dienstag"],
  ["WEDNESDAY", "Mittwoch"],
  ["THURSDAY", "Donnerstag"],
  ["FRIDAY", "Freitag"],
  ["SATURDAY", "Samstag"],
  ["SUNDAY", "Sonntag"],
] as const;

export default function HeatingProfileDayDetail() {
  const { roomName, profileName, day } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const mode = (searchParams.get("mode") as ClimateMode) || undefined;
  const modeQuery = mode ? `?mode=${mode}` : "";

  const nr = parseInt(profileName!.replace(/^P/i, ""), 10);
  const { data: week, isLoading } = useProfile(roomName, nr, mode);
  const { data: profileNames } = useProfileNames();
  const copyProfile = useCopyProfile(roomName!, nr, mode);

  const [copyOpen, setCopyOpen] = useState(false);
  const [copyToDay, setCopyToDay] = useState("");
  const [copyBusy, setCopyBusy] = useState(false);
  const [copyMsg, setCopyMsg] = useState("");
  const [copyError, setCopyError] = useState("");

  const blocks = week?.days[day!.toLowerCase()] ?? [];

  const weekdayMap: Record<string, string> = {
    MONDAY: "MO",
    TUESDAY: "DI",
    WEDNESDAY: "MI",
    THURSDAY: "DO",
    FRIDAY: "FR",
    SATURDAY: "SA",
    SUNDAY: "SO"
  };

  const displayName = profileNames?.[nr] ?? profileName;

  async function runCopy() {
    setCopyError("");
    setCopyMsg("");
    if (!copyToDay) {
      setCopyError("Bitte einen Zieltag wählen.");
      return;
    }
    const here = day!.toUpperCase();
    const allOther = DAYS.map(([k]) => k).filter((k) => k !== here);
    setCopyBusy(true);
    try {
      await copyProfile.mutateAsync({
        to_profile: nr,
        from_day: here,
        ...(copyToDay === "__ALL__"
          ? { to_days: allOther }
          : { to_day: copyToDay }),
      });
      setCopyMsg(
        copyToDay === "__ALL__"
          ? "Auf alle anderen Tage kopiert."
          : `Nach ${DAYS.find(([k]) => k === copyToDay)?.[1] ?? copyToDay} kopiert.`
      );
    } catch (err: unknown) {
      logApiError("runCopy", err);
      setCopyError(apiErrorMessage(err));
    } finally {
      setCopyBusy(false);
    }
  }

  if (isLoading || !week) {
    return (
      <div className="room-grid">
        <div className="back-card">
          <span className="back-left"><AppIcon name="arrowleft" /></span>
          <span className="back-center">Lade Profil…</span>
          <span className="back-right">{getIcon(roomName!)}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="room-grid">

      {copyBusy && <BusyOverlay text="Tag wird kopiert…" />}

      {/* Back-Kachel */}
      <div
        className="back-card"
        onClick={() => navigate(-1)}
        style={{ cursor: "pointer" }}
      >
        <span className="back-left"><AppIcon name="arrowleft" /></span>

        <span className="back-center">
          {roomName} – {displayName} – {weekdayMap[day!.toUpperCase()]}
        </span>

        <span className="back-right">{getIcon(roomName!)}</span>
      </div>

      {/* Tages-Graph */}
      <ProfileDayChart
        day={day!}
        blocks={blocks}
        roomName={roomName!}
        profileName={displayName}
        profileNumber={nr}
        mode={mode}
      />

      {/* Zeitabschnitte */}
      <div className="room-card">
        {blocks.map((b, i) => (
          <div
            key={i}
            className="time-block-row"
            style={{ cursor: "pointer" }}
            onClick={() =>
              navigate(
                `/settings/heating-profiles/${roomName}/P${nr}/${day}/${i}${modeQuery}`
              )
            }
          >
            <span className="time-range">
              {b.start} – {b.end}
            </span>
            <span className="temp-value">{b.setpoint}°C</span>
          </div>
        ))}
      </div>

      {/* Hinzufügen */}
      <div
        className="room-card"
        style={{ cursor: "pointer" }}
        onClick={() =>
          navigate(
            `/settings/heating-profiles/${roomName}/P${nr}/${day}/add${modeQuery}`
          )
        }
      >
        <div className="add-block-button" style={{ textAlign: "center" }}>
          + Zeitabschnitt hinzufügen
        </div>
      </div>

      {/* Tag kopieren – Aufklapp-Kachel */}
      <div className="room-card" style={{ gap: "0.75rem" }}>
        {!copyOpen ? (
          <div
            className="add-block-button"
            style={{ textAlign: "center", cursor: "pointer" }}
            onClick={() => setCopyOpen(true)}
          >
            Tag kopieren nach…
          </div>
        ) : (
          <>
            <div className="dropdown-block">
              <label>Zieltag</label>
              <select value={copyToDay} onChange={(e) => setCopyToDay(e.target.value)}>
                <option value="">– wählen –</option>
                <option value="__ALL__">Alle anderen Tage</option>
                {DAYS.filter(([k]) => k !== day!.toUpperCase()).map(([k, label]) => (
                  <option key={k} value={k}>{label}</option>
                ))}
              </select>
            </div>
            <ConfirmRow
              onCancel={() => {
                setCopyOpen(false);
                setCopyMsg("");
                setCopyError("");
              }}
              onConfirm={runCopy}
              disabled={copyBusy}
            />
            {copyMsg && (
              <div style={{ color: "var(--color-primary)" }}>{copyMsg}</div>
            )}
            {copyError && (
              <div className="validation-error">{copyError}</div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
