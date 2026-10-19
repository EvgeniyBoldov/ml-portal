import { test as base, expect, type Page } from '@playwright/test';
import { readFileSync, writeFileSync, unlinkSync } from 'node:fs';

const authFile = process.env.CHAT_E2E_AUTH_FILE;
const test = base.extend<{ chatId: string }>({
  chatId: async ({ page, context }, use) => {
    if (!authFile) throw new Error('CHAT_E2E_AUTH_FILE is required');
    const { refresh_token } = JSON.parse(readFileSync(authFile, 'utf8'));
    await context.addCookies([
      {
        name: 'refresh_token',
        value: refresh_token,
        url: process.env.BASE_URL || 'http://nginx:8081',
        httpOnly: true,
        sameSite: 'Lax',
      },
    ]);
    expect((await context.request.post('/api/v1/auth/refresh')).status()).toBe(
      200
    );
    const response = await context.request.post('/api/v1/chats', {
      data: { name: 'Chat contract E2E' },
    });
    expect(response.status()).toBe(200);
    const { chat_id } = await response.json();
    await page.goto(`/gpt/chat/${chat_id}`);
    await expect(page.getByPlaceholder('Напишите сообщение...')).toBeVisible();
    await use(chat_id);
    await context.request.delete(`/api/v1/chats/${chat_id}`);
  },
});
test.skip(!authFile, 'Requires local authenticated test session');

const answer = (page: Page) =>
  page.getByRole('article', { name: 'Ответ ассистента', exact: true }).last();
async function send(page: Page, content: string) {
  await page.getByPlaceholder('Напишите сообщение...').fill(content);
  await page
    .getByRole('button', { name: 'Отправить сообщение', exact: true })
    .click();
}
async function clarify(page: Page, question: string, response: string) {
  await expect(
    page.getByRole('heading', { name: question, exact: true })
  ).toBeVisible();
  await page
    .getByPlaceholder('Введите уточнение для продолжения...')
    .fill(response);
  await page.getByRole('button', { name: 'Ответить', exact: true }).click();
}

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

// Each test traverses browser -> nginx -> real chat routes/services -> PostgreSQL.
// Only RuntimePipeline.execute is scripted by the separate test application.
test('send, streamed answer, persistence, next message', async ({
  page,
  chatId,
}) => {
  await send(page, 'E2E:echo Первое сообщение');
  await expect(answer(page)).toContainText('Получено 25 символов');
  await expect(
    page.getByRole('article', { name: 'Сообщение пользователя' })
  ).toHaveCount(1);
  await page.reload();
  await expect(answer(page)).toContainText('Первое сообщение');
  await send(page, 'E2E:echo Второе сообщение');
  await expect(
    page.getByRole('article', { name: 'Ответ ассистента', exact: true })
  ).toHaveCount(2);
  await expect(answer(page)).toContainText('Второе сообщение');
  const composer = page.getByPlaceholder('Напишите сообщение...');
  await composer.focus();
  await composer.press('ArrowUp');
  await expect(composer).toHaveValue('E2E:echo Второе сообщение');
});

test('large Unicode message survives request, rendering and persistence', async ({
  page,
  chatId,
}) => {
  const content = `E2E:echo ${'Большое сообщение 🐙\n'.repeat(2_000)}КОНЕЦ`;
  await send(page, content);
  await expect(answer(page)).toContainText(
    `Получено ${Array.from(content).length} символов`
  );
  const response = await page.request.get(`/api/v1/chats/${chatId}/messages`);
  expect(
    (await response.json()).items.find(
      (m: { role: string }) => m.role === 'user'
    ).content
  ).toBe(content);
});

test('clarification header contains the new question, answer is persisted', async ({
  page,
  chatId,
}) => {
  await send(page, 'E2E:clarify Исходный запрос');
  await clarify(page, 'Какой проект?', 'Проект Альфа');
  await expect(answer(page)).toContainText(
    'Готово: Какой проект? Проект Альфа'
  );
  await expect(
    page.getByPlaceholder('Введите уточнение для продолжения...')
  ).toHaveCount(0);
  await page.reload();
  await expect(
    page.getByRole('article', { name: 'Сообщение пользователя' }).last()
  ).toContainText('Проект Альфа');
});

