import { Outlet, Link, useLocation, Navigate, useMatch } from "react-router-dom";
import { useAuth } from "../../store/auth";
import ThemeToggle from "../../components/ThemeToggle";
import s from "./GPTLayout.module.css";

function NavItem({ to, children }: { to: string; children: React.ReactNode }) {
    const match = useMatch(to);
    return (
        <Link to={to} className={`${s.navItem} ${match ? s.active : ""}`}>{children}</Link>
    );
}

export default function GPTLayout() {
    const { token, role } = useAuth();
    const loc = useLocation();
    if (!token) return <Navigate to="/login" state={{ from: loc }} replace />;

    return (
        <div className={s.shell}>
            <aside className={s.aside}>
                <div className={s.brand}>РТК-ЦОД • GPT</div>
                <nav>
                    <NavItem to="/gpt/chat">💬 Чат</NavItem>
                    <NavItem to="/gpt/doc">📄 Анализ документа</NavItem>
                    {role==="admin" && (
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
                <header className={s.header}>
                    <h1>Панель</h1>
                    <div style={{ display:"flex", gap: 12, alignItems:"center" }}>
                        <span className={s.role}>Роль: {role}</span>
                        <ThemeToggle />
                    </div>
                </header>

                <div className={s.panel}>
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
