# Frontend (pure)

Чистый фронт на React + Vite + TS. Без Docker и без обратного прокси в этой директории.

## Быстрый старт (локально)
```bash
npm i
cp .env.example .env
# при необходимости поменяйте VITE_API_BASE (по умолчанию /api)
npm run dev
```

## Структура
- `src/theme.css` — глобальная тема (CSS-переменные).
- `src/shared/ui/*` — переиспользуемые компоненты (CSS Modules).
- `src/shared/api/*` — слой API (вынесен из компонентов).
- `src/shared/lib/*` — утилиты (SSE, хранилище).
- `src/app/routes/*` — страницы/лейауты (Login, GPTGate, GPTLayout, Chat).
- `src/app/store/*` — zustand store (auth).

## Примечания
- Авторизация: login → me, хранение токенов в localStorage, авто-refresh.
- Чат: создание чата, отправка сообщения со стримом (SSE/чанки).
- Idempotency-Key: для POST сообщений (генерируется через crypto.randomUUID()).

## Моки (без бэкенда)
Включить моки: в `.env` установите `VITE_USE_MOCKS=true` (по умолчанию уже так в `.env.example`).  
Моки реализованы внутри `src/mocks/mockFetch.ts` и перехватываются на уровне `apiFetch()`.
Поддержано:
- `POST /auth/login` (`admin` / `admin`), `GET /auth/me`, `POST /auth/refresh`, `POST /auth/logout`
- `POST /chats` создание чата
- `POST /chats/:id/messages` со стримингом **SSE** (моковый ответ печатается по символам)
- `GET /chats/:id/messages`, `GET /chats`
- `GET /rag`, `POST /rag/upload`, `POST /rag/search`

Чтобы перейти на реальный бэкенд — поставьте `VITE_USE_MOCKS=false` и настройте `VITE_API_BASE`.


⚙️ При запуске с `VITE_USE_MOCKS=true` глобально переопределяется `window.fetch` (см. `src/mocks/enableMocks.ts`), чтобы ни один запрос не улетел в реальный бэкенд.

## Навигация по чатам
В разделе **Chat** добавлена боковая панель со списком чатов и кнопкой **New**.
- Маршруты: `/gpt/chat/:chatId`
- Создание нового чата автоматически перенаправляет к нему.
- Сообщения чата подгружаются при переключении.
