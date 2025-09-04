import React, { useEffect, useState } from "react";
import { Link, Outlet, useMatch, useNavigate } from "react-router-dom";
import s from "./GPTLayout.module.css";
import { useAuth } from "../../store/auth.ts";
import { listChats } from "../../lib/api.chats";
import type { ChatSummary } from "../../lib/api.chats";

function NavItem({
  to,
  children,
  end = false,
}: {
  to: string;
  children: React.ReactNode;
  end?: boolean;
}) {
  const match = useMatch({ path: to, end });
  return (
    <Link to={to} className={`${s.navItem} ${match ? s.active : ""}`}>
      {children}
    </Link>
  );
}

function ChatLink({ to, title }: { to: string; title: string }) {
  const match = useMatch({ path: to, end: true });
  return (
    <Link
      to={to}
      className={`${s.navItem} ${match ? s.active : ""}`}
      style={{
        paddingLeft: 20,
        display: "block",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
      }}
      title={title}
    >
      {title}
    </Link>
  );
}

export default function GPTLayout() {
  const { role, token: authToken } = useAuth();
  const token =
    authToken ||
    (typeof window !== "undefined" ? localStorage.getItem("access_token") : null);

  const navigate = useNavigate();
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);

  const loadChats = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await listChats(token);
      setChats(data);
    } catch (e) {
      console.error("listChats error:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadChats();
  }, [token]);

  useEffect(() => {
    const onRefresh = () => loadChats();
    window.addEventListener("chats:refresh", onRefresh as EventListener);
    return () => window.removeEventListener("chats:refresh", onRefresh as EventListener);
  }, [token]);

  const onCreateChat = () => {
    if (creating) return;
    setCreating(true);
    navigate(`/gpt/chat`); // пустой чат (без запроса к бэку)
    setTimeout(() => setCreating(false), 150);
  };

  return (
    <div className={s.shell}>
      <aside className={s.aside}>
        <div className={s.brand}>GPT</div>

        <nav>
          <div className={s.section}>Чаты</div>

          <div
            onClick={onCreateChat}
            className={s.navItem}
            style={{
              paddingLeft: 20,
              cursor: creating ? "not-allowed" : "pointer",
              opacity: creating ? 0.6 : 1,
            }}
            title={creating ? "Открываем…" : "Новый чат"}
          >
            {creating ? "Открываем…" : "Новый чат"}
          </div>

          {/* список показываем только если есть чаты */}
          {chats.length > 0 && (
            <div style={{ maxHeight: 280, overflowY: "auto", marginTop: 6 }}>
              {loading ? (
                <div
                  className={s.navItem}
                  style={{ paddingLeft: 20, color: "#6b7280" }}
                >
                  Загрузка…
                </div>
              ) : (
                chats.map((c) => (
                  <ChatLink key={c.id} to={`/gpt/chat/${c.id}`} title={c.title} />
                ))
              )}
            </div>
          )}

          <div className={s.section}>Анализ документа</div>
          <NavItem to="/gpt/doc" end={false}>
            Анализ документа
          </NavItem>

          {role === "admin" && (
            <>
              <div className={s.section}>RAG</div>
              <NavItem to="/gpt/rag" end={false}>
                RAG
              </NavItem>
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
