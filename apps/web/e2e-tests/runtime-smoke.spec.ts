import { test, expect } from '@playwright/test';

async function streamChat(page: any, chatId: string, content: string) {
  return page.evaluate(async ({ chatIdArg, contentArg }) => {
    const token = localStorage.getItem('access_token');
    if (!token) throw new Error('access_token not found in localStorage');

    const res = await fetch(`/api/v1/chats/${chatIdArg}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        content: contentArg,
        use_rag: false,
        model: null,
        agent_slug: null,
        attachment_ids: [],
      }),
    });

    if (!res.ok || !res.body) {
      throw new Error(`stream failed: HTTP ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    const events: Array<{ event: string; payload: any }> = [];

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      let sepIdx = -1;
      while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
        const rawEvent = buffer.slice(0, sepIdx);
        buffer = buffer.slice(sepIdx + 2);

        const lines = rawEvent.split('\n');
        const eventLine = lines.find((l: string) => l.startsWith('event:')) || '';
        const dataLines = lines.filter((l: string) => l.startsWith('data:'));
        const eventType = eventLine.replace('event:', '').trim();
        const data = dataLines
          .map((dl: string) => {
            let val = dl.slice(5);
            if (val.startsWith(' ')) val = val.slice(1);
            return val;
          })
          .join('\n');

        if (data === '[DONE]') continue;

        let payload: any = data;
        try {
          payload = JSON.parse(data);
        } catch {
          // keep raw text for delta-like events
        }
        events.push({ event: eventType, payload });
      }
    }

    return events;
  }, { chatIdArg: chatId, contentArg: content });
}

async function getChatMessages(page: any, chatId: string) {
  return page.evaluate(async ({ chatIdArg }) => {
    const token = localStorage.getItem('access_token');
    if (!token) throw new Error('access_token not found in localStorage');
    const res = await fetch(`/api/v1/chats/${chatIdArg}/messages?limit=50`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    if (!res.ok) throw new Error(`messages failed: HTTP ${res.status}`);
    return res.json();
  }, { chatIdArg: chatId });
}

test.describe('Runtime Smoke', () => {
  test('chat stream emits envelope and cross-turn recall works', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/логин|email|login/i).fill('admin@test.com');
    await page.getByLabel(/пароль|password/i).fill('admin123');
    await page.getByRole('button', { name: /войти|sign in|login/i }).click();
    await expect(page).toHaveURL(/\/(gpt|chat|admin|$)/, { timeout: 10000 });

    const chat = await page.evaluate(async () => {
      const token = localStorage.getItem('access_token');
      if (!token) throw new Error('access_token not found in localStorage');
      const res = await fetch('/api/v1/chats', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ name: 'runtime-smoke', tags: null }),
      });
      if (!res.ok) throw new Error(`create chat failed: HTTP ${res.status}`);
      return res.json();
    });
    const chatId = chat.chat_id as string;
    expect(chatId).toBeTruthy();

    const codeword = 'ORBIT-7391';
    const firstEvents = await streamChat(
      page,
      chatId,
      `Запомни кодовое слово: ${codeword}. Ответь одним словом ok.`,
    );
    const firstTerminal = firstEvents.find((e) => e.event === 'final' || e.event === 'stop');
    expect(firstTerminal).toBeTruthy();
    const firstEnvelopeSource =
      (firstTerminal?.payload && typeof firstTerminal.payload === 'object' && firstTerminal.payload.orchestration_envelope)
      || firstEvents
        .map((e) => e.payload)
        .find((p) => p && typeof p === 'object' && p.orchestration_envelope)?.orchestration_envelope;
    expect(firstEnvelopeSource).toBeTruthy();
    expect(Number(firstEnvelopeSource.sequence)).toBeGreaterThan(0);

    await streamChat(
      page,
      chatId,
      'Какое кодовое слово я просил запомнить в прошлом сообщении? Ответь только кодовым словом.',
    );
    const messages = await getChatMessages(page, chatId);
    const assistantMessages = (messages.items || []).filter((m: any) => m.role === 'assistant');
    expect(assistantMessages.length).toBeGreaterThan(0);
    const lastAssistant = assistantMessages[assistantMessages.length - 1];
    // API returns `content` either as a plain string (current shape) or as
    // `{ text: string }` (legacy shape). Handle both so the smoke is robust
    // to the envelope choice without depending on response-shape migrations.
    const rawContent = lastAssistant?.content;
    const answerText = (
      typeof rawContent === 'string' ? rawContent : String(rawContent?.text || '')
    ).toUpperCase();
    expect(answerText).toContain(codeword);
  });
});

