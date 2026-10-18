import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRoom, listRooms, patchRoom, setApartmentProfile } from "../services/api";
import type { RoomPatch, RoomState } from "../services/types";
import { climateTransferKey } from "./useClimate";

export const roomsKey = ["rooms"] as const;
export const roomKey = (name: string) => ["rooms", name] as const;

/** Room overview: polled (matches the CCU's own ~15s status refresh) and
 * refetched on window focus / bfcache restore, so a stale overview left open
 * in a background tab catches up automatically. */
export function useRooms() {
  return useQuery({
    queryKey: roomsKey,
    queryFn: listRooms,
    refetchInterval: 15_000,
  });
}

export function useRoom(name: string | undefined) {
  return useQuery({
    queryKey: roomKey(name ?? ""),
    queryFn: () => getRoom(name!),
    enabled: !!name,
  });
}

export function usePatchRoom(name: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: RoomPatch) => patchRoom(name!, patch),
    onSuccess: (next: RoomState, patch) => {
      queryClient.setQueryData(roomKey(next.room), next);
      queryClient.invalidateQueries({ queryKey: roomsKey });
      // Picking another profile may start a background transfer (its stored
      // plan is written first, the switch follows) -- start watching it.
      if (patch.active_profile !== undefined) {
        queryClient.invalidateQueries({ queryKey: climateTransferKey });
      }
    },
  });
}

/** "Wohnung": all rooms to one profile. The switch runs in the background;
 * watching the transfer picks up its progress and the final room states. */
export function useSetApartmentProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (profile: number) => setApartmentProfile(profile),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: climateTransferKey });
      queryClient.invalidateQueries({ queryKey: roomsKey });
    },
  });
}
