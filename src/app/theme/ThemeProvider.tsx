import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

type Theme = "light" | "dark";
type Ctx = { theme: Theme; toggle: () => void; set: (t: Theme) => void; };

const ThemeContext = createContext<Ctx | null>(null);
const THEME_KEY = "theme";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
    const [theme, setTheme] = useState<Theme>(() => {
        const fromStorage = localStorage.getItem(THEME_KEY) as Theme | null;
        if (fromStorage) return fromStorage;
        // авто: если системная тёмная — возьмём её по умолчанию
        const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)")?.matches;
        return prefersDark ? "dark" : "light";
    });

    useEffect(() => {
        const root = document.documentElement;
        if (theme === "dark") root.classList.add("dark");
        else root.classList.remove("dark");
        localStorage.setItem(THEME_KEY, theme);
    }, [theme]);

    const value = useMemo<Ctx>(() => ({
        theme,
        toggle: () => setTheme(prev => (prev === "dark" ? "light" : "dark")),
        set: (t) => setTheme(t),
    }), [theme]);

    return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
    const ctx = useContext(ThemeContext);
    if (!ctx) throw new Error("useTheme must be used inside ThemeProvider");
    return ctx;
}
