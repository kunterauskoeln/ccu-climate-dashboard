import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useDewPoint } from "../hooks/useDewPoint";

/** App-wide warning while cooling brings a room's floor close to the dew point.
 * Not dismissable: it disappears on its own once the margin is back. */
export default function DewPointBanner() {
  const navigate = useNavigate();
  const location = useLocation();
  const { data } = useDewPoint();

  // sits outside every page: unexpected data must never take the app down
  if (!data || (data.level !== "knapp" && data.level !== "gefahr")) return null;
  const onPage = location.pathname === "/settings/dew-point";

  return (
    <div
      className={`transfer-banner dew-banner dew-banner-${data.level}`}
      role="alert"
      onClick={onPage ? undefined : () => navigate("/settings/dew-point")}
      style={{ cursor: onPage ? "default" : "pointer" }}
    >
      <div className="transfer-row">
        <span>{data.message}</span>
        {!onPage && <span className="transfer-detail">Details</span>}
      </div>
    </div>
  );
}
