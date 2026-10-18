import type { DewStatus } from "../services/types";

export const DEW_STATUS_LABEL: Record<DewStatus, string> = {
  ok: "ok",
  knapp: "knapp",
  gefahr: "Kondensgefahr",
  unbekannt: "unbekannt",
  ventil_zu: "Ventil zu",
  aus: "Heizbetrieb",
};

/** "17,6 °C" / "+1,9 K" with a German decimal comma; "–" for missing values. */
export function formatCelsius(value: number | null | undefined): string {
  return value == null ? "–" : `${value.toFixed(1).replace(".", ",")} °C`;
}

export function formatKelvin(value: number | null | undefined): string {
  if (value == null) return "–";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1).replace(".", ",")} K`;
}

/** "vor 3 min" / "vor 2 h" for an epoch-seconds timestamp. */
export function formatAge(epochSeconds: number | null | undefined, now = Date.now()): string {
  if (epochSeconds == null) return "nie";
  const minutes = Math.max(0, Math.round((now / 1000 - epochSeconds) / 60));
  if (minutes < 1) return "gerade eben";
  if (minutes < 120) return `vor ${minutes} min`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `vor ${hours} h` : `vor ${Math.round(hours / 24)} Tagen`;
}
