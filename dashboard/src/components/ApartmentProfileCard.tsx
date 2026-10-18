import React, { useState } from "react";
import { AppIcon } from "../icons/IconMap";
import { apiErrorMessage } from "../services/api";
import type { ApartmentSwitchResult, ProfileNames, RoomState } from "../services/types";
import { useSetApartmentProfile } from "../hooks/useRooms";

const PROFILES = [1, 2, 3, 4, 5, 6];

function resultText(result: ApartmentSwitchResult, name: string): string {
  if (!result.background) {
    return result.deferred > 0
      ? `${result.deferred} Raum/Räume brauchen zu viele Übertragungen für einen Lauf – bitte erneut tippen.`
      : `Alle Räume stehen schon auf „${name}“.`;
  }
  const parts = [`${result.rooms} Raum/Räume werden auf „${name}“ umgeschaltet, Fortschritt oben im Hinweis.`];
  if (result.skipped > 0) parts.push(`${result.skipped} stand(en) schon darauf.`);
  if (result.deferred > 0) {
    parts.push(`${result.deferred} Raum/Räume folgen – danach erneut tippen.`);
  }
  return parts.join(" ");
}

/** "Wohnung": switch every room to the same profile slot, after an explicit
 * confirmation. The backend switches room by room in the background. */
export default function ApartmentProfileCard({
  rooms,
  profileNames,
}: {
  rooms: RoomState[];
  profileNames: ProfileNames | undefined;
}) {
  const switchAll = useSetApartmentProfile();
  const [pick, setPick] = useState<number | null>(null);
  const [message, setMessage] = useState("");

  const nameOf = (p: number) => profileNames?.[String(p)] ?? `P${p}`;
  // highlighted only when every room runs the same profile
  const common =
    rooms.length > 0 && rooms.every((r) => r.active_profile === rooms[0].active_profile)
      ? rooms[0].active_profile
      : null;

  function confirm() {
    if (pick === null) return;
    const name = nameOf(pick);
    switchAll.mutate(pick, {
      onSuccess: (result) => {
        setPick(null);
        setMessage(resultText(result, name));
      },
    });
  }

  return (
    <div className="room-card">
      <div className="room-header-row">
        <span className="room-name">Wohnung</span>
        <span className="room-icon room-icon-right"><AppIcon name="wohnung" /></span>
      </div>

      {pick === null ? (
        <>
          <div className="room-subtitle">Alle Räume auf ein Profil umschalten</div>
          <div className="profile-list-vertical">
            {PROFILES.map((p) => (
              <div
                key={p}
                className={`profile-mini-card-vertical ${common === p ? "active-profile" : ""}`}
                onClick={() => {
                  setMessage("");
                  switchAll.reset();
                  setPick(p);
                }}
                style={{ cursor: "pointer" }}
              >
                <span>{nameOf(p)}</span>
              </div>
            ))}
          </div>
        </>
      ) : (
        <div className="climate-confirm">
          <div className="setting-name">Alle Räume auf „{nameOf(pick)}“ umschalten?</div>
          <div className="room-subtitle">
            Räume, die schon darauf stehen, werden übersprungen. Weicht der gespeicherte Plan
            eines Raums vom Thermostat ab, wird er vorher übertragen – das kann einige Minuten
            dauern.
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              className="profile-mini-card-vertical"
              style={{ flex: 1, textAlign: "center" }}
              onClick={() => setPick(null)}
              disabled={switchAll.isPending}
            >
              Abbrechen
            </button>
            <button
              className="profile-mini-card-vertical active-profile"
              style={{ flex: 1, textAlign: "center" }}
              onClick={confirm}
              disabled={switchAll.isPending}
            >
              Ja, alle umschalten
            </button>
          </div>
        </div>
      )}

      {message && <div style={{ color: "var(--color-primary)" }}>{message}</div>}
      {switchAll.isError && (
        <div className="validation-error">{apiErrorMessage(switchAll.error)}</div>
      )}
    </div>
  );
}
