import React from "react";
import { useAuth } from "../store/auth.ts";
import GPTLayout from "./gpt/GPTLayout.tsx";
import Login from "./Login.tsx";

/** Показывает Login если нет токена, иначе — GPTLayout */
export default function GPTGate() {
    const { token } = useAuth();
    if (!token) return <Login />;
    return <GPTLayout />;
}
