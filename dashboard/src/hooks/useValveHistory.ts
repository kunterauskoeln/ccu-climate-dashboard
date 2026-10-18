import { useQuery } from "@tanstack/react-query";
import { getValveHistory } from "../services/api";

/** Valve history; a new sample arrives every 5 minutes. */
export function useValveHistory(hours: number) {
  return useQuery({
    queryKey: ["valveHistory", hours],
    queryFn: () => getValveHistory(hours),
    refetchInterval: 5 * 60_000,
  });
}
