import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  continueClimateTransfer, getClimate, getClimateSchedule, getClimateTransfer, setClimate,
  setClimateSchedule,
} from "../services/api";

export const climateKey = ["climate"] as const;
export const climateTransferKey = ["climateTransfer"] as const;
export const climateScheduleKey = ["climateSchedule"] as const;

export function useClimate() {
  return useQuery({ queryKey: climateKey, queryFn: getClimate });
}

/** Background profile-transfer progress (see backend profile_transfer.py).
 * Polls every 2s only while a transfer is running -- picks up one already in
 * flight on mount, and keeps polling after a switch via the invalidate in
 * useSetClimate below. */
export function useClimateTransfer() {
  return useQuery({
    queryKey: climateTransferKey,
    queryFn: getClimateTransfer,
    refetchInterval: (query) => (query.state.data?.running ? 2000 : false),
  });
}

export function useSetClimate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (cooling: boolean) => setClimate(cooling),
    onSuccess: (state) => {
      queryClient.setQueryData(climateKey, state);
      // the switch just kicked off a background transfer -- refetch its
      // status now so the dynamic refetchInterval above picks it up
      queryClient.invalidateQueries({ queryKey: climateTransferKey });
    },
  });
}

/** "Jetzt übertragen": run the transfer again for the days still outstanding. */
export function useContinueTransfer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: continueClimateTransfer,
    onSuccess: (state) => {
      queryClient.setQueryData(climateTransferKey, state);
      queryClient.invalidateQueries({ queryKey: climateTransferKey });
    },
  });
}

/** Scheduled heating/cooling switch. Refetched every minute: an automatic
 * switch changes "next" and "last_run" (and the mode itself). */
export function useClimateSchedule() {
  return useQuery({
    queryKey: climateScheduleKey,
    queryFn: getClimateSchedule,
    refetchInterval: 60_000,
  });
}

export function useSetClimateSchedule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: setClimateSchedule,
    onSuccess: (state) => {
      queryClient.setQueryData(climateScheduleKey, state);
    },
  });
}
