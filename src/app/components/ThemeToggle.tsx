import React from "react";
import Button from "./Button";
import { useTheme } from "../theme/ThemeProvider";

export default function ThemeToggle() {
    const { theme, toggle } = useTheme();
    return (
        <Button variant="outline" onClick={toggle}>
            {theme === "dark" ? "🌙 Тёмная" : "☀️ Светлая"}
        </Button>
    );
}
