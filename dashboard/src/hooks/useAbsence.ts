import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cancelAbsence, getAbsence, setAbsence } from "../services/api";
import { climateTransferKey } from "./useClimate";
import { roomsKey } from "./useRooms";

export const absenceKey = ["absence"] as const;

/** The backend acts on its own (start, end), so poll every 30 s. */
export function useAbsence() {
  return useQuery({ queryKey: absenceKey, queryFn: getAbsence, refetchInterval: 30_000 });
}

function useAbsenceMutation<T>(fn: (arg: T) => ReturnType<typeof getAbsence>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (state) => {
      queryClient.setQueryData(absenceKey, state);
      queryClient.invalidateQueries({ queryKey: climateTransferKey });
      queryClient.invalidateQueries({ queryKey: roomsKey });
    },
  });
}

export function useSetAbsence() {
  return useAbsenceMutation(setAbsence);
}

export function useCancelAbsence() {
  return useAbsenceMutation<void>(() => cancelAbsence());
}
