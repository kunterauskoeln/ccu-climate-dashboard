import React from "react";
import { useNavigate } from "react-router-dom";
import { AppIcon } from "../icons/IconMap";
import { useTheme, AVAILABLE_THEMES, ELEVATION_LEVELS } from "../theme/ThemeContext";
import "../styles/styles.css";

export default function ThemeSettings() {
  const navigate = useNavigate();
  const { theme, setTheme, elevation, setElevation, gloss, setGloss } = useTheme();

  return (
    <div className="room-grid">
      <div className="back-card" onClick={() => navigate("/settings")}> 
        <span className="back-left"><AppIcon name="arrowleft" /></span>
        <span className="back-center">Design</span>
        <span className="back-right"><AppIcon name="themes" /></span>
      </div>

      <div className="room-card">
        <h3 className="card-title">Theme wählen</h3>
        <div className="profile-list-vertical">
          {AVAILABLE_THEMES.map((item) => (
            <button
              key={item.id}
              className={`profile-mini-card-vertical ${theme === item.id ? "active-profile" : ""}`}
              onClick={() => setTheme(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      <div className="room-card">
        <h3 className="card-title">Effekt</h3>
        <div className="setting-name">Erhaben</div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {ELEVATION_LEVELS.map((level) => (
            <button
              key={level.id}
              className={`profile-mini-card-vertical ${elevation === level.id ? "active-profile" : ""}`}
              style={{ flex: 1, textAlign: "center" }}
              onClick={() => setElevation(level.id)}
            >
              {level.label}
            </button>
          ))}
        </div>
        <p className="setting-help">
          Lässt Karten und Schaltflächen plastisch vom Hintergrund abheben: mit Lichtkante,
          Schatten und leichtem Verlauf. Stark wirkt am deutlichsten.
        </p>

        <div className="setting-name">Glanz</div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {[false, true].map((on) => (
            <button
              key={String(on)}
              className={`profile-mini-card-vertical ${gloss === on ? "active-profile" : ""}`}
              style={{ flex: 1, textAlign: "center" }}
              onClick={() => setGloss(on)}
            >
              {on ? "An" : "Aus"}
            </button>
          ))}
        </div>
        <p className="setting-help">
          Legt einen Lichtreflex wie auf Glas über Karten und Schaltflächen. Lässt sich
          mit Erhaben kombinieren.
        </p>
      </div>
    </div>
  );
}
