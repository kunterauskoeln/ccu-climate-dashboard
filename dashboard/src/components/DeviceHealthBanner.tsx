import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useDeviceHealth } from "../hooks/useDeviceHealth";

/** App-wide notice for weak batteries, unreachable devices or a busy radio.
 * Disappears on its own once the problem is gone. */
export default function DeviceHealthBanner() {
  const navigate = useNavigate();
  const location = useLocation();
  const { data } = useDeviceHealth();

  // sits outside every page: unexpected data must never take the app down
  if (!data || data.level !== "warnung" || !Array.isArray(data.problems)) return null;
  const onPage = location.pathname === "/settings/devices";

  return (
    <div
      className="transfer-banner dew-banner dew-banner-knapp"
      role="status"
      onClick={onPage ? undefined : () => navigate("/settings/devices")}
      style={{ cursor: onPage ? "default" : "pointer" }}
    >
      <div className="transfer-row">
        <span>{data.message}</span>
        {!onPage && <span className="transfer-detail">Details</span>}
      </div>
    </div>
  );
}
