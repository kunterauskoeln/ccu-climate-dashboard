import React, { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { apiErrorMessage, logApiError } from "../services/api";
import type { ClimateMode } from "../services/types";
import { AppIcon, getIcon } from "../icons/IconMap";
import ProfileDayChart from "./ProfileDayChart";
import BusyOverlay from "./BusyOverlay";
import ConfirmRow from "./ConfirmRow";
import { useProfile, useCopyProfile } from "../hooks/useProfiles";
import { useProfileNames, useSetProfileName } from "../hooks/useProfileNames";
import { useRooms } from "../hooks/useRooms";
import { useClimate } from "../hooks/useClimate";
import { useStuckRooms } from "../hooks/useDeviceHealth";
import "../styles/styles.css";

const MODE_OPTIONS: { label: string; value: ClimateMode }[] = [
  { label: "Heizen", value: "heating" },
  { label: "Kühlen", value: "cooling" },
];

export default function HeatingProfileDetail() {
  const { roomName, profileName } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const profileNumber = parseInt(profileName!.replace(/^P/i, ""), 10);

  // Default mode = whatever the system currently runs, unless the URL
  // already names one (e.g. coming back from a day/block edit).
  const { data: climate } = useClimate();
  const systemMode: ClimateMode | null = climate ? (climate.cooling ? "cooling" : "heating") : null;
  const [modeOverride, setModeOverride] = useState<ClimateMode | null>(
    (searchParams.get("mode") as ClimateMode) || null
  );
  const mode = modeOverride ?? systemMode;

  function chooseMode(next: ClimateMode) {
    setModeOverride(next);
    setSearchParams({ mode: next }, { replace: true });
  }

  const { data: week } = useProfile(roomName, profileNumber, mode ?? undefined);
  const { data: storedNames } = useProfileNames();
  const { data: rooms = [] } = useRooms();
  const stuck = useStuckRooms().has(roomName ?? "");
  const setProfileName = useSetProfileName();
  const copyProfile = useCopyProfile(roomName!, profileNumber, mode ?? undefined);

  const [renameOpen, setRenameOpen] = useState(false);
  const [editableName, setEditableName] = useState("");

  const [copyOpen, setCopyOpen] = useState(false);
  const [copyToRoom, setCopyToRoom] = useState(roomName ?? "");
  const [copyToProfile, setCopyToProfile] = useState(profileNumber);
  const [copyBusy, setCopyBusy] = useState(false);
  const [copyMsg, setCopyMsg] = useState("");
  const [copyError, setCopyError] = useState("");

  useEffect(() => {
    setCopyToRoom(roomName ?? "");
    setCopyToProfile(profileNumber);
  }, [roomName, profileNumber]);

  if (!week || !mode) {
    return <div>Lade Profil…</div>;
  }

  const displayName = storedNames?.[profileNumber] ?? profileName;
  // Only the profile the thermostat runs is shown/edited on the device; every
  // other one is the stored plan that gets written when the room switches to it.
  const runningProfile = rooms.find((r) => r.room === roomName)?.active_profile ?? null;
  const whereText =
    mode !== systemMode
      ? `Gespeicherter Plan für ${mode === "cooling" ? "Kühlen" : "Heizen"}: wird beim Wechsel der Betriebsart übertragen.`
      : runningProfile === profileNumber
      ? "Läuft gerade auf dem Thermostat: Änderungen gehen direkt dorthin."
      : runningProfile != null
      ? "Gespeicherter Plan, liegt noch nicht auf dem Thermostat: wird übertragen, sobald der Raum auf dieses Profil umschaltet. Änderungen kosten keinen Funk."
      : "";

  function saveNewName() {
    setProfileName.mutate(
      { profile: profileNumber, label: editableName },
      { onSuccess: () => setRenameOpen(false) }
    );
  }

  function closeCopy() {
    setCopyOpen(false);
    setCopyMsg("");
    setCopyError("");
  }

  async function runCopy() {
    setCopyError("");
    setCopyMsg("");
    const roomNames = rooms.map((r) => r.room);
    const targets =
      copyToRoom === "__ALL__" ? roomNames.filter((r) => r !== roomName) : [copyToRoom];
    if (targets.length === 0) {
      setCopyError("Kein Zielraum.");
      return;
    }
    if (
      copyToRoom !== "__ALL__" &&
      copyToRoom === roomName &&
      copyToProfile === profileNumber
    ) {
      setCopyError("Ziel ist identisch mit der Quelle.");
      return;
    }

    setCopyBusy(true);
    const done: string[] = [];
    const failed: string[] = [];
    for (const t of targets) {
      try {
        await copyProfile.mutateAsync({ to_room: t, to_profile: copyToProfile });
        done.push(t);
      } catch (err: unknown) {
        failed.push(t);
        logApiError(t, err);
      }
      setCopyMsg(
        `OK: ${done.join(", ") || "–"}` +
          (failed.length ? ` · Fehler: ${failed.join(", ")}` : "")
      );
    }
    setCopyBusy(false);
    if (failed.length) setCopyError(`${failed.length} Raum/Räume fehlgeschlagen.`);
  }

  return (
    <div className="room-grid equal-height center-cards">

      {copyBusy && (
        <BusyOverlay text="Profil wird kopiert…" sub={copyMsg || undefined} />
      )}

      <div className="back-card" onClick={() => navigate("/settings/heating-profiles")}>
        <span className="back-left">
          <AppIcon name="arrowleft" />
        </span>
        <span className="back-center">
          {roomName} – {displayName}
        </span>

        <span className="back-right">
          {getIcon(roomName)}
        </span>
      </div>

      <div className="room-card" style={{ gap: "0.5rem" }}>
        <div className="room-subtitle">
          Modus{mode === systemMode ? " (aktiv)" : ""}
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {MODE_OPTIONS.map((opt) => (
            <div
              key={opt.value}
              onClick={() => chooseMode(opt.value)}
              className={`profile-mini-card-vertical ${
                mode === opt.value ? "active-profile" : ""
              }`}
              style={{ flex: 1, textAlign: "center", cursor: "pointer" }}
            >
              {opt.label}
            </div>
          ))}
        </div>
        {whereText && <div className="room-subtitle">{whereText}</div>}
      </div>

      {stuck && (
        <div className="room-card dew-border-knapp" style={{ gap: "0.4rem" }}>
          <div className="setting-name">Plan nicht am Thermostat angekommen</div>
          <div className="room-subtitle">
            Die CCU kann dem Thermostat seit längerer Zeit keine Einstellungen übertragen.
            Der Plan hier ist in der CCU gespeichert, der Thermostat arbeitet aber noch mit
            einem älteren. Abhilfe: am Thermostat kurz die Systemtaste drücken und die
            Servicemeldungen der CCU prüfen. Steckt ein ungültiger Wert in den Einstellungen,
            hilft das nicht (siehe Handbuch, CCU-Hintergrund).
          </div>
        </div>
      )}

      <div
        className="room-card"
        onClick={() => {
          setEditableName(displayName ?? "");
          setRenameOpen(true);
        }}
        style={{ cursor: "pointer", textAlign: "center" }}
      >
        <div className="add-block-button">Profil umbenennen</div>
      </div>

      {renameOpen && (
        <div className="room-card" style={{ padding: "20px" }}>

          <input
            type="text"
            value={editableName}
            onChange={(e) => setEditableName(e.target.value)}
            style={{
              width: "100%",
              fontSize: "1.2rem",
              padding: "10px",
              marginBottom: "20px",
              borderRadius: "8px",
              border: "1px solid #ccc"
            }}
          />

          <ConfirmRow onCancel={() => setRenameOpen(false)} onConfirm={saveNewName} />

          {setProfileName.isError && (
            <div className="validation-error" style={{ marginTop: "12px" }}>
              {apiErrorMessage(setProfileName.error)}
            </div>
          )}

        </div>
      )}

      <div className="room-card" style={{ gap: "0.75rem" }}>
        {!copyOpen ? (
          <div
            className="add-block-button"
            style={{ textAlign: "center", cursor: "pointer" }}
            onClick={() => setCopyOpen(true)}
          >
            Profil kopieren
          </div>
        ) : (
          <>
            <div className="dropdown-block">
              <label>Zielraum</label>
              <select value={copyToRoom} onChange={(e) => setCopyToRoom(e.target.value)}>
                <option value="__ALL__">Alle anderen Räume</option>
                {rooms.map((r) => (
                  <option key={r.room} value={r.room}>{r.room}</option>
                ))}
              </select>
            </div>

            <div className="dropdown-block">
              <label>Zielprofil</label>
              <select
                value={copyToProfile}
                onChange={(e) => setCopyToProfile(Number(e.target.value))}
              >
                {[1, 2, 3, 4, 5, 6].map((p) => (
                  <option key={p} value={p}>{storedNames?.[String(p)] ?? `P${p}`}</option>
                ))}
              </select>
            </div>

            <ConfirmRow onCancel={closeCopy} onConfirm={runCopy} disabled={copyBusy} />

            {copyMsg && (
              <div style={{ color: "var(--color-primary)" }}>{copyMsg}</div>
            )}
            {copyError && (
              <div className="validation-error">{copyError}</div>
            )}
          </>
        )}
      </div>

      <div className="profile-visual-container" style={{ cursor: "pointer" }}>
        {Object.entries(week.days).map(([day, blocks]) => (

          <ProfileDayChart
            key={day}
            day={day}
            blocks={blocks}
            roomName={roomName}
            profileName={displayName}
            profileNumber={profileNumber}
            mode={mode}
          />
        ))}
      </div>
    </div>
  );
}
