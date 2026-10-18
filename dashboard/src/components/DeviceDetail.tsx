import React from "react";
import { useNavigate, useParams } from "react-router-dom";

export default function DeviceDetail() {
  const navigate = useNavigate();
  const { deviceId } = useParams();

  return (
    <div style={{ padding: "1rem" }}>
      <button onClick={() => navigate("/settings/devices")}>←</button>
      <h2>Gerät: {deviceId}</h2>
      <p>Hier kommen später die Gerätedetails hin.</p>
    </div>
  );
}
