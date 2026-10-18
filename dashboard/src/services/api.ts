import axios from "axios";
import type {
  AbsenceState,
  ClimateMode,
  ClimateSchedule,
  ClimateSchedulePoint,
  ApartmentSwitchResult,
  BackupList,
  ClimateState,
  DeviceHealth,
  DeviceInfo,
  DewPointSnapshot,
  HistoryEntry,
  ProfileNames,
  ProfilesResponse,
  ImportResult,
  RestoreResult,
  RoomPatch,
  RoomState,
  ValveHistory,
  TransferState,
  WeekProfile,
} from "./types";

// Same-origin by default (nginx proxies /api -> backend).
// For local dev against a directly-run backend: VITE_API_URL=http://localhost:8000
const http = axios.create({ baseURL: import.meta.env.VITE_API_URL ?? "/api" });

const room = (name: string) => encodeURIComponent(name);
const day = (d: string) => d.toUpperCase();

/** Human-readable message from an axios error (backend {error:{message}} / FastAPI detail). */
export function apiErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { error?: { message?: string }; detail?: unknown } | undefined;
    const detail = data?.detail;
    return (
      data?.error?.message ||
      (Array.isArray(detail)
        ? (detail[0] as { msg?: string } | undefined)?.msg
        : typeof detail === "string"
        ? detail
        : null) ||
      err.message ||
      "Unbekannter Fehler"
    );
  }
  if (err instanceof Error) return err.message;
  return "Unbekannter Fehler";
}

/** Logs an API error to the console with whatever detail axios gives us. */
export function logApiError(context: string, err: unknown): void {
  if (axios.isAxiosError(err)) {
    console.error(context, err.response?.status, err.response?.data ?? err.message);
  } else {
    console.error(context, err);
  }
}

// ---- rooms ----
export async function listRooms(): Promise<RoomState[]> {
  return (await http.get("/rooms")).data;
}

export async function getRoom(name: string): Promise<RoomState> {
  return (await http.get(`/rooms/${room(name)}`)).data;
}

export async function patchRoom(name: string, patch: RoomPatch): Promise<RoomState> {
  return (await http.patch(`/rooms/${room(name)}`, patch)).data;
}

// ---- profiles ----
// `mode` is Phase 2b.2: omitted, every call below behaves exactly as before
// (whatever the system currently runs, on the real device). Passed
// explicitly as the *inactive* mode, it reads/writes that mode's stored
// schedule directly instead -- no CCU round-trip, near-instant.
export async function getProfiles(name: string, mode?: ClimateMode): Promise<ProfilesResponse> {
  return (await http.get(`/rooms/${room(name)}/profiles`, { params: { mode } })).data;
}

export async function getProfile(
  name: string, profile: number, mode?: ClimateMode
): Promise<WeekProfile> {
  return (await http.get(`/rooms/${room(name)}/profiles/${profile}`, { params: { mode } })).data;
}

export async function addBlock(
  name: string,
  profile: number,
  weekday: string,
  body: { start: string; end: string; setpoint: number },
  mode?: ClimateMode
): Promise<WeekProfile> {
  return (
    await http.post(
      `/rooms/${room(name)}/profiles/${profile}/days/${day(weekday)}/blocks`, body,
      { params: { mode } }
    )
  ).data;
}

export async function copyProfile(
  sourceRoom: string,
  sourceProfile: number,
  body: {
    to_room?: string;
    to_profile: number;
    from_day?: string;
    to_day?: string;
    to_days?: string[];
  },
  mode?: ClimateMode
): Promise<WeekProfile> {
  return (
    await http.post(
      `/rooms/${room(sourceRoom)}/profiles/${sourceProfile}/copy`, body, { params: { mode } }
    )
  ).data;
}

export async function clearBlock(
  name: string,
  profile: number,
  weekday: string,
  body: { start: string; end: string },
  mode?: ClimateMode
): Promise<WeekProfile> {
  return (
    await http.delete(`/rooms/${room(name)}/profiles/${profile}/days/${day(weekday)}/blocks`, {
      data: body,
      params: { mode },
    })
  ).data;
}

