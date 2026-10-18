import { useQuery } from "@tanstack/react-query";
import { getDeviceHealth } from "../services/api";

export const deviceHealthKey = ["deviceHealth"] as const;

/** Batteries, reachability, duty cycle; the backend refreshes every 5 min. */
export function useDeviceHealth() {
  return useQuery({ queryKey: deviceHealthKey, queryFn: getDeviceHealth, refetchInterval: 60_000 });
}