test('three subsequent clarifications in the same run, reload restores only the current question', async ({
  page,
  chatId,
}) => {
  await send(page, 'E2E:clarify-three Подготовить отчёт');
  await clarify(page, 'Какой проект?', 'Альфа');
  await expect(
    page.getByRole('heading', { name: 'Какой период?' })
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'Какой период?' })
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Какой проект?' })
  ).toHaveCount(0);
  await clarify(page, 'Какой период?', 'Октябрь');
  await clarify(page, 'В каком формате нужен ответ?', 'Таблица');
  await expect(answer(page)).toContainText(
    'Альфа; Какой период? Октябрь; В каком формате нужен ответ? Таблица'
  );
  await page.reload();
  await expect(page.getByPlaceholder('Напишите сообщение...')).toBeVisible();
  await expect(
    page.getByPlaceholder('Введите уточнение для продолжения...')
  ).toHaveCount(0);
});

test('confirmation issue, resume token, final answer', async ({
  page,
  chatId,
}) => {
  await send(page, 'E2E:confirm Выполнить действие');
  await expect(
    page.getByText('Подтвердить тестовое действие?', { exact: true })
  ).toBeVisible();
  await page.getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect(answer(page)).toContainText('Действие подтверждено');
});

test('clarification then confirmation in one run', async ({ page, chatId }) => {
  await send(page, 'E2E:clarify-confirm Публикация');
  await clarify(page, 'Какой проект?', 'Альфа');
  await expect(
    page.getByText('Подтвердить публикацию отчёта?', { exact: true })
  ).toBeVisible();
  await page.getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect(answer(page)).toContainText('Альфа');
});

for (const kind of ['clarify', 'confirm']) {
  test(`cancel ${kind}, no stale interaction on reload or next send`, async ({
    page,
    chatId,
  }) => {
    await send(page, `E2E:${kind} Отменить ожидание`);
    await expect(
      page.getByRole('button', { name: 'Отменить', exact: true })
    ).toBeVisible();
    await page.getByRole('button', { name: 'Отменить', exact: true }).click();
    await expect(page.getByPlaceholder('Напишите сообщение...')).toBeVisible();
    await page.reload();
    await expect(page.getByPlaceholder('Напишите сообщение...')).toBeVisible();
    await send(page, 'E2E:echo После отмены');
    await expect(answer(page)).toContainText('После отмены');
  });
}

for (const status of [400, 403, 409, 413, 422, 429, 500, 503]) {
  test(`HTTP ${status} is visible and chat remains usable`, async ({
    page,
    chatId,
  }) => {
    await send(page, `E2E:http-${status} Ошибка`);
    await expect(
      page.getByRole('button', { name: 'Отправить сообщение', exact: true })
    ).toBeVisible();
    await expect(
      page.getByText(new RegExp(`HTTP ${status}|${status}`)).last()
    ).toBeVisible();
    await send(page, 'E2E:echo После ошибки');
    await expect(answer(page)).toContainText('После ошибки');
  });
}

for (const mode of [
  'runtime-error',
  'empty-agent',
  'exception',
  'broken-sse',
  'malformed-sse',
]) {
  test(`${mode}: no clarification, no internal details, next send works`, async ({
    page,
    chatId,
  }) => {
    await send(page, `E2E:${mode} Ошибка`);
    await expect(
      page
        .getByText(/Ошибка|прервалось|Некорректное|недоступ|попробуйте/i)
        .last()
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Отправить сообщение', exact: true })
    ).toBeVisible();
    await expect(page.getByPlaceholder('Напишите сообщение...')).toHaveValue(
      ''
    );
    await expect(
      page.getByPlaceholder('Введите уточнение для продолжения...')
    ).toHaveCount(0);
    await expect(page.getByText(/SECRET_INTERNAL/)).toHaveCount(0);
    await send(page, 'E2E:echo Восстановление');
    await expect(answer(page)).toContainText('Восстановление');
  });
}

test('file validation: extension, MIME, size, binary signature, empty file', async ({
  page,
  chatId,
}) => {
  const input = page.locator('input[type=file]');
  await input.setInputFiles({
    name: 'bad.exe',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('MZ'),
  });
  await expect(
    page.getByText('Файл "bad.exe" не поддерживается')
  ).toBeVisible();
  await input.setInputFiles({
    name: 'bad.pdf',
    mimeType: 'image/png',
    buffer: Buffer.from('fake'),
  });
  await expect(page.getByText(/неподдерживаемый MIME/)).toBeVisible();
  const oversized = `/tmp/chat-e2e-oversized-${chatId}.txt`;
  writeFileSync(oversized, Buffer.alloc(51 * 1024 * 1024, 'x'));
  try {
    await input.setInputFiles(oversized);
  } finally {
    unlinkSync(oversized);
  }
  await expect(page.getByText(/превышает лимит/)).toBeVisible();
  for (const file of [
    {
      name: 'fake.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('This is not PDF'),
    },
    { name: 'empty.txt', mimeType: 'text/plain', buffer: Buffer.alloc(0) },
  ]) {
    const response = await page.request.post(
      `/api/v1/chats/${chatId}/uploads`,
      {
        multipart: {
          file: {
            name: file.name,
            mimeType: file.mimeType,
            buffer: file.buffer,
          },
        },
      }
    );
    expect(response.status()).toBe(400);
  }
});

