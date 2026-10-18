// Werte der Zeit-/Temperatur-Wheels (TimeBlockAdd, TimeBlockDetail).
// Modulweit statt pro Render, damit sie als stabile Effekt-Abhängigkeiten taugen.
export const hours = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0"));
export const minutes = ["00", "05", "10", "15", "20", "25", "30", "35", "40", "45", "50", "55"];
export const temperatures = Array.from({ length: 31 }, (_, i) => (15 + i * 0.5).toFixed(1));
