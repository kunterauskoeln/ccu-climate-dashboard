import React from "react";
import { useNavigate } from "react-router-dom";
import "../styles/styles.css";
import { AppIcon, getIcon } from "../icons/IconMap";
import { useDevices } from "../hooks/useDevices";
import { useDeviceHealth } from "../hooks/useDeviceHealth";
import type { DeviceHealthState } from "../services/types";

function healthLine(h: DeviceHealthState): string {
  const parts: string[] = [];
  if (h.voltage != null) parts.push(`Batterie ${h.voltage.toFixed(1).replace(".", ",")} V`);
  if (h.rssi != null) parts.push(`Signal ${h.rssi} dBm`);
  if (h.config_pending) parts.push("Konfiguration ausstehend");
  return parts.join(" · ");
}

function healthProblems(h: DeviceHealthState): string[] {
  const out: string[] = [];
  if (h.reachable === null) out.push("Zustand nicht lesbar");
  else if (!h.reachable) out.push("nicht erreichbar");
  if (h.low_battery) out.push("Batterie schwach");
  if (h.duty_cycle) out.push("Funk-Limit erreicht");
  return out;
}

export default function Devices() {
  const navigate = useNavigate();
  const { data: devices = [] } = useDevices();
  const { data: health } = useDeviceHealth();
  const byAddress = new Map((health?.devices ?? []).map((d) => [d.address, d]));

  return (
    <div>
      <div className="room-grid equal-height">
        <div className="back-card" onClick={() => navigate("/settings")} style={{ cursor: "pointer" }}>
          <span className="back-left"><AppIcon name="arrowleft" /></span>
          <span className="back-center">Geräte</span>
          <span className="back-right"><AppIcon name="devices" /></span>
        </div>
        {health && (
          <div className={`room-card card-wide ${health.level === "warnung" ? "dew-border-knapp" : ""}`}
               style={{ gap: "0.4rem" }}>
            <div className="setting-name">
              {health.level === "warnung" ? "Hinweise" : "Alle Geräte in Ordnung"}
            </div>
            {health.problems.length > 0 && (
              <ul className="backup-list">
                {health.problems.map((p) => <li key={p}>{p}</li>)}
              </ul>
            )}
            <div className="room-subtitle">
              Funkauslastung der CCU:{" "}
              {health.ccu_duty_cycle == null ? "unbekannt" : `${health.ccu_duty_cycle} %`}
              {" "}(ab 70 % hält die App Profilübertragungen an, bei 100 % sendet die CCU nichts mehr)
            </div>
          </div>
        )}
      </div>

      <div className="room-grid equal-height uniform-rows" style={{ paddingTop: 0 }}>
        {devices.map((dev) => {
          const h = dev.address ? byAddress.get(dev.address) : undefined;
          const problems = h ? healthProblems(h) : [];
          return (
            <div
              key={dev.id ?? dev.address}
              className={`room-card ${problems.length ? "dew-border-knapp" : ""}`}
              onClick={() => navigate(`/settings/devices/${dev.id ?? ""}`)}
              style={{ cursor: "pointer" }}
            >
              <div className="room-header-left">
                <span className="room-icon">{getIcon((dev.type ?? "").toLowerCase())}</span>
                <span className="room-name">{dev.name}</span>
              </div>

              <div className="room-subtitle">{dev.type}</div>
              {h && healthLine(h) && <div className="room-subtitle">{healthLine(h)}</div>}
              {problems.length > 0 && (
                <div className="validation-error" style={{ textAlign: "left", marginTop: 0 }}>
                  {problems.join(" · ")}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