test('failed upload keeps text and file for retry', async ({
  page,
  chatId,
}) => {
  await page.locator('input[type=file]').setInputFiles({
    name: 'fake.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('not PDF'),
  });
  await send(page, 'E2E:read Сохранить текст после ошибки');
  await expect(page.getByText(/PDF format/)).toBeVisible();
  await expect(page.getByPlaceholder('Напишите сообщение...')).toHaveValue(
    'E2E:read Сохранить текст после ошибки'
  );
  await expect(page.getByText('fake.pdf', { exact: true })).toBeVisible();
});

test('generic text MIME is accepted and file focus survives clarification', async ({
  page,
  chatId,
}) => {
  await page.locator('input[type=file]').setInputFiles({
    name: 'notes.txt',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('FILE_FOCUS_7391'),
  });
  await send(page, 'E2E:file-clarify Проверка вложения');
  await clarify(page, 'Какой проект?', 'Альфа');
  await expect(answer(page)).toContainText('Альфа');
  await expect(
    page.getByRole('link', { name: /notes.txt/ }).first()
  ).toBeVisible();
});

test('upload and read a 1.5 MB PDF through the chat tool path', async ({
  page,
  chatId,
}) => {
  const marker = 'VERIFY7391';
  const content = pdf(
    `Verification code: ${marker}. Project delivery date: 2026-11-30.`
  );
  const large = Buffer.concat([
    content,
    Buffer.from(`\n%${' '.repeat(1_500_000 - content.length)}\n`),
  ]);
  await page.locator('input[type=file]').setInputFiles({
    name: 'verification.pdf',
    mimeType: 'application/pdf',
    buffer: large,
  });
  await send(page, 'E2E:read Прочитай текущее PDF-вложение и верни код и дату');
  await expect(answer(page)).toContainText(marker, { timeout: 60_000 });
  await expect(answer(page)).toContainText('2026-11-30');
  const response = await page.request.get(`/api/v1/chats/${chatId}/messages`);
  const items = (await response.json()).items;
  expect(
    items.some(
      (item: { role: string; content: unknown }) =>
        item.role === 'assistant' &&
        JSON.stringify(item.content).includes(marker)
    )
  ).toBeTruthy();
});

test('response attachment downloads real bytes; answer link survives reload', async ({
  page,
  chatId,
}) => {
  await send(page, 'E2E:files Подготовь файл');
  await expect(
    page.getByRole('link', { name: 'Документация', exact: true })
  ).toHaveAttribute('href', 'https://example.com/report');
  const downloaded = page.waitForEvent('download');
  await page.getByRole('link', { name: 'e2e-result.txt' }).click();
  const file = await downloaded;
  expect(file.suggestedFilename()).toBe('e2e-result.txt');
  expect(readFileSync((await file.path())!, 'utf8')).toBe(
    'E2E generated result 7391'
  );
  await page.reload();
  await expect(
    page.getByRole('link', { name: 'e2e-result.txt' })
  ).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Документация', exact: true })
  ).toBeVisible();
});

test('stop stream, preserve partial answer, next send ignores late old events', async ({
  page,
  chatId,
}) => {
  await page.locator('input[type=file]').setInputFiles({
    name: 'notes.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('прикрепленный файл'),
  });
  await expect(page.getByText('notes.txt')).toBeVisible();
  await send(page, 'E2E:slow Долгий запрос');
  const composer = page.getByPlaceholder('Напишите сообщение...');
  await expect(composer).toHaveValue('');
  await expect(composer).toBeDisabled();
  await expect(page.getByText('notes.txt')).toHaveCount(0);
  await expect(page.locator('input[type=file]')).toBeDisabled();
  await expect(
    page.getByRole('button', { name: 'Остановить генерацию' })
  ).toBeEnabled();
  await expect(
    page.getByRole('button', { name: 'Отправить сообщение' })
  ).toHaveCount(0);
  await expect(answer(page)).toContainText('Начало длинного ответа');
  await page.getByRole('button', { name: /Остановить/ }).click();
  await expect(answer(page)).toContainText('Начало длинного ответа');
  await expect
    .poll(async () => {
      const turns = await (
        await page.request.get(`/api/v1/__e2e/chats/${chatId}/turns`)
      ).json();
      return turns[0]?.status;
    })
    .toBe('cancelled');
  await expect(
    page.getByRole('button', { name: 'Отправить сообщение', exact: true })
  ).toBeVisible();
  await send(page, 'E2E:echo Новый запрос');
  await expect(answer(page)).toContainText('Новый запрос');
  await expect(page.getByText('ЗАПОЗДАЛЫЙ_ОТВЕТ')).toHaveCount(0);
});

