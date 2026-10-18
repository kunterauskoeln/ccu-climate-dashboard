import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import "../styles/styles.css";
import TemperatureDial from "./TemperatureDial";
import ValveBar from "./ValveBar";
import { AppIcon, getIcon } from "../icons/IconMap";
import { MODE_LABELS } from "../lib/modes";
import { formatHumidity } from "../lib/format";
import { useDewPoint } from "../hooks/useDewPoint";
import { DEW_STATUS_LABEL, formatCelsius } from "../lib/dewPoint";
import { useRoom, usePatchRoom } from "../hooks/useRooms";
import { useProfileNames } from "../hooks/useProfileNames";
import { apiErrorMessage } from "../services/api";

export default function RoomDetail() {
  const { roomName } = useParams();
  const navigate = useNavigate();

  const { data: room } = useRoom(roomName);
  const { data: dew } = useDewPoint();
  const dewRoom = dew?.rooms.find((r) => r.room === roomName);
  const { data: profileNames = {} } = useProfileNames();
  const patch = usePatchRoom(roomName);

  // Only the dial needs local state (live-drag vs. commit-on-release); mode
  // and active profile are plain controlled inputs straight off the query.
  const [setpoint, setSetpoint] = useState<number>(20);
  useEffect(() => {
    if (room) setSetpoint(room.set_temperature ?? 20);
  }, [room]);

  if (!room) return <div style={{ padding: "1rem" }}>Lade...</div>;

  const activeProfile = room.active_profile ?? 1;
  const profileDisplayName = profileNames?.[String(activeProfile)] ?? `P${activeProfile}`;

  return (
    <div className="room-grid">

      <div className="back-card" onClick={() => navigate(-1)} style={{ cursor: "pointer" }}>
        <span className="back-left">
            <AppIcon name="arrowleft" />
          </span>
        <span className="back-center">
          {roomName} – {profileDisplayName}
        </span>

        <span className="back-right">
          {getIcon(roomName)}
        </span>
      </div>

      <div className="room-card">

        <div className="room-header">
          <div className="room-header-left">
            <span className="room-icon">{getIcon(room.room)}</span>
            <span className="room-name">{room.room}</span>
          </div>

          <div className="room-humidity-top">
            <span className="flex items-center gap-1">
              <AppIcon name="tropfen" />
              {formatHumidity(room.humidity)}
            </span>
          </div>
        </div>

        {dewRoom && dewRoom.dew_point != null && (
          <div className="room-subtitle">
            Taupunkt {formatCelsius(dewRoom.dew_point)}
            {(dewRoom.status === "knapp" || dewRoom.status === "gefahr") && (
              <span className="validation-error"> • {DEW_STATUS_LABEL[dewRoom.status]}</span>
            )}
          </div>
        )}

        <div className="room-subtitle">
          {MODE_LABELS[room.mode_code]} • {profileDisplayName}
          {room.reachable === false && (
            <span className="validation-error"> • nicht erreichbar</span>
          )}
        </div>

        <div className="slider-container">
          <TemperatureDial
            value={setpoint}
            min={5}
            max={30}
            step={0.5}
            size={240}
            onChange={setSetpoint}
            onCommit={(celsius) => {
              setSetpoint(celsius);
              patch.mutate({ setpoint: celsius });
            }}
          />
        </div>

        <ValveBar value={room.valve} />

        {patch.isError && (
          <div className="validation-error">{apiErrorMessage(patch.error)}</div>
        )}

        <div className="dropdowns">

          <div className="dropdown-block">
            <label>Modus</label>
            <select
              value={room.mode_code}
              onChange={(e) => patch.mutate({ mode: Number(e.target.value) })}
            >
              {Object.entries(MODE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          <div className="dropdown-block">
            <label>Profil</label>
            <select
              value={activeProfile}
              onChange={(e) => patch.mutate({ active_profile: Number(e.target.value) })}
            >
              {[1, 2, 3, 4, 5, 6].map((p) => {
                const name = profileNames?.[String(p)] ?? `P${p}`;
                return (
                  <option key={p} value={p}>
                    {name}
                  </option>
                );
              })}
            </select>
          </div>

        </div>
      </div>

    </div>
  );
}
