import { useQuery } from "@tanstack/react-query";
import { getDewPoint } from "../services/api";

export const dewPointKey = ["dewPoint"] as const;

/** Dew point snapshot; the backend refreshes it every 60 s, so poll at that pace. */
export function useDewPoint() {
  return useQuery({ queryKey: dewPointKey, queryFn: getDewPoint, refetchInterval: 60_000 });
}