// ---- devices / meta ----
export async function listDevices(): Promise<DeviceInfo[]> {
  return (await http.get("/devices")).data;
}

export async function getProfileNames(): Promise<ProfileNames> {
  return (await http.get("/profile-names")).data;
}

export async function setProfileName(profile: number, label: string) {
  return (await http.put(`/profile-names/${profile}`, { name: label })).data;
}

export async function getClimate(): Promise<ClimateState> {
  return (await http.get("/system/climate")).data;
}

export async function setClimate(cooling: boolean): Promise<ClimateState> {
  return (await http.patch("/system/climate", { cooling })).data;
}

export async function getClimateSchedule(): Promise<ClimateSchedule> {
  return (await http.get("/system/climate/schedule")).data;
}

export async function setClimateSchedule(schedule: {
  heating: ClimateSchedulePoint;
  cooling: ClimateSchedulePoint;
}): Promise<ClimateSchedule> {
  return (await http.put("/system/climate/schedule", schedule)).data;
}

/** Switch every room to one profile slot ("Wohnung"), room by room in the background. */
export async function setApartmentProfile(profile: number): Promise<ApartmentSwitchResult> {
  return (await http.post("/system/active-profile", { profile })).data;
}

export async function getClimateTransfer(): Promise<TransferState> {
  return (await http.get("/system/climate/transfer")).data;
}

/** Re-run the transfer for the current mode (writes the days a mode switch had to defer). */
export async function continueClimateTransfer(): Promise<TransferState> {
  return (await http.post("/system/climate/transfer")).data;
}

// ---- change history ----
export async function getHistory(): Promise<HistoryEntry[]> {
  return (await http.get("/history")).data;
}

/** Undo this change and every newer one. */
export async function restoreHistory(id: string): Promise<RestoreResult> {
  return (await http.post(`/history/${encodeURIComponent(id)}/restore`)).data;
}

// ---- backup ----
/** Everything the app stores, as a downloadable JSON file (no CCU credentials). */
export async function exportData(): Promise<{ blob: Blob; filename: string }> {
  const response = await http.get("/export", { responseType: "blob" });
  const disposition = String(response.headers["content-disposition"] ?? "");
  const match = /filename="([^"]+)"/.exec(disposition);
  return { blob: response.data, filename: match?.[1] ?? "ccu-export.json" };
}

export async function listBackups(): Promise<BackupList> {
  return (await http.get("/backups")).data;
}

/** Write today's automatic backup right away. */
export async function backupNow(): Promise<BackupList> {
  return (await http.post("/backups")).data;
}

export async function downloadBackup(name: string): Promise<Blob> {
  return (await http.get(`/backups/${encodeURIComponent(name)}`, { responseType: "blob" })).data;
}

/** A stored backup as parsed JSON (for "Einspielen…"). */
export async function fetchBackup(name: string): Promise<unknown> {
  return (await http.get(`/backups/${encodeURIComponent(name)}`)).data;
}

/** Check an export file (apply=false, changes nothing) or import it. */
export async function importData(doc: unknown, apply: boolean): Promise<ImportResult> {
  return (await http.post("/import", doc, { params: { apply } })).data;
}

// ---- dew point ----
export async function getDewPoint(): Promise<DewPointSnapshot> {
  return (await http.get("/system/dew-point")).data;
}

// ---- device health ----
export async function getDeviceHealth(): Promise<DeviceHealth> {
  return (await http.get("/system/device-health")).data;
}

// ---- absence ----
export async function getAbsence(): Promise<AbsenceState> {
  return (await http.get("/system/absence")).data;
}

/** Plan an absence or change the running one. Times as "YYYY-MM-DDTHH:MM" local time;
 * start null = now. */
export async function setAbsence(body: {
  profile: number;
  start: string | null;
  end: string;
}): Promise<AbsenceState> {
  return (await http.put("/system/absence", body)).data;
}

export async function cancelAbsence(): Promise<AbsenceState> {
  return (await http.delete("/system/absence")).data;
}

// ---- valve history ----
export async function getValveHistory(hours: number): Promise<ValveHistory> {
  return (await http.get("/system/valve-history", { params: { hours } })).data;
}
