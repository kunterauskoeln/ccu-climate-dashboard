import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getProfileNames, setProfileName } from "../services/api";

export const profileNamesKey = ["profileNames"] as const;

/** Global profile-slot labels ("1".."6" -> name). Shared cache across every
 * component that shows a profile name -- react-query's cache replaces the
 * manual useRef caches that used to be sprinkled through several components. */
export function useProfileNames() {
  return useQuery({
    queryKey: profileNamesKey,
    queryFn: getProfileNames,
    staleTime: 5 * 60_000, // renamed rarely; the mutation below invalidates on change anyway
  });
}

export function useSetProfileName() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ profile, label }: { profile: number; label: string }) =>
      setProfileName(profile, label),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: profileNamesKey });
    },
  });
}
