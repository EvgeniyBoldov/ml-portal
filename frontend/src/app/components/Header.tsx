import React from "react";
import ThemeToggle from "./ThemeToggle.tsx";
import s from "./Header.module.css";
import logoUrl from "../../assets/logo.png"; // помести файл в src/assets/logo.png

export default function Header() {
    return (
        <header className={s.header}>
            <div className={s.brand}>
                <img className={s.logo} src={logoUrl} alt="Logo" />
                <div className={s.title}>ML Portal</div>
            </div>
            <div className={s.right}>
                <ThemeToggle />
            </div>
        </header>
    );
}
