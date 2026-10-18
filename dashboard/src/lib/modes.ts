// Display labels for the room control mode (RoomState.mode_code).
export const MODE_LABELS: Record<number, string> = {
  0: "Automatik",
  1: "Manuell",
  2: "Urlaub",
  3: "Boost",
};

export const modeLabel = (code: number, fallback = "?"): string =>
  MODE_LABELS[code] ?? fallback;