test('stale answer from a previous pause cannot answer the next question', async ({
  page,
  chatId,
}) => {
  await send(page, 'E2E:clarify-three Последовательные вопросы');
  await expect(
    page.getByRole('heading', { name: 'Какой проект?' })
  ).toBeVisible();
  const first = (
    await (await page.request.get(`/api/v1/chats/${chatId}/paused-run`)).json()
  ).pause;
  expect(first.action.pause_id).toBeTruthy();
  await clarify(page, 'Какой проект?', 'Альфа');
  await expect(
    page.getByRole('heading', { name: 'Какой период?' })
  ).toBeVisible();
  const rejected = await page.request.post(
    `/api/v1/chats/runs/${first.run_id}/resume`,
    {
      data: {
        action: 'input',
        input: 'Повторный ответ из старой вкладки',
        pause_id: first.action.pause_id,
      },
    }
  );
  expect(rejected.status()).toBe(409);
  const second = (
    await (await page.request.get(`/api/v1/chats/${chatId}/paused-run`)).json()
  ).pause;
  expect(second.action.pause_id).not.toBe(first.action.pause_id);
  expect(second.context.question).toBe('Какой период?');
  await clarify(page, 'Какой период?', 'Ноябрь');
  await clarify(page, 'В каком формате нужен ответ?', 'Текст');
  await expect(answer(page)).toContainText('Ноябрь');
});

test('network failure is recoverable and cannot become a clarification', async ({
  page,
  chatId,
}) => {
  await page.route(`**/chats/${chatId}/messages`, route =>
    route.request().method() === 'POST'
      ? route.abort('connectionreset')
      : route.continue()
  );
  await send(page, 'E2E:echo Ошибка сети');
  await expect(
    page.getByRole('button', { name: 'Отправить сообщение', exact: true })
  ).toBeVisible();
  await expect(
    page.getByPlaceholder('Введите уточнение для продолжения...')
  ).toHaveCount(0);
  await page.unroute(`**/chats/${chatId}/messages`);
  await send(page, 'E2E:echo Сеть восстановлена');
  await expect(answer(page)).toContainText('Сеть восстановлена');
});

test('several questions in one pause are displayed together in the header', async ({
  page,
  chatId,
}) => {
  await send(page, 'E2E:clarify-batch Уточнить сразу два параметра');
  const header = page.getByRole('heading', {
    name: 'Какой проект? Какой период?',
    exact: true,
  });
  await expect(header).toBeVisible();
  await expect(header).toHaveText('Какой проект?\nКакой период?');
  await page
    .getByPlaceholder('Введите уточнение для продолжения...')
    .fill('Альфа, ноябрь');
  await page.getByRole('button', { name: 'Ответить', exact: true }).click();
  await expect(answer(page)).toContainText('Альфа, ноябрь');
});

test('invalid resume actions and oversized answers preserve the current pause', async ({
  page,
  chatId,
}) => {
  await send(page, 'E2E:clarify Проверить валидацию продолжения');
  await expect(
    page.getByRole('heading', { name: 'Какой проект?' })
  ).toBeVisible();
  const { pause } = await (
    await page.request.get(`/api/v1/chats/${chatId}/paused-run`)
  ).json();
  for (const body of [
    { action: 'confirm', pause_id: pause.action.pause_id },
    { action: 'input', input: 'Альфа' },
    { action: 'input', input: 'Альфа', pause_id: 'obsolete' },
  ]) {
    expect(
      (
        await page.request.post(`/api/v1/chats/runs/${pause.run_id}/resume`, {
          data: body,
        })
      ).status()
    ).toBe(409);
  }
  expect(
    (
      await page.request.post(`/api/v1/chats/runs/${pause.run_id}/resume`, {
        data: {
          action: 'input',
          input: 'x'.repeat(4_001),
          pause_id: pause.action.pause_id,
        },
      })
    ).status()
  ).toBe(422);
  await clarify(page, 'Какой проект?', 'Альфа');
  await expect(answer(page)).toContainText('Альфа');
  expect(
    (
      await page.request.post(`/api/v1/chats/runs/${pause.run_id}/resume`, {
        data: {
          action: 'input',
          input: 'Дубликат',
          pause_id: pause.action.pause_id,
        },
      })
    ).status()
  ).toBe(404);
  const turns = await (
    await page.request.get(`/api/v1/__e2e/chats/${chatId}/turns`)
  ).json();
  expect(turns).toHaveLength(1);
  expect(turns[0].status).toBe('completed');
  const messages = (
    await (await page.request.get(`/api/v1/chats/${chatId}/messages`)).json()
  ).items;
  expect(
    messages.find((m: { id: string }) => m.id === turns[0].user_message_id)
      .content
  ).toContain('E2E:clarify');
});

