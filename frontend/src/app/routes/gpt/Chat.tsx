import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { sendNewChat, sendToChatStream, sendToChat } from "../../lib/api.chats";
import type { ChatMessage, ChatSendRequest } from "../../lib/api.chats";

/** компактный слайдер-переключатель без внешних зависимостей */
function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        background: "transparent",
        border: "none",
        cursor: "pointer",
        padding: 0,
      }}
      title={label}
    >
      {label && <span style={{ fontSize: 14 }}>{label}</span>}
      <span
        style={{
          width: 40,
          height: 22,
          borderRadius: 999,
          background: checked ? "#22c55e" : "#d1d5db",
          position: "relative",
          transition: "background 120ms",
          display: "inline-block",
        }}
      >
        <span
          style={{
            position: "absolute",
            top: 2,
            left: checked ? 20 : 2,
            width: 18,
            height: 18,
            borderRadius: "50%",
            background: "#fff",
            boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
            transition: "left 120ms",
          }}
        />
      </span>
    </button>
  );
}

export default function Chat() {
  const { chatId } = useParams();
  const navigate = useNavigate();
  const id = useMemo(() => (chatId ? Number(chatId) : null), [chatId]);

  const token =
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [ragEnabled, setRagEnabled] = useState(false);
  const [title, setTitle] = useState("Чат");

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // авто-рост textarea
  function autoresize() {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    const max = 180; // px
    ta.style.height = Math.min(ta.scrollHeight, max) + "px";
  }

  useEffect(() => {
    setMessages([]);
    setInput("");
    setLoading(false);
    setRagEnabled(false);
    setTitle(id ? `Чат #${id}` : "Новый чат");
    // сброс высоты инпута при смене чата
    const ta = textareaRef.current;
    if (ta) ta.style.height = "42px";
  }, [id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    autoresize();
  }, [input]);

  async function send() {
    if (!token) return;
    const text = input.trim();
    if (!text || loading) return;

    const nextMessages: ChatMessage[] = [
      ...messages,
      { role: "user", content: text },
    ];

    const payload: ChatSendRequest = {
      messages: nextMessages,
      use_rag: ragEnabled,
      temperature: 0.2,
      top_k: 5,
    };

    setLoading(true);
    setInput("");
    setMessages(nextMessages);

    try {
      if (id == null) {
        // первый месседж создаёт чат
        const res = await sendNewChat(token, payload);
        setMessages((prev) => [...prev, res.assistant]);
        setTitle(res.chat.title);
        window.dispatchEvent(new CustomEvent("chats:refresh"));
        navigate(`/gpt/chat/${res.chat.id}`, { replace: true });
      } else {
        // поток для существующего чата
        const { textStream } = sendToChatStream(token, id, payload);
        let acc = "";
        setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
        for await (const chunk of textStream) {
          acc += chunk;
          setMessages((prev) => {
            const copy = [...prev];
            copy[copy.length - 1] = { role: "assistant", content: acc };
            return copy;
          });
        }
      }
    } catch (e) {
      console.error(e);
      try {
        if (id != null) {
          const res = await sendToChat(token, id, payload);
          setMessages((prev) => [...prev, res.assistant]);
        } else {
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: "Не удалось создать чат." },
          ]);
        }
      } catch (e2) {
        console.error(e2);
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "Не удалось получить ответ. Попробуйте позже.",
          },
        ]);
      }
    } finally {
      setLoading(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
    // Shift+Enter — обычный перенос строки
  }

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <div
        style={{
          padding: "10px 12px",
          borderBottom: "1px solid #e5e7eb",
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        <div style={{ fontWeight: 600 }}>{title}</div>
        <Switch
          checked={ragEnabled}
          onChange={setRagEnabled}
          label="RAG"
        />
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
        {messages.length > 0 && (
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            {messages.map((m, idx) => (
              <li
                key={idx}
                style={{
                  alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                  maxWidth: "70%",
                  background: m.role === "user" ? "#dbeafe" : "#f3f4f6",
                  padding: "8px 10px",
                  borderRadius: 10,
                  whiteSpace: "pre-wrap",
                }}
              >
                <div
                  style={{
                    fontSize: 12,
                    color: "#6b7280",
                    marginBottom: 4,
                  }}
                >
                  {m.role === "user" ? "Вы" : "Ассистент"}
                </div>
                <div>{m.content}</div>
              </li>
            ))}
            <div ref={bottomRef} />
          </ul>
        )}
      </div>

      {/* Input */}
      <div
        style={{
          padding: 12,
          borderTop: "1px solid #e5e7eb",
          display: "flex",
          gap: 8,
          alignItems: "flex-end",
        }}
      >
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          onInput={autoresize}
          placeholder="Введите сообщение…"
          rows={1}
          style={{
            flex: 1,
            resize: "none",
            padding: "10px 12px",
            border: "1px solid #e5e7eb",
            borderRadius: 8,
            lineHeight: "1.35",
            maxHeight: 180,
            overflowY: "auto",
          }}
          disabled={loading}
        />
        <button onClick={send} disabled={loading || !input.trim()}>
          {loading ? "…" : "Отправить"}
        </button>
      </div>
    </div>
  );
}
