
# Руководство по написанию и проведению тестов фронтенда

Это руководство объединяет практики архитектора и QA для вашего фронта на Vite + React + TS, с Vitest/RTL для unit/компонентных тестов и Playwright для E2E.

## 1) Пирамида тестирования
- **Unit/компонентные (60–70%)**: чистые функции, хуки, компоненты без сети.
- **Интеграционные (20–30%)**: компонент + стор/роутер/формы, мок REST.
- **E2E (10–15%)**: бизнес-флоу в браузере через Playwright.

## 2) Библиотеки и конфигурация
- **Vitest + @testing-library/react + user-event** для unit/компонентных.
- **jsdom** как env, общий `setup.ts` для `RTL + jest-dom`.
- Отчёт покрытия через `@vitest/coverage-v8` (`text`, `html`, `json`).
- **Playwright**: проекты `chromium`, `firefox`, `webkit`; репортеры `html`, `json`, `junit`; `trace/screenshot/video on failure`.
- Сторонние зависимости мокать через MSW или `vi.mock`, сетевые слои — через MSW.

## 3) Структура папок и нейминг
```
apps/web/
  src/
    shared/test-utils.tsx     # кастомный render с провайдерами
    test/setup.ts             # jest-dom, msw server, cleanup
    entities|features|widgets|pages/
      Component/
        Component.tsx
        Component.test.tsx
        Component.stories.tsx (опц.)
  e2e-tests/
    *.spec.ts                 # playwright сценарии
```
- Имена тестов: `*.test.tsx` для Vitest, `*.spec.ts` для E2E.
- Одна спека — один сценарий флоу/компонента; название по бизнес-ценности.

## 4) Правила для Unit/Component (Vitest + RTL)
- Тест держать **чистым от имплементации**: проверяем поведение и текст/ролли, не внутренние состояния.
- Использовать **поиск по ролям** (`getByRole`) и **доступность** вместо селекторов.
- **user-event** вместо fireEvent для реалистичного ввода.
- Изолировать дату/время через `vi.setSystemTime` и `fakeTimers` при необходимости.
- **MSW**: поднимать сервер в `setup.ts` и описывать хендлеры для REST/GraphQL.
- Не тестировать сторонние библиотеки, только интеграцию.
- Снимайте **минимальные снапшоты** (для лэйаута), иначе — проверяйте семантику.

### Шаблон теста (компонент/форма)
```ts
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Providers } from '@/shared/test-utils';
import { ProfileForm } from './ProfileForm';

test('успешная отправка формы', async () => {
  render(<ProfileForm />, { wrapper: Providers });
  await userEvent.type(screen.getByLabelText(/email/i), 'user@example.com');
  await userEvent.type(screen.getByLabelText(/password/i), 'Aa12345678!');
  await userEvent.click(screen.getByRole('button', { name: /save/i }));
  expect(await screen.findByText(/saved/i)).toBeInTheDocument();
});
```

## 5) Правила для Интеграционных
- Рендерить дерево c **Router + Store (zustand) + Theme**.
- Мокать **сетевые запросы** MSW-хендлерами (успех, 4xx, 5xx, таймаут).
- Проверять **сайд-эффекты**: редирект, запись в стор, кэш.

## 6) Правила для E2E (Playwright)
- **idempotent**: данные создавать с уникальными значениями (через `Date.now()`), удалять после.
- **Стабильность**: избегать фиксированных `wait`, использовать `await expect(...).toBeVisible()`.
- **Сетевые флейки**: для негативных — `page.route(...)` (аборт/500), для позитивных — прогрев окружения.
- **Параллельность**: не делить один и тот же «тестовый пользователь» между потоками.
- **Артефакты**: включён `trace/screenshot/video on failure`; выгружать html-репорт как артефакт CI.
- **Tagging/grep**: пометить критичные флоу `@smoke` и запускать их на каждый PR.

### Шаблон smoke E2E-флоу
```ts
import { test, expect } from '@playwright/test';

test('@smoke авторизация и чат: создать → отправить → удалить', async ({ page }) => {
  await page.goto('/');
  await page.fill('input[name="email"]', `user_${Date.now()}@example.com`);
  await page.fill('input[name="password"]', 'Aa12345678!');
  await page.click('button[type="submit"]');
  await expect(page.getByText(/welcome/i)).toBeVisible();

  await page.getByRole('button', { name: /new chat/i }).click();
  await page.getByRole('textbox', { name: /message/i }).fill('hello');
  await page.getByRole('button', { name: /send/i }).click();
  await expect(page.getByText(/hello/)).toBeVisible();

  await page.getByRole('button', { name: /delete chat/i }).click();
  await page.getByRole('button', { name: /confirm/i }).click();
  await expect(page.getByText(/deleted/i)).toBeVisible();
});
```

## 7) Политики покрытия
- **Минимум**: 80% lines/branches по `src/`, исключая `src/test/**`, типы и конфиги.
- **Критические модули** (аутентификация, чаты, роли): ≥90% branches.
- E2E: smoke на PR, регресс полную — по nightly/merge в main.

## 8) Стандарты кода тестов
- AAA (Arrange-Act-Assert), без «магических» чисел/стороночных селекторов.
- Один «ожидаемый результат» на один кейс; сложные кейсы — разделить.
- Именование: `feature: действие → результат`.

## 9) Запуск и отчётность
- Локально: `npm run test` (unit), `npx playwright test` (e2e).
- В Docker/Makefile: `make test-frontend`, `make test-frontend-e2e`.
- Публикация: выгружать `coverage/` и `playwright-report/` как артефакты CI.
- Gate в CI: блокировать PR при падении smoke/покрытия ниже порога.

## 10) Нефункциональные проверки UI
- **Адаптивность**: mobile 375×667 и desktop 1920×1080.
- **Доступность**: `aria-*`, контрасты, `tab`-навигация, `:focus-visible`.
- **Производительность**: Lighthouse бюджет (TTI, CLS, LCP), basic регресс.
- **i18n**: переключение locale, падежи/плюрализация, направление текста.
- **Безопасность**: XSS (ввод `<script>`), CSRF (если формы), хардкод токенов.

## 11) Что автоматизировать в первую очередь (Roadmap)
1. Smoke E2E: авторизация, базовая навигация, CRUD чатов.
2. Компонентные: формы (валидация), хедеры/меню/роутинг, хранилище (zustand).
3. Негативные E2E: сеть (abort/500), просроченный токен, форс-логаут.
4. Роли/доступы: админ/писатель/читатель — видимость и ограничения.
5. Нефункциональные: a11y smoke, responsive smoke.
