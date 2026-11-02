import { useQuery } from "@tanstack/react-query";
import { getRoomHistory } from "../services/api";

/** Plan, temperature and valve of one room; a new sample arrives every 5 minutes. */
export function useRoomHistory(room: string | null, hours: number) {
  return useQuery({
    queryKey: ["roomHistory", room, hours],
    queryFn: () => getRoomHistory(room!, hours),
    enabled: room != null,
    refetchInterval: 5 * 60_000,
  });
}
