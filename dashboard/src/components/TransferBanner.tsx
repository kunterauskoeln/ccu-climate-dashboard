import React, { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiErrorMessage } from "../services/api";
import { roomsKey } from "../hooks/useRooms";
import { historyKey } from "../hooks/useHistory";
import { useClimateTransfer, useContinueTransfer } from "../hooks/useClimate";

const DISMISS_KEY = "transferBannerDismissed";

// per-viewer convenience only; storage can be unavailable
function readDismissed(): string {
  try {
    return localStorage.getItem(DISMISS_KEY) ?? "";
  } catch {
    return "";
  }
}

/** App-wide notice for the background profile transfer: progress while it runs,
 * and afterwards whatever is still open (deferred days, errors) until dismissed. */
export default function TransferBanner() {
  const queryClient = useQueryClient();
  const { data: transfer } = useClimateTransfer();
  const continueTransfer = useContinueTransfer();
  const wasRunning = useRef(false);
  const [dismissed, setDismissed] = useState(readDismissed);

  // A finished transfer changed what the thermostats hold (and, for a profile
  // switch, which profile is active): refresh everything that shows it.
  useEffect(() => {
    if (!transfer) return;
    if (wasRunning.current && !transfer.running) {
      queryClient.invalidateQueries({ queryKey: roomsKey });
      queryClient.invalidateQueries({ queryKey: ["profiles"] });
      // a finished reset removes its history entries
      queryClient.invalidateQueries({ queryKey: historyKey });
    }
    wasRunning.current = transfer.running;
  }, [transfer, queryClient]);

  // The banner sits outside every page: unexpected data must never take the app down.
  if (!transfer || !Array.isArray(transfer.errors) || !Array.isArray(transfer.deferred)) return null;

  if (transfer.running) {
    const text = transfer.kind === "profile_switch"
      ? `Wechsel auf ${transfer.label}: Plan wird übertragen`
      : transfer.kind === "restore"
      ? "Änderungen werden zurückgesetzt"
      : transfer.kind === "apartment_switch"
      ? `${transfer.label}: Räume werden umgeschaltet`
      : transfer.total > 0
      ? "Pläne werden übertragen"
      : "Pläne werden geprüft";
    const percent = transfer.total > 0 ? (transfer.done / transfer.total) * 100 : 0;
    return (
      <div className="transfer-banner" role="status">
        <div className="transfer-row">
          <span>
            {text}
            {transfer.total > 0 && ` · ${transfer.done}/${transfer.total}`}
          </span>
        </div>
        {transfer.total > 0 && (
          <div className="transfer-track">
            <div className="transfer-fill" style={{ width: `${percent}%` }} />
          </div>
        )}
      </div>
    );
  }

  const hasErrors = transfer.errors.length > 0;
  const hasDeferred = transfer.deferred.length > 0;
  // a run is identified by its start time; a new run shows its result again
  const signature = `${transfer.started_at}|${transfer.deferred.length}|${transfer.errors.length}`;
  const dismiss = () => {
    setDismissed(signature);
    try {
      localStorage.setItem(DISMISS_KEY, signature);
    } catch {
      /* not persisted */
    }
  };
  if ((!hasErrors && !hasDeferred) || dismissed === signature) return null;

  return (
    <div className={`transfer-banner ${hasErrors ? "has-error" : ""}`} role="status">
      <div className="transfer-row">
        <span>
          {hasErrors
            ? `${transfer.errors.length} Fehler bei der Übertragung`
            : `${transfer.deferred.length} Profil-Tag(e) stehen noch aus`}
        </span>
        <button
          className="transfer-close"
          aria-label="Hinweis schließen"
          onClick={dismiss}
        >
          ×
        </button>
      </div>
      {hasErrors && (
        <div className="transfer-detail">
          {transfer.errors.slice(0, 3).map((message, i) => (
            <div key={i}>{message}</div>
          ))}
        </div>
      )}
      {hasDeferred && (
        <div className="transfer-row">
          <span className="transfer-detail">
            {hasErrors ? "Zusätzlich offen: " : ""}
            {transfer.kind === "restore"
              ? `${transfer.deferred.length} Profil-Tag(e) noch offen – in der Änderungshistorie erneut zurücksetzen.`
              : transfer.kind === "apartment_switch"
              ? `${transfer.deferred.length} Raum/Räume noch nicht umgeschaltet – unter Heizprofile → Wohnung erneut tippen.`
              : `${transfer.deferred.length} Profil-Tag(e) folgen beim nächsten Wechsel.`}
          </span>
          {transfer.kind === "mode_switch" && (
            <button
              className="transfer-action"
              disabled={continueTransfer.isPending}
              onClick={() => continueTransfer.mutate()}
            >
              Jetzt übertragen
            </button>
          )}
        </div>
      )}
      {continueTransfer.isError && (
        <div className="transfer-detail">{apiErrorMessage(continueTransfer.error)}</div>
      )}
    </div>
  );
}
