import React, { useState, useEffect, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import ProfileDayChart from "./ProfileDayChart";
import { AppIcon, getIcon } from "../icons/IconMap";
import { apiErrorMessage, logApiError } from "../services/api";
import type { ClimateMode } from "../services/types";
import { useProfile, useAddBlock, useClearBlock } from "../hooks/useProfiles";
import { useProfileNames } from "../hooks/useProfileNames";
import BusyOverlay from "./BusyOverlay";
import ConfirmRow from "./ConfirmRow";
import { hours, minutes, temperatures } from "../lib/timePicker";
import "../styles/styles.css";

export default function TimeBlockDetail() {
  const { roomName, profileName, day, blockIndex } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const mode = (searchParams.get("mode") as ClimateMode) || undefined;

  const [startHour, setStartHour] = useState("00");
  const [startMinute, setStartMinute] = useState("00");
  const [endHour, setEndHour] = useState("00");
  const [endMinute, setEndMinute] = useState("00");
  const [temp, setTemp] = useState(17);

  const [editField, setEditField] =
    useState<null | "start" | "end" | "temp">(null);
  const [changed, setChanged] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<null | "save" | "delete">(null);

  const nr = parseInt(profileName!.replace(/^P/i, ""), 10);
  const { data: week } = useProfile(roomName, nr, mode);
  const { data: profileNames } = useProfileNames();
  const addBlock = useAddBlock(roomName ?? "", nr, mode);
  const clearBlock = useClearBlock(roomName ?? "", nr, mode);

  const startHourRef = useRef<HTMLDivElement>(null);
  const startMinuteRef = useRef<HTMLDivElement>(null);
  const endHourRef = useRef<HTMLDivElement>(null);
  const endMinuteRef = useRef<HTMLDivElement>(null);
  const tempRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!week || !day) return;
    const dayBlocks = week.days[day.toLowerCase()] ?? [];
    const block = dayBlocks[Number(blockIndex)];
    if (!block) return;

    const [sh, sm] = block.start.split(":");
    const [eh, em] = block.end.split(":");

    setStartHour(sh);
    setStartMinute(sm);
    setEndHour(eh);
    setEndMinute(em);
    setTemp(block.setpoint);
  }, [week, day, blockIndex]);

  useEffect(() => {
    if (editField === "start") {
      if (startHourRef.current)
        startHourRef.current.scrollTop = hours.indexOf(startHour) * 40;
      if (startMinuteRef.current)
        startMinuteRef.current.scrollTop = minutes.indexOf(startMinute) * 40;
    }
    if (editField === "end") {
      if (endHourRef.current)
        endHourRef.current.scrollTop = hours.indexOf(endHour) * 40;
      if (endMinuteRef.current)
        endMinuteRef.current.scrollTop = minutes.indexOf(endMinute) * 40;
    }
    if (editField === "temp") {
      if (tempRef.current) {
        const index = Math.round((temp - 15) / 0.5);
        tempRef.current.scrollTop = index * 40;
      }
    }
  }, [editField, startHour, startMinute, endHour, endMinute, temp]);

  function markChanged() {
    setChanged(true);
  }

  function handleScroll<T>(
    e: React.UIEvent<HTMLDivElement>,
    setter: (v: T) => void,
    values: T[]
  ) {
    const itemHeight = 40;
    const index = Math.round(e.currentTarget.scrollTop / itemHeight);
    const clamped = Math.max(0, Math.min(values.length - 1, index));
    const value = values[clamped];
    setter(value);
    markChanged();
  }

  async function saveBlock() {
    if (busy) return;
    const start = `${startHour}:${startMinute}`;
    const end = `${endHour}:${endMinute}`;

    setError("");
    setBusy("save");
    try {
      await addBlock.mutateAsync({ weekday: day!, body: { start, end, setpoint: temp } });
      navigate(-1);
    } catch (err: unknown) {
      logApiError("saveBlock", err);
      setError(apiErrorMessage(err));
      setBusy(null);
    }
  }

  async function deleteBlock() {
    if (busy) return;
    const start = `${startHour}:${startMinute}`;
    const end = `${endHour}:${endMinute}`;

    setError("");
    setBusy("delete");
    try {
      await clearBlock.mutateAsync({ weekday: day!, body: { start, end } });
      navigate(-1);
    } catch (err: unknown) {
      logApiError("deleteBlock", err);
      setError(apiErrorMessage(err));
      setBusy(null);
    }
  }

  const displayName =
    profileNames?.[String(nr)] ?? profileName;

  return (
    <div className="room-grid">

      {busy && (
        <BusyOverlay
          text={busy === "delete" ? "Zeitabschnitt wird gelöscht…" : "Wird gespeichert…"}
        />
      )}

      {/* Back-Kachel */}
      <div className="back-card">
        <span className="back-left" onClick={() => navigate(-1)}>
          <AppIcon name="arrowleft" />
        </span>

        <span className="back-center">
          {roomName} – {displayName}
        </span>

        <span className="back-right">{getIcon(roomName)}</span>
      </div>

      {/* Graph */}
      <ProfileDayChart
        day={day!}
        blocks={[
          {
            start: `${startHour}:${startMinute}`,
            end: `${endHour}:${endMinute}`,
            setpoint: temp
          }
        ]}
        roomName={roomName!}
        profileName={displayName}
        profileNumber={nr}
        mode={mode}
      />

      {/* Edit-Karte */}
      <div className="room-card">

        {/* Start */}
        <div className="time-block-row" onClick={() => setEditField("start")}>
          <span className="time-range">Start:</span>
          <span className="temp-value">
            {startHour}:{startMinute}
          </span>
        </div>

        {editField === "start" && (
          <div className="time-picker-container">
            <div
              className="time-picker-close"
              onClick={() => setEditField(null)}
            >
              <AppIcon name="chevron-up" />
            </div>

            <div className="time-picker-wheel-wrapper">
              <div
                ref={startHourRef}
                className="time-picker-wheel"
                onScroll={(e) => handleScroll(e, setStartHour, hours)}
              >
                {hours.map((h) => (
                  <div
                    key={h}
                    className={`time-picker-item ${
                      startHour === h ? "active" : ""
                    }`}
                  >
                    {h}
                  </div>
                ))}
              </div>

              <div
                ref={startMinuteRef}
                className="time-picker-wheel"
                onScroll={(e) => handleScroll(e, setStartMinute, minutes)}
              >
                {minutes.map((m) => (
                  <div
                    key={m}
                    className={`time-picker-item ${
                      startMinute === m ? "active" : ""
                    }`}
                  >
                    {m}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Ende */}
        <div className="time-block-row" onClick={() => setEditField("end")}>
          <span className="time-range">Ende:</span>
          <span className="temp-value">
            {endHour}:{endMinute}
          </span>
        </div>

        {editField === "end" && (
          <div className="time-picker-container">
            <div
              className="time-picker-close"
              onClick={() => setEditField(null)}
            >
              <AppIcon name="chevron-up" />
            </div>
            <div className="time-picker-wheel-wrapper">
              <div
                ref={endHourRef}
                className="time-picker-wheel"
                onScroll={(e) => handleScroll(e, setEndHour, hours)}
              >
                {hours.map((h) => (
                  <div
                    key={h}
                    className={`time-picker-item ${
                      endHour === h ? "active" : ""
                    }`}
                  >
                    {h}
                  </div>
                ))}
              </div>

              <div
                ref={endMinuteRef}
                className="time-picker-wheel"
                onScroll={(e) => handleScroll(e, setEndMinute, minutes)}
              >
                {minutes.map((m) => (
                  <div
                    key={m}
                    className={`time-picker-item ${
                      endMinute === m ? "active" : ""
                    }`}
                  >
                    {m}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Temperatur */}
        <div className="time-block-row" onClick={() => setEditField("temp")}>
          <span className="time-range">Temperatur:</span>
          <span className="temp-value">{temp.toFixed(1)}°C</span>
        </div>

        {editField === "temp" && (
          <div className="time-picker-container">
            <div
              className="time-picker-close"
              onClick={() => setEditField(null)}
            >
              <AppIcon name="chevron-up" />
            </div>

            <div className="time-picker-wheel-wrapper">
              <div
                ref={tempRef}
                className="time-picker-wheel"
                onScroll={(e) =>
                  handleScroll(
                    e,
                    (v) => setTemp(parseFloat(v)),
                    temperatures
                  )
                }
              >
                {temperatures.map((t) => (
                  <div
                    key={t}
                    className={`time-picker-item ${
                      temp.toFixed(1) === t ? "active" : ""
                    }`}
                  >
                    {t}°C
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {error && <div className="validation-error">{error}</div>}

      {/* Speichern (Pfeil zurück / Haken) + Löschen */}
      <div className="room-card" style={{ gap: "0.9rem" }}>
        <ConfirmRow
          onCancel={() => navigate(-1)}
          onConfirm={saveBlock}
          disabled={busy !== null || !changed}
        />
        <div
          className="add-block-button"
          style={{
            textAlign: "center",
            color: "red",
            cursor: busy ? "default" : "pointer",
            opacity: busy ? 0.4 : 1,
          }}
          onClick={busy ? undefined : deleteBlock}
        >
          Zeitabschnitt löschen
        </div>
      </div>
    </div>
  );
}
