import React from "react";

export default function BusyOverlay({
  text,
  sub,
}: {
  text: string;
  sub?: string;
}) {
  return (
    <div className="busy-overlay">
      <div className="spinner" />
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "0.3rem",
        }}
      >
        <span>{text}</span>
        {sub && (
          <span style={{ fontWeight: 400, fontSize: "0.9rem", opacity: 0.85 }}>
            {sub}
          </span>
        )}
      </div>
    </div>
  );
}
