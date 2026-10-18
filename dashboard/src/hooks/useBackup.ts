import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { backupNow, importData, listBackups } from "../services/api";
import { climateScheduleKey, climateTransferKey } from "./useClimate";
import { historyKey } from "./useHistory";
import { profileNamesKey } from "./useProfileNames";
import { roomsKey } from "./useRooms";

export const backupsKey = ["backups"] as const;

export function useBackups() {
  return useQuery({ queryKey: backupsKey, queryFn: listBackups, staleTime: 0 });
}

export function useBackupNow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: backupNow,
    onSuccess: (list) => queryClient.setQueryData(backupsKey, list),
  });
}

/** Check (apply=false) or import an export file. An applied import replaces
 * profiles, names and the valve mapping and clears the history. */
export function useImportData() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ doc, apply }: { doc: unknown; apply: boolean }) => importData(doc, apply),
    onSuccess: (result) => {
      if (!result.applied) return;
      queryClient.invalidateQueries({ queryKey: profileNamesKey });
      queryClient.invalidateQueries({ queryKey: ["profiles"] });
      queryClient.invalidateQueries({ queryKey: historyKey });
      queryClient.invalidateQueries({ queryKey: roomsKey });
      queryClient.invalidateQueries({ queryKey: climateTransferKey });
      queryClient.invalidateQueries({ queryKey: climateScheduleKey });
      queryClient.invalidateQueries({ queryKey: backupsKey }); // new vor-import copy
    },
  });
}