test('late empty restoration cannot erase a newer streamed question', async ({
  page,
  chatId,
}) => {
  let release = () => {};
  let restored = false;
  await page.route(`**/chats/${chatId}/paused-run`, async route => {
    const response = await route.fetch();
    await new Promise<void>(resolve => {
      release = resolve;
      restored = true;
    });
    await route.fulfill({ response }).catch(() => {});
  });
  try {
    await page.reload();
    await expect.poll(() => restored).toBe(true);
    await send(page, 'E2E:clarify Не терять новый вопрос');
    await expect(
      page.getByRole('heading', { name: 'Какой проект?' })
    ).toBeVisible();
    release();
    await expect(
      page.getByRole('heading', { name: 'Какой проект?' })
    ).toBeVisible();
    await clarify(page, 'Какой проект?', 'Альфа');
    await expect(answer(page)).toContainText('Альфа');
  } finally {
    release();
  }
});

test('unknown or foreign-chat artifact produces an attachment error, not a clarification', async ({
  page,
  chatId,
}) => {
  const uploaded = await page.request.post(`/api/v1/chats/${chatId}/uploads`, {
    multipart: {
      file: {
        name: 'source.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from('private source'),
      },
    },
  });
  expect(uploaded.status()).toBe(200);
  const { artifact_id } = await uploaded.json();
  const other = await (
    await page.request.post('/api/v1/chats', {
      data: { name: 'Artifact isolation E2E' },
    })
  ).json();
  try {
    for (const id of [artifact_id, '00000000-0000-4000-8000-000000000099']) {
      const response = await page.request.post(
        `/api/v1/chats/${other.chat_id}/messages`,
        {
          data: {
            content: 'E2E:read Чужой файл',
            artifact_ids: [id],
          },
        }
      );
      const body = await response.text();
      expect(body).toContain('attachment_not_found');
      expect(body).not.toContain('event: pause');
      expect(body).not.toContain('event: final');
    }
  } finally {
    await page.request.delete(`/api/v1/chats/${other.chat_id}`);
  }
});

test('synthesis creates a file and the next turn can read it after reload', async ({
  page,
  chatId,
}) => {
  await send(page, 'E2E:synthesis-file Создай файл с примером Python');
  const fileLink = page.getByRole('link', {
    name: 'example.py',
    exact: true,
  });
  await expect(fileLink).toBeVisible();
  await expect(fileLink).toHaveAttribute(
    'href',
    /\/api\/v1\/files\/[^/]+\/download$/
  );
  const downloaded = page.waitForEvent('download');
  await fileLink.click();
  expect(readFileSync((await (await downloaded).path())!, 'utf8')).toContain(
    'SYNTHESIS_FILE_7391'
  );
  const contextResponse = await page.request.get(
    `/api/v1/chats/${chatId}/context`
  );
  expect(contextResponse.status()).toBe(200);
  expect(JSON.stringify(await contextResponse.json())).toContain('example.py');
  await page.reload();
  await expect(
    page.getByRole('link', { name: 'example.py', exact: true })
  ).toBeVisible();
  await send(page, 'E2E:read-existing Прочитай созданный файл');
  await expect(answer(page)).toContainText('SYNTHESIS_FILE_7391');
});

test('failed synthesis file creation cannot publish a successful attachment', async ({
  page,
  chatId,
}) => {
  await expect(page).toHaveURL(new RegExp(chatId));
  await send(page, 'E2E:synthesis-file-fail Создай файл');
  await expect(
    page
      .getByText(/Во время выполнения запроса возникли проблемы/, {
        exact: false,
      })
      .first()
  ).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'example.py', exact: true })
  ).toHaveCount(0);
  await expect(page.getByText('E2E_PRIVATE_FILE_ERROR')).toHaveCount(0);
  await send(page, 'E2E:text После ошибки');
  await expect(answer(page)).toContainText('После ошибки');
});
