import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

// Uses real auth, nginx, upload storage, extraction, and the configured LLM runtime.
// Supply a local refresh-token fixture; credentials never enter reports.
const authFile = process.env.CHAT_E2E_AUTH_FILE;
test.skip(
  !authFile || process.env.CHAT_E2E_LIVE !== '1',
  'CHAT_E2E_AUTH_FILE is required for the live stack'
);

function pdf(text: string): Buffer {
  const stream = `BT /F1 14 Tf 50 700 Td (${text}) Tj ET`;
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
  ];
  let value = '%PDF-1.4\n';
  const offsets = [0];
  for (const [i, object] of objects.entries()) {
    offsets.push(Buffer.byteLength(value));
    value += `${i + 1} 0 obj\n${object}\nendobj\n`;
  }
  const xref = Buffer.byteLength(value);
  value += `xref\n0 6\n0000000000 65535 f \n${offsets
    .slice(1)
    .map(o => `${String(o).padStart(10, '0')} 00000 n \n`)
    .join('')}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(value);
}

for (const kind of ['large-pdf', 'small-pdf', 'txt']) {
  test(`upload and attach ${kind} to a live chat message`, async ({
    page,
    context,
    request,
  }) => {
    test.setTimeout(240_000);
    const { refresh_token } = JSON.parse(readFileSync(authFile!, 'utf8'));
    await context.addCookies([
      {
        name: 'refresh_token',
        value: refresh_token,
        url: process.env.BASE_URL || 'http://nginx:8080',
        httpOnly: true,
        sameSite: 'Lax',
      },
    ]);
    const auth = await context.request.post('/api/v1/auth/refresh', {});
    expect(auth.ok()).toBeTruthy();
    const { access_token } = await auth.json();
    const headers = { Authorization: `Bearer ${access_token}` };
    const created = await context.request.post('/api/v1/chats', {
      headers,
      data: { name: `Attachment E2E ${kind}` },
    });
    expect(created.ok()).toBeTruthy();
    const { chat_id } = await created.json();
    console.log(`E2E ${kind} chat=${chat_id}`);
    await page.goto(`/gpt/chat/${chat_id}`);
    await expect(page.getByPlaceholder('Напишите сообщение...')).toBeVisible();
    const marker = 'VERIFY7391';
    const buffer =
      kind === 'txt'
        ? Buffer.from(
            `Verification code: ${marker}. Project delivery date: 2026-11-30.`
          )
        : pdf(
            `Verification code: ${marker}. Project delivery date: 2026-11-30.`
          );
    const uploadBuffer =
      kind === 'large-pdf'
        ? Buffer.concat([
            buffer,
            Buffer.from(`\n%${' '.repeat(1_500_000 - buffer.length)}\n`),
          ])
        : buffer;
    const filename = kind === 'txt' ? 'verification.txt' : `${kind}.pdf`;
    await page.locator('input[type=file]').setInputFiles({
      name: filename,
      mimeType: kind === 'txt' ? 'text/plain' : 'application/pdf',
      buffer: uploadBuffer,
    });
    await page
      .locator('textarea')
      .first()
      .fill(
        'Прочитай текущее вложение инструментом file.read и верни дословно verification code и дату поставки из файла.'
      );
    const upload = page.waitForResponse(
      r =>
        r.url().endsWith(`/chats/${chat_id}/uploads`) &&
        r.request().method() === 'POST'
    );
    const answer = page.waitForResponse(
      r =>
        r.url().includes(`/chats/${chat_id}/messages`) &&
        r.request().method() === 'POST'
    );
    await page
      .getByRole('button', { name: 'Отправить сообщение', exact: true })
      .click();
    const uploaded = await upload;
    expect(uploaded.status()).toBe(200);
    const { artifact_id } = await uploaded.json();
    const stream = await answer;
    expect(stream.status()).toBe(200);
    await expect
      .poll(async () => {
        const messages = await request.get(
          `/api/v1/chats/${chat_id}/messages`,
          { headers }
        );
        const transcript = await messages.json();
        return transcript.items.some(
          (message: {
            role: string;
            meta?: { attachments?: Array<{ artifact_id: string }> };
          }) =>
            message.role === 'user' &&
            message.meta?.attachments?.some(
              item => item.artifact_id === artifact_id
            )
        );
      })
      .toBeTruthy();
    const stop = page.getByRole('button', { name: /Остановить/ });
    if (await stop.isVisible()) await stop.click();
    await expect(
      page.getByRole('button', { name: 'Отправить сообщение', exact: true })
    ).toBeVisible();
  });
}
