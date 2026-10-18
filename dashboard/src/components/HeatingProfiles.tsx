import React from "react";
import { useNavigate } from "react-router-dom";
import { AppIcon, getIcon } from "../icons/IconMap";
import { useRooms } from "../hooks/useRooms";
import { useProfileNames } from "../hooks/useProfileNames";
import ApartmentProfileCard from "./ApartmentProfileCard";
import "../styles/styles.css";

export default function HeatingProfiles() {
  const navigate = useNavigate();

  const { data: rooms, isLoading: roomsLoading } = useRooms();
  const { data: profileNames, isLoading: namesLoading } = useProfileNames();

  if (roomsLoading || namesLoading) {
    return (
      <div className="room-grid">
        <div className="back-card">
          <span className="back-left"><AppIcon name="arrowleft" /></span>
          <span className="back-center">Heizprofile</span>
          <span className="back-right"><AppIcon name="profile" /></span>
        </div>

        <div className="loading" style={{ padding: "20px", textAlign: "center" }}>
          Lade Profilnamen…
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="room-grid uniform-rows">

        <div
          className="back-card"
          onClick={() => navigate("/settings")}
          style={{ cursor: "pointer" }}
        >
          <span className="back-left"><AppIcon name="arrowleft" /></span>
          <span className="back-center">Heizprofile</span>
          <span className="back-right"><AppIcon name="profile" /></span>
        </div>

        <ApartmentProfileCard rooms={rooms ?? []} profileNames={profileNames} />

        {(rooms ?? []).map((room) => (
          <div key={room.room} className="room-card">

            <div className="room-header-row">
              <span className="room-name">{room.room}</span>
              <span className="room-icon room-icon-right">{getIcon(room.room)}</span>
            </div>

            {/* same height as the sentence on the "Wohnung" card, so the profile
                buttons line up across cards side by side */}
            <div className="room-subtitle subtitle-spacer" aria-hidden="true">&nbsp;</div>

            <div className="profile-list-vertical">
              {[1, 2, 3, 4, 5, 6].map((p) => {
                const isActive = room.active_profile === p;

                const displayName =
                  profileNames?.[String(p)] ?? `P${p}`;

                return (
                  <div
                    key={p}
                    className={`profile-mini-card-vertical ${
                      isActive ? "active-profile" : ""
                    }`}
                    onClick={() => navigate(`/settings/heating-profiles/${room.room}/P${p}`)}
                    style={{ cursor: "pointer" }}
                  >
                    <span>{displayName}</span>
                  </div>
                );
              })}
            </div>

          </div>
        ))}
      </div>
    </div>
  );
}
