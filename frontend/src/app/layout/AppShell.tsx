import React from "react";
import { Outlet } from "react-router-dom";
import Header from "../components/Header.tsx";
import s from "./AppShell.module.css";

export default function AppShell() {
    return (
        <div className={s.shell}>
            <Header />
            <div className={s.content}>
                <Outlet />
            </div>
        </div>
    );
}
