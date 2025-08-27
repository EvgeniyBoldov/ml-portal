import { FormEvent, useState } from "react";
import { login, me } from "../lib/api";
import { useAuth } from "../store/auth";
import { useNavigate, useLocation } from "react-router-dom";
import Button from "../components/Button";
import s from "./Login.module.css";

export default function Login() {
    const [u, setU] = useState("");
    const [p, setP] = useState("");
    const [err, setErr] = useState("");
    const setAuth = useAuth(s => s.setAuth);
    const nav = useNavigate();
    const loc = useLocation();

    async function onSubmit(e: FormEvent) {
        e.preventDefault(); setErr("");
        try {
            const { access_token } = await login(u, p);
            const { role } = await me(access_token);
            setAuth(access_token, role);
            nav((loc.state as any)?.from?.pathname || "/gpt", { replace: true });
        } catch (e:any) { setErr(e.message || "Ошибка входа"); }
    }

    return (
        <div className={s.wrap}>
            <form onSubmit={onSubmit} className={s.card}>
                <h1 className={s.title}>Вход</h1>
                <div className={s.row}>
                    <input className={s.field} placeholder="username" value={u} onChange={e=>setU(e.target.value)} />
                </div>
                <div className={s.row}>
                    <input className={s.field} type="password" placeholder="password" value={p} onChange={e=>setP(e.target.value)} />
                </div>
                {err && <div className={s.error}>{err}</div>}
                <Button className="mt-3" block>Войти</Button>
                <div className={s.hint}>demo: admin/admin или user/user</div>
            </form>
        </div>
    );
}
