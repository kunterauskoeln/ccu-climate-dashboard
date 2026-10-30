// Mirrors the backend Pydantic / dataclass response models.
// TODO: generate from /api/openapi.json once the API has settled.

export interface RoomState {
  room: string;
  actual_temperature: number | null;
  set_temperature: number | null;
  humidity: number | null;
  mode_code: number; // 0=AUTO 1=MANU 2=PARTY 3=BOOST
  mode: string;
  active_profile: number | null;
  window_open: boolean;
  boost: boolean;
  cooling: boolean;
  valve: number | null;
  battery_low: boolean;
  voltage: number | null;
  rssi: number | null;
  reachable: boolean;
}

export interface TimeBlock {
  start: string; // "HH:MM"
  end: string;
  setpoint: number;
}

export interface WeekProfile {
  profile: number;
  days: Record<string, TimeBlock[]>; // lowercase weekday -> ordered blocks
}

export interface ProfilesResponse {
  active: number | null;
  profiles: Record<string, WeekProfile>; // "1".."6"
}

export interface DeviceInfo {
  id: string | null;
  name: string | null;
  address: string | null;
  type: string | null;
  interface: string | null;
}

export interface ClimateState {
  cooling: boolean;
  actuator: string | null;
}

export type ClimateMode = "heating" | "cooling";

/** A yearly point in time (day, month, "HH:MM"), local time of the server's SCHEDULE_TZ. */
export interface ClimateSchedulePoint {
  day: number;
  month: number;
  time: string;
  enabled: boolean; // switch automatically at this point
}

/** Scheduled switching between heating and cooling ("Automatisch umschalten"). */
export interface ClimateSchedule {
  heating: ClimateSchedulePoint | null;
  cooling: ClimateSchedulePoint | null;
  next: { at: string; cooling: boolean } | null;
  last_run: {
    at: string;
    due: string;
    cooling: boolean;
    result: "switched" | "already" | "error";
    message: string;
  } | null;
  timezone: string;
}

export interface TransferState {
  running: boolean;
  mode: string | null; // "heating" | "cooling"
  kind: "mode_switch" | "profile_switch" | "restore" | "apartment_switch" | null;
  label: string | null; // profile_switch: "Arbeitszimmer P3"
  started_at: number | null; // epoch seconds, identifies the run
  total: number;
  done: number;
  written: string[];
  deferred: string[];
  errors: string[];
}

export type ProfileNames = Record<string, string>; // profile slot "1".."6" -> label

/** One recorded change (backend change_history), newest first in the list. */
export interface HistoryEntry {
  id: string;
  at: string; // ISO 8601, UTC
  kind: "profile" | "name";
  mode: string | null; // profile entries: "heating" | "cooling"
  room: string | null; // profile entries only
  profile: number;
  summary: string;
}

export interface ApartmentSwitchResult {
  rooms: number; // rooms being switched in this run
  skipped: number; // already on that profile
  deferred: number; // over the per-run budget, tap again
  background: boolean;
}

export interface RestoreResult {
  names: number; // profile names put back right away
  profiles: number; // room profiles being put back
  days: number; // thermostat days written in this run
  deferred: number; // days left for another reset
  background: boolean; // true: being written, see the transfer banner
}

/** Result of POST /import: a check (dry run) or the applied import. */
export interface ImportResult {
  valid: boolean;
  applied: boolean;
  errors: string[];
  warnings: string[];
  rooms: number;
  profiles: number;
  names: number;
  valve_rooms: number;
  // automatic heating/cooling switch: "replace" (file has one), "clear" (file has
  // none set), "keep" (older export without it -- the current one stays)
  schedule: "replace" | "clear" | "keep";
  backup_file: string | null; // copy of the previous state in the data directory
  transfer_started: boolean;
}

export interface RoomPatch {
  setpoint?: number;
  mode?: number;
  active_profile?: number;
  boost?: boolean;
}

/** Dew point monitoring (GET /system/dew-point), refreshed by the backend every 60 s. */
export type DewLevel = "aus" | "ok" | "unbekannt" | "knapp" | "gefahr";
export type DewStatus = DewLevel | "ventil_zu";

export interface DewRoom {
  room: string;
  temperature: number | null;
  humidity: number | null;
  dew_point: number | null;
  valve: number | null;
  margin: number | null; // effective flow temperature minus dew point, K
  status: DewStatus;
}

export interface DewFlow {
  configured: boolean;
  connection: string; // aus | verbinde | verbunden | Fehler: …
  topic: string;
  value: number | null;
  received_at: number | null; // epoch seconds
  stale: boolean;
  effective: number | null;
  source: "live" | "last_valid" | null;
  last_valid: number | null;
  last_valid_at: number | null;
  flowing_since: number | null;
}

export interface DewPointSnapshot {
  at: number | null;
  cooling: boolean | null;
  level: DewLevel;
  message: string;
  warn_margin: number;
  alarm_margin: number;
  flow: DewFlow;
  rooms: DewRoom[];
}

/** Stored backups (GET /backups): nightly ones and the copies imports leave. */
export interface BackupFile {
  name: string;
  kind: "auto" | "vor-import";
  size: number; // bytes
  modified: number; // epoch seconds
}

export interface BackupList {
  files: BackupFile[];
  hour: number; // automatic backup after this hour (local time)
  keep: number; // number of automatic backups kept
  last_error: string | null;
}

/** Device health (GET /system/device-health), refreshed by the backend every 5 min. */
export interface DeviceHealthState {
  name: string;
  address: string;
  kind: "thermostat" | "aktor";
  reachable: boolean | null; // null: could not be read
  low_battery: boolean | null; // null: no battery
  voltage: number | null;
  rssi: number | null;
  duty_cycle: boolean; // the device hit its own airtime limit
  config_pending: boolean; // CCU still has settings to hand over (briefly normal after a write)
  config_pending_since?: number | null; // epoch s, first seen pending
  config_stuck?: boolean; // pending longer than the warn limit (30 min)
}

export interface DeviceHealth {
  at: number;
  ccu_duty_cycle: number | null; // percent of the legal airtime
  level: "ok" | "warnung";
  message: string;
  problems: string[];
  devices: DeviceHealthState[];
}

/** Absence (GET/PUT/DELETE /system/absence): all rooms on one profile, then back. */
export interface AbsenceState {
  phase: "aus" | "geplant" | "aktiv" | "rueckkehr" | "beendet" | "abgebrochen";
  profile: number | null;
  profile_name: string | null;
  start: string | null; // ISO with offset
  end: string | null;
  previous: Record<string, number>; // room -> profile before the absence
  applied: boolean;
  message: string;
}

/** Valve history (GET /system/valve-history): one column per room, percent. */
export interface ValveHistory {
  times: number[]; // epoch seconds, every 5 minutes
  rooms: Record<string, (number | null)[]>; // null: recording paused
}
