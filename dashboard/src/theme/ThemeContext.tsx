import React, { createContext, useContext, useEffect, useState } from "react";

export type ThemeMode =
  | "light" | "dark" | "sepia"
  | "wald" | "sonne" | "graphit" | "ozean";

export const AVAILABLE_THEMES: Array<{ id: ThemeMode; label: string }> = [
  { id: "light", label: "Hellblau" },
  { id: "dark", label: "Dunkel" },
  { id: "sepia", label: "Sepia" },
  { id: "wald", label: "Wald" },
  { id: "sonne", label: "Sonnenuntergang" },
  { id: "graphit", label: "Graphit" },
  { id: "ozean", label: "Ozean" }
];

export type Elevation = "off" | "light" | "strong";

export const ELEVATION_LEVELS: Array<{ id: Elevation; label: string }> = [
  { id: "off", label: "Aus" },
  { id: "light", label: "Leicht" },
  { id: "strong", label: "Stark" }
];

type ThemeContextType = {
  theme: ThemeMode;
  availableThemes: typeof AVAILABLE_THEMES;
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;
  elevation: Elevation;
  setElevation: (level: Elevation) => void;
};

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

// localStorage can be unavailable (private window, blocked site data).
function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function initialTheme(): ThemeMode {
  const stored = readStorage("theme");
  return AVAILABLE_THEMES.find((item) => item.id === stored)?.id ?? "light";
}

function initialElevation(): Elevation {
  const stored = readStorage("elevation");
  const level = ELEVATION_LEVELS.find((item) => item.id === stored)?.id;
  if (level) return level;
  // Before the three levels there was a single on/off "elevated" switch.
  return readStorage("elevated") === "true" ? "light" : "off";
}

export function ThemeProvider({ children }: { children?: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemeMode>(initialTheme);
  const [elevation, setElevation] = useState<Elevation>(initialElevation);

  useEffect(() => {
    const classList = document.documentElement.classList;
    classList.remove(...AVAILABLE_THEMES.map((item) => `theme-${item.id}`));
    classList.remove(...ELEVATION_LEVELS.map((item) => `elev-${item.id}`));
    classList.add(`theme-${theme}`, `elev-${elevation}`);
    try {
      localStorage.setItem("theme", theme);
      localStorage.setItem("elevation", elevation);
    } catch {
      /* per-viewer convenience only */
    }
  }, [theme, elevation]);

  const toggleTheme = () =>
    setThemeState((current) => (current === "dark" ? "light" : "dark"));

  return (
    <ThemeContext.Provider
      value={{
        theme,
        availableThemes: AVAILABLE_THEMES,
        setTheme: setThemeState,
        toggleTheme,
        elevation,
        setElevation
      }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}
