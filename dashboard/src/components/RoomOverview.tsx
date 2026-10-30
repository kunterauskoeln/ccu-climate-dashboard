import React, { useEffect } from "react";
import "../styles/styles.css";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { AppIcon, getIcon } from "../icons/IconMap";
import { modeLabel } from "../lib/modes";
import { formatTemp, formatHumidity } from "../lib/format";
import { useRooms, roomsKey } from "../hooks/useRooms";
import { useProfileNames } from "../hooks/useProfileNames";
import { useStuckRooms } from "../hooks/useDeviceHealth";
import ValveBar from "./ValveBar";

export default function RoomOverview() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: rooms = [] } = useRooms();
  const { data: profileNames = {} } = useProfileNames();
  const stuckRooms = useStuckRooms();

  // react-query's refetchOnWindowFocus doesn't fire on bfcache restore
  // (browser back/forward without a real reload) -- catch that case explicitly.
  useEffect(() => {
    const onPageShow = () => queryClient.invalidateQueries({ queryKey: roomsKey });
    window.addEventListener("pageshow", onPageShow);
    return () => window.removeEventListener("pageshow", onPageShow);
  }, [queryClient]);

  return (
    <div className="room-grid equal-height center-cards">
      {rooms.map((room) => {
        const profileDisplayName =
          profileNames?.[String(room.active_profile)] ??
          `P${room.active_profile}`;

        return (
          <div
            className={`room-card ${stuckRooms.has(room.room) ? "dew-border-knapp" : ""}`}
            key={room.room}
            onClick={() => navigate(`/room/${encodeURIComponent(room.room)}`)}
            style={{ cursor: "pointer" }}
          >
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

            <div className="room-subtitle">
              {modeLabel(room.mode_code, room.mode)} • {profileDisplayName}
            </div>

            <div className="temp-row">
              <div className="temp-block">
                <span className="temp-value">
                  {formatTemp(room.set_temperature)}
                </span>
                <span className="temp-label">Soll</span>
              </div>

              <div className="temp-block">
                <span className="temp-value">
                  {formatTemp(room.actual_temperature)}
                </span>
                <span className="temp-label">Ist</span>
              </div>
            </div>

            <ValveBar value={room.valve} />

            {stuckRooms.has(room.room) && (
              <div className="validation-error" style={{ textAlign: "left", marginTop: 0 }}>
                Plan nicht am Thermostat angekommen
              </div>
            )}
          </div>
        );
      })}

      <div
        className="room-card"
        onClick={() => navigate("/settings")}
        style={{ cursor: "pointer" }}
      >
        <div className="room-header-left">
          <span className="room-icon"><AppIcon name="zahnrad" /></span>
          <span className="room-name">Einstellungen</span>
        </div>
      </div>
    </div>
  );
}
