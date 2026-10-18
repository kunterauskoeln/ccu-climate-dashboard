import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getHistory, restoreHistory } from "../services/api";
import { climateTransferKey } from "./useClimate";
import { profileNamesKey } from "./useProfileNames";

export const historyKey = ["history"] as const;

/** Recorded changes, newest first. Always refetched when the page opens --
 * edits elsewhere in the app add entries without touching this cache. */
export function useHistory() {
  return useQuery({ queryKey: historyKey, queryFn: getHistory, staleTime: 0 });
}

export function useRestoreHistory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => restoreHistory(id),
    onSuccess: () => {
      // names are back right away; profiles follow in the background
      queryClient.invalidateQueries({ queryKey: historyKey });
      queryClient.invalidateQueries({ queryKey: profileNamesKey });
      queryClient.invalidateQueries({ queryKey: ["profiles"] });
      queryClient.invalidateQueries({ queryKey: climateTransferKey });
    },
  });
}
