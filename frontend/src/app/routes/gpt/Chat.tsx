import { useState, useRef } from "react";
import { chatStream } from "../../lib/api.ts";
import type { ChatMessage } from "../../lib/api.ts";
import { useAuth } from "../../store/auth.ts";
import Button from "../../components/Button.tsx";
import s from "./Chat.module.css";

type Msg = { role: "user"|"assistant"; content: string };

export default function Chat() {
    const [messages, setMessages] = useState<Msg[]>([]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const { token } = useAuth();
    const outRef = useRef<HTMLDivElement>(null);

    async function send() {
        if (!input.trim() || loading) return;
        const userMsg: Msg = { role: "user", content: input };
        setMessages(prev => [...prev, userMsg, { role: "assistant", content: "" }]);
        setInput(""); setLoading(true);
        const payload: ChatMessage[] = [...messages, userMsg].map(m => ({ role: m.role, content: m.content }));

        try {
            for await (const chunk of chatStream({ messages: payload, token, use_rag: false })) {
                setMessages(prev => {
                    const cp = [...prev];
                    cp[cp.length-1] = { role: "assistant", content: cp[cp.length-1].content + chunk };
                    return cp;
                });
                outRef.current?.scrollTo({ top: 1e9 });
            }
        } finally { setLoading(false); }
    }

    return (
        <div className={s.wrap}>
            <div ref={outRef} className={s.scroll}>
                {messages.map((m, i) => (
                    <div key={i} className={`${s.bubble} ${m.role==="user" ? s.user : s.assistant}`}>
                        {m.content}
                    </div>
                ))}
                {loading && <div className={s.hint}>Модель печатает…</div>}
            </div>

            <div className={s.row}>
                <input
                    className={s.input}
                    placeholder="Спросите что-нибудь…"
                    value={input} onChange={e=>setInput(e.target.value)}
                    onKeyDown={e=>e.key==="Enter" && send()}
                />
                <Button onClick={send} disabled={loading}>Отправить</Button>
            </div>
        </div>
    );
}
