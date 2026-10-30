import { useQuery } from "@tanstack/react-query";
import { getDeviceHealth } from "../services/api";

export const deviceHealthKey = ["deviceHealth"] as const;

/** Batteries, reachability, duty cycle; the backend refreshes every 5 min. */
export function useDeviceHealth() {
  return useQuery({ queryKey: deviceHealthKey, queryFn: getDeviceHealth, refetchInterval: 60_000 });
}

/** Rooms whose thermostat has had settings waiting at the CCU for too long:
 * what the app shows as plan may not be what the thermostat runs. */
export function useStuckRooms(): Set<string> {
  const { data } = useDeviceHealth();
  const devices = Array.isArray(data?.devices) ? data.devices : [];
  return new Set(devices.filter((d) => d.kind === "thermostat" && d.config_stuck).map((d) => d.name));
}
