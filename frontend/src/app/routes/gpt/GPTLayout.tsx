import { Outlet, Link, useMatch } from "react-router-dom";
import s from "./GPTLayout.module.css";
import { useAuth } from "../../store/auth.ts";

function NavItem({ to, children }: { to: string; children: React.ReactNode }) {
    const match = useMatch(to);
    return <Link to={to} className={`${s.navItem} ${match ? s.active : ""}`}>{children}</Link>;
}

export default function GPTLayout() {
    const { role } = useAuth();
    return (
        <div className={s.shell}>
            <aside className={s.aside}>
                <div className={s.brand}>GPT</div>
                <nav>
                    <NavItem to="/gpt/chat">💬 Чат</NavItem>
                    <NavItem to="/gpt/doc">📄 Анализ документа</NavItem>
                    {role === "admin" && (
                        <>
                            <div className={s.section}>RAG</div>
                            <NavItem to="/gpt/admin/list">📂 Список</NavItem>
                            <NavItem to="/gpt/admin/add">➕ Добавить</NavItem>
                            <NavItem to="/gpt/admin/delete">❌ Удалить</NavItem>
                        </>
                    )}
                </nav>
            </aside>

            <main className={s.main}>
                <div className={s.panel}>
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
