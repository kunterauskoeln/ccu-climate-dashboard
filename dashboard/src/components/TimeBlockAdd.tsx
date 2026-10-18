import React, { useState, useRef, useEffect } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import ProfileDayChart from "./ProfileDayChart";
import { AppIcon, getIcon } from "../icons/IconMap";
import { apiErrorMessage, logApiError } from "../services/api";
import type { ClimateMode } from "../services/types";
import { useProfile, useAddBlock } from "../hooks/useProfiles";
import { useProfileNames } from "../hooks/useProfileNames";
import BusyOverlay from "./BusyOverlay";
import ConfirmRow from "./ConfirmRow";
import { hours, minutes, temperatures } from "../lib/timePicker";
import "../styles/styles.css";

function handleScroll<T>(
  e: React.UIEvent<HTMLDivElement>,
  setValue: (v: T) => void,
  values: T[]
) {
  const itemHeight = 40;
  const scrollTop = (e.target as HTMLDivElement).scrollTop;

  const index = Math.round(scrollTop / itemHeight);
  const clampedIndex = Math.max(0, Math.min(values.length - 1, index));

  setValue(values[clampedIndex]);
}

export default function TimeBlockAdd() {
  const { roomName, profileName, day } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const mode = (searchParams.get("mode") as ClimateMode) || undefined;

  const nr = profileName ? parseInt(profileName.replace(/^P/i, ""), 10) : 0;
  const { data: week } = useProfile(roomName, nr || undefined, mode);
  const blocks = (day && week?.days[day.toLowerCase()]) || [];
  const { data: storedNames } = useProfileNames();
  const addBlock = useAddBlock(roomName ?? "", nr, mode);

  const [startOpen, setStartOpen] = useState(false);
  const [endOpen, setEndOpen] = useState(false);
  const [editField, setEditField] = useState<null | "temp">(null);

  const [startHour, setStartHour] = useState("08");
  const [startMinute, setStartMinute] = useState("00");
  const [endHour, setEndHour] = useState("12");
  const [endMinute, setEndMinute] = useState("00");

  const [temp, setTemp] = useState(17);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const startHourRef = useRef<HTMLDivElement>(null);
  const startMinuteRef = useRef<HTMLDivElement>(null);
  const endHourRef = useRef<HTMLDivElement>(null);
  const endMinuteRef = useRef<HTMLDivElement>(null);
  const tempWheelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (startOpen) {
      if (startHourRef.current) {
        const index = hours.indexOf(startHour);
        startHourRef.current.scrollTop = index * 40;
      }
      if (startMinuteRef.current) {
        const index = minutes.indexOf(startMinute);
        startMinuteRef.current.scrollTop = index * 40;
      }
    }
  }, [startOpen, startHour, startMinute]);

  useEffect(() => {
    if (endOpen) {
      if (endHourRef.current) {
        const index = hours.indexOf(endHour);
        endHourRef.current.scrollTop = index * 40;
      }
      if (endMinuteRef.current) {
        const index = minutes.indexOf(endMinute);
        endMinuteRef.current.scrollTop = index * 40;
      }
    }
  }, [endOpen, endHour, endMinute]);

  useEffect(() => {
    if (editField === "temp" && tempWheelRef.current) {
      const index = Math.round((temp - 15) / 0.5);
      tempWheelRef.current.scrollTop = index * 40;
    }
  }, [editField, temp]);

  const weekdayMap: Record<string, string> = {
    MONDAY: "MO",
    TUESDAY: "DI",
    WEDNESDAY: "MI",
    THURSDAY: "DO",
    FRIDAY: "FR",
    SATURDAY: "SA",
    SUNDAY: "SO"
  };

  async function saveBlock() {
    if (busy) return;
    setError("");

    const startTime = `${startHour}:${startMinute}`;
    const endTime = `${endHour}:${endMinute}`;

    if (startTime >= endTime) {
      setError("Die Startzeit muss vor der Endzeit liegen.");
      return;
    }

    if (!roomName || !profileName || !day) {
      setError("Ungültige Parameter.");
      return;
    }

    setBusy(true);
    try {
      await addBlock.mutateAsync({
        weekday: day,
        body: { start: startTime, end: endTime, setpoint: temp },
      });
      navigate(-1);
    } catch (err: unknown) {
      logApiError("saveBlock", err);
      setError(apiErrorMessage(err));
      setBusy(false);
    }
  }

  const displayName =
    roomName && nr
      ? storedNames?.[String(nr)] ?? profileName
      : profileName;

  return (
    <div className="room-grid">
      {busy && <BusyOverlay text="Wird gespeichert…" />}
      <div
        className="back-card"
        onClick={() => navigate(-1)}
        style={{ cursor: "pointer" }}
      >
        <span className="back-left"><AppIcon name="arrowleft" /></span>
        <span className="back-center">
          {roomName} – {displayName} –{" "}
          {day ? weekdayMap[day.toUpperCase()] : ""}
        </span>
        <span className="back-right">{getIcon(roomName)}</span>
      </div>

      {day && <ProfileDayChart
                day={day}
                blocks={blocks}
                roomName={roomName}
                profileName={displayName}
                profileNumber={nr}
                mode={mode}
              />
      }

      <div className="room-card">
        <h3 className="card-title">Neuer Zeitabschnitt</h3>

        <div
          className="time-block-row"
          onClick={() => {
            setStartOpen(true);
            setEndOpen(false);
            setEditField(null);
          }}
        >
          <span className="time-range">Start:</span>
          <span className="temp-value">
            {startHour}:{startMinute}
          </span>
        </div>

        {startOpen && (
          <div className="time-picker-container">
            <div
              className="time-picker-close"
              onClick={() => setStartOpen(false)}
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

        <div
          className="time-block-row"
          onClick={() => {
            setEndOpen(true);
            setStartOpen(false);
            setEditField(null);
          }}
        >
          <span className="time-range">Ende:</span>
          <span className="temp-value">
            {endHour}:{endMinute}
          </span>
        </div>

        {endOpen && (
          <div className="time-picker-container">
            <div
              className="time-picker-close"
              onClick={() => setEndOpen(false)}
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

        <div
          className="time-block-row"
          onClick={() => {
            setStartOpen(false);
            setEndOpen(false);
            setEditField("temp");
          }}
        >
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
                ref={tempWheelRef}
                className="time-picker-wheel"
                onScroll={(e) =>
                  handleScroll(
                    e,
                    (v: string) => setTemp(parseFloat(v)),
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

      <div className="room-card">
        <ConfirmRow
          onCancel={() => navigate(-1)}
          onConfirm={saveBlock}
          disabled={busy}
        />
      </div>
    </div>
  );
}
