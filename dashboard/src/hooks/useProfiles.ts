import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addBlock,
  clearBlock,
  copyProfile,
  getProfile,
  getProfiles,
} from "../services/api";
import type { ClimateMode, WeekProfile } from "../services/types";

// `mode` undefined means "whatever the system currently runs" (see api.ts) --
// keep it in the key as-is (not normalised) so a switch between explicit
// heating/cooling and "current" doesn't share a cache entry it shouldn't.
export const profilesKey = (room: string, mode?: ClimateMode) =>
  ["profiles", room, mode ?? "active"] as const;
export const profileKey = (room: string, profile: number, mode?: ClimateMode) =>
  ["profiles", room, profile, mode ?? "active"] as const;

export function useProfiles(room: string | undefined, mode?: ClimateMode) {
  return useQuery({
    queryKey: profilesKey(room ?? "", mode),
    queryFn: () => getProfiles(room!, mode),
    enabled: !!room,
  });
}

export function useProfile(
  room: string | undefined, profile: number | undefined, mode?: ClimateMode
) {
  return useQuery({
    queryKey: profileKey(room ?? "", profile ?? 0, mode),
    queryFn: () => getProfile(room!, profile!, mode),
    enabled: !!room && !!profile,
  });
}

/** Every write below returns the updated WeekProfile, so the specific
 * profile's cache entry is updated directly -- the profile *list* (which also
 * carries "active") is just invalidated, it's cheap and rarely the hot path. */
function useProfileWrite<TArgs>(
  room: string, profile: number, mode: ClimateMode | undefined,
  mutationFn: (args: TArgs) => Promise<WeekProfile>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: (week) => {
      queryClient.setQueryData(profileKey(room, profile, mode), week);
      queryClient.invalidateQueries({ queryKey: profilesKey(room, mode) });
    },
  });
}

export function useAddBlock(room: string, profile: number, mode?: ClimateMode) {
  return useProfileWrite(
    room, profile, mode,
    ({ weekday, body }: { weekday: string; body: { start: string; end: string; setpoint: number } }) =>
      addBlock(room, profile, weekday, body, mode),
  );
}

export function useClearBlock(room: string, profile: number, mode?: ClimateMode) {
  return useProfileWrite(
    room, profile, mode,
    ({ weekday, body }: { weekday: string; body: { start: string; end: string } }) =>
      clearBlock(room, profile, weekday, body, mode),
  );
}

export function useCopyProfile(sourceRoom: string, sourceProfile: number, mode?: ClimateMode) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      to_room?: string;
      to_profile: number;
      from_day?: string;
      to_day?: string;
      to_days?: string[];
    }) => copyProfile(sourceRoom, sourceProfile, body, mode),
    onSuccess: (week, body) => {
      const dstRoom = body.to_room || sourceRoom;
      queryClient.setQueryData(profileKey(dstRoom, body.to_profile, mode), week);
      queryClient.invalidateQueries({ queryKey: profilesKey(dstRoom, mode) });
    },
  });
}
