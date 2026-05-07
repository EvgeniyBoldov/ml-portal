# Chat Frontend Normalization Plan

## 0. Статус выполнения

- [x] Этап 1. Message Layout
- [x] Этап 2. Markdown Rendering
- [x] Этап 3. Structured Answer Blocks
- [x] Этап 4. Streaming Render Performance
- [x] Этап 5. Chat State Boundaries
- [x] Этап 6. Composer Reliability
- [x] Этап 7. Smart Scroll
- [x] Этап 8. Chat Auto Rename After First Message
- [x] Этап 9. Cleanup

### Что сделано в этой итерации

- Переработан рендер сообщений: assistant без тяжелого bubble, user bubble сохранен, добавлен smart jump к новым сообщениям.
- Приведен markdown к chat-формату: уменьшены заголовки и отступы, включен режим без forced line breaks для chat messages.
- `answerBlocks` получили безопасный fallback на `content` при неизвестных или пустых блоках.
- Исправлен cache-update для `chat_title`: обновление через `qk.chats.all()` вместо жесткого ключа.
- Зафиксирована защита auto-rename от перезаписи кастомных названий:
  - backend title generation выполняется только для дефолтных имен (`New Chat`, `Новый чат`, пустое);
  - добавлены backend unit-тесты на сценарии first-message и no-overwrite.
- В `ChatComposer` закрыта утечка preview URL (`createObjectURL`/`revokeObjectURL`) и добавлены `aria-label` для icon-кнопок.
- Удален неиспользуемый legacy `OptimizedChatMessage`.
- Снижен ререндер-шум:
  - добавлен custom `memo` comparator в `ChatMessage`;
  - `ChatStatus` переведен на отдельный `ChatStatusContext`, не подписан на весь chat-state.
  - обновления `streamStatus` защищены от повторных set-state при неизменном значении.
  - chat-контекст разнесен на узкие контексты (`actions`, `messages-state`, `catalog-state`, `status-state`);
  - потребители (`Chat`, `ChatStatus`, `ChatSearch`, `ChatStats`, `ChatExport`) переведены на узкие хуки.
- Добавлены unit-тесты:
  - `ChatMessage.test.tsx` (fallback/structured render);
  - `ChatComposer.test.tsx` (revoke on send/unmount).

### Что осталось до полного закрытия плана

- План реализован по коду и тестам; финальная ручная UX-проверка в браузере остается как release-smoke перед выкладкой.

### Ограничение текущего окружения проверки

- Frontend `type-check` и `vitest` в контейнере сейчас нестабильны из-за поврежденных/несовместимых зависимостей в `node_modules` контейнера (`micromark/remark` d.ts parse errors, ранее отсутствующий `object-keys`).
- Backend unit-тесты по авто-ренейму и orchestration проходят штатно.

## 1. Цель

Привести фронт чата к предсказуемому, спокойному и производительному рендерингу:

- сообщения читаются как рабочий диалог, без лишних карточек и визуального шума;
- assistant-ответы выглядят как документный текст: нормальная ширина, аккуратные списки, таблицы, код и источники;
- user-сообщения остаются компактными bubble-сообщениями;
- streaming обновляет только нужные части интерфейса;
- старый техдолг с названием чата закрыт: новый чат автоматически получает нормальное имя после первого сообщения.

## 2. Scope

### В scope

- `apps/web/src/domains/gpt/pages/Chat.tsx`
- `apps/web/src/domains/gpt/pages/Chat.module.css`
- `apps/web/src/domains/chat/components/ChatMessage.tsx`
- `apps/web/src/domains/chat/components/ChatMessage.module.css`
- `apps/web/src/domains/chat/components/ChatComposer.tsx`
- `apps/web/src/domains/chat/contexts/ChatContext.tsx`
- `apps/web/src/shared/ui/MarkdownRenderer.tsx`
- `apps/web/src/shared/ui/MarkdownRenderer.module.css`
- chat title auto-rename flow: frontend event handling + backend contract check

### Не в scope

- редизайн всего `/gpt` shell;
- изменение backend runtime-логики агентов;
- изменение RAG/collection contracts;
- миграция всего chat state на новую библиотеку состояния.

## 3. Принципы целевого UI

1. Assistant-сообщение не является карточкой. Это основной текстовый документ в ленте.
2. User-сообщение остается bubble справа, потому что это короткий ввод пользователя.
3. Markdown в чате не должен выглядеть как статья или landing page.
4. Таблицы и код должны использовать доступную ширину, а не сжиматься до 75%.
5. Streaming не должен заставлять перерисовываться всю страницу чата.
6. Системные runtime-статусы не должны доминировать над ответом.

## 4. Этапы работ

### Этап 1. Message Layout

**Задачи:**

- Разделить визуальные правила для `user` и `assistant`.
- Убрать тяжелый bubble у assistant-сообщений: фон, border и крупный radius оставить только там, где это действительно нужно.
- Оставить user-сообщение справа в компактном bubble.
- Расширить assistant content до доступной ширины контейнера.
- Сохранить аватар/роль только если они не создают лишний шум. Если оставляем, сделать их вторичными визуально.
- Проверить responsive layout на узких экранах.

**Критерии выполнения:**

- Длинный assistant-ответ занимает почти всю ширину ленты.
- User-сообщение визуально отделено и не смешивается с ответом.
- Таблица в assistant-ответе не сжимается из-за `max-width: 75%`.
- На ширине 375px текст не вылезает за экран.
- Визуально нет ощущения "карточка внутри карточки".

**Проверка:**

- Ручная проверка `/gpt/chat/:id` с коротким ответом.
- Ручная проверка с длинным markdown-ответом.
- Ручная проверка с таблицей, кодом и списком.

### Этап 2. Markdown Rendering

**Задачи:**

- Ввести chat-oriented markdown profile для сообщений.
- Приглушить `h1`, `h2`, `h3`: в чате они не должны быть hero-заголовками.
- Уменьшить вертикальные отступы параграфов, списков, quote и hr.
- Пересмотреть `remarkBreaks`: одиночный перенос не должен автоматически делать ответ рваным, если это не требуется контрактом.
- Проверить inline code, fenced code, ordered/unordered lists, nested lists, blockquote.
- Сделать кодовые блоки менее тяжелыми визуально, но оставить читаемость и horizontal scroll.
- Убедиться, что ссылки безопасны и не ломают layout.

**Критерии выполнения:**

- Ответ с `#`, `##`, `###` выглядит как структурированный chat response, а не как отдельная статья.
- Списки не получают лишние большие отступы.
- Кодовый блок не перетягивает все внимание на себя.
- Markdown без пустых строк между предложениями не превращается в чрезмерно разреженный текст.
- Таблицы имеют horizontal scroll внутри сообщения и не растягивают страницу.

**Проверка:**

- Snapshot/visual fixture с markdown:
  - headings;
  - paragraphs;
  - ordered list;
  - unordered list;
  - table;
  - code block;
  - inline code;
  - links;
  - blockquote.

### Этап 3. Structured Answer Blocks

**Задачи:**

- Пересмотреть ветку `answerBlocks`.
- Добавить fallback: если `answerBlocks` пустые после фильтрации или содержат неизвестные типы, рендерить обычный `content`.
- Для известных блоков (`bigstring`, `code`, `table`, `file`, `citations`) определить единый визуальный стиль.
- Не дублировать markdown/table styling между `ChatMessage.module.css` и `MarkdownRenderer.module.css` без необходимости.
- Для `table` block поддержать безопасный рендер строк с missing values.
- Для unknown block types добавить нейтральный fallback или пропуск без потери основного content.

**Критерии выполнения:**

- Сообщение не может стать пустым только из-за невалидного `answerBlocks`.
- `bigstring` выглядит так же, как обычный markdown answer.
- `code` выглядит так же, как fenced code из markdown.
- `table` block и markdown table визуально согласованы.
- Unknown block не ломает весь message render.

**Проверка:**

- Unit tests для `ChatMessage`:
  - content only;
  - valid `answerBlocks`;
  - invalid/unknown `answerBlocks` + content fallback;
  - empty `answerBlocks` + content fallback.

### Этап 4. Streaming Render Performance

**Задачи:**

- Стабилизировать props для `ChatMessage`.
- Не создавать новые arrays/objects для `ragSources`, `attachments`, `answerBlocks` на каждый render без необходимости.
- Перенести normalization/meta parsing ближе к state layer или мемоизировать на уровне message id/meta reference.
- Убедиться, что при streaming delta обновляется только последний assistant message.
- Проверить, нужен ли `OptimizedChatMessage.tsx`; удалить или включить в целевую реализацию отдельной задачей.

**Критерии выполнения:**

- При streaming длинного ответа старые сообщения не перерисовываются на каждый delta flush.
- `React.memo(ChatMessage)` реально снижает количество renders.
- Нет заметного лага на чате со 100 сообщениями.
- Не появляется рассинхрон между message meta и rendered props.

**Проверка:**

- React Profiler: streaming одного ответа в чате с 100 сообщениями.
- Ручная проверка smooth scroll во время streaming.
- Unit test normalization helper, если он будет вынесен отдельно.

### Этап 5. Chat State Boundaries

**Задачи:**

- Разделить concerns внутри `ChatContext`:
  - message history;
  - stream status;
  - pending confirmation/input;
  - chat list/sidebar data.
- Минимально стабилизировать `ChatContext.Provider value` через `useMemo`.
- Убедиться, что `ChatSidebar` не перерисовывается из-за каждого streaming delta.
- Убрать дублирование SSE parsing между `shared/api/chats.ts` и `ChatContext.tsx` или явно выбрать один источник правды.
- Привести `useEffect` dependencies в `Chat.tsx` к предсказуемому виду.

**Критерии выполнения:**

- Streaming delta не вызывает ререндер sidebar.
- Chat status обновляется независимо от message list.
- SSE event parsing существует в одном месте или имеет общий parser/helper.
- ESLint hooks rules не требуют suppressions.

**Проверка:**

- React Profiler на streaming.
- Existing chat flows:
  - normal message;
  - agent message;
  - waiting input;
  - confirmation required;
  - abort stream.

### Этап 6. Composer Reliability

**Задачи:**

- Закрыть утечку `URL.createObjectURL` для attachment previews.
- Revoke делать при:
  - удалении attachment;
  - успешной отправке;
  - unmount компонента;
  - очистке списка вложений.
- Добавить `aria-label` для icon-only buttons.
- Проверить disabled states во время upload/send/stream.
- Проверить отправку attachment-only сообщения.

**Критерии выполнения:**

- После отправки файлов object URLs освобождаются.
- При unmount composer object URLs освобождаются.
- Кнопки доступны через screen reader labels.
- Нельзя отправить дубль во время active send.

**Проверка:**

- Unit test на cleanup previews.
- Ручная проверка upload + send + remove.

### Этап 7. Smart Scroll

**Задачи:**

- Заменить безусловный scroll-to-bottom на smart scroll.
- Скроллить вниз автоматически только если пользователь находится около нижней границы.
- При новом входящем сообщении, если пользователь читает историю, показать ненавязчивый indicator "новые сообщения".
- При отправке собственного сообщения всегда скроллить вниз.
- Сохранить корректное поведение при streaming.

**Критерии выполнения:**

- Если пользователь читает старые сообщения, streaming не дергает scroll вниз.
- Если пользователь внизу, streaming остается приклеенным к низу.
- При отправке нового user-сообщения лента переходит вниз.
- Indicator новых сообщений исчезает после перехода вниз.

**Проверка:**

- Ручная проверка длинной истории.
- Playwright test на scroll position при incoming update.

### Этап 8. Chat Auto Rename After First Message

**Задачи:**

- Зафиксировать целевой контракт: новый чат создается с техническим/пустым именем, после первого user message backend генерирует title и отправляет событие `chat_title`.
- Проверить существующий backend flow генерации title:
  - когда генерируется;
  - только ли для первого сообщения;
  - что происходит при ошибке генерации;
  - есть ли persistence в `chats.name`.
- Проверить frontend handling `chat_title`.
- Исправить query key mismatch, если cache update использует ключ не через `qk.chats.list(...)`.
- После получения `chat_title` обновлять sidebar без полного визуального мигания списка.
- Если SSE событие потеряно, sidebar должен получить новое имя после invalidate/refetch.
- Не переименовывать чат повторно после следующих сообщений, если пользователь уже переименовал его вручную.

**Критерии выполнения:**

- Новый чат после первого сообщения получает осмысленное название.
- Название видно в sidebar без refresh страницы.
- После reload название сохранено.
- Второе и последующие сообщения не перетирают ручное название.
- Ошибка title generation не ломает отправку сообщения.

**Проверка:**

- Unit/integration backend test:
  - first message triggers title generation;
  - title persisted;
  - manual title is not overwritten.
- Frontend test:
  - mock `chat_title` event updates sidebar cache;
  - fallback refetch updates sidebar if event missed.
- Manual:
  - создать новый чат;
  - отправить первое сообщение;
  - увидеть rename в sidebar;
  - обновить страницу;
  - убедиться, что rename сохранился.

### Этап 9. Cleanup

**Задачи:**

- Удалить неиспользуемые imports из `Chat.tsx`.
- Удалить неиспользуемый `id` prop из `ChatMessage`, если он не нужен для analytics/test ids.
- Удалить или применить `OptimizedChatMessage.tsx`.
- Убрать устаревшие CSS comments, которые не помогают сопровождению.
- Свести chat CSS к понятным слоям:
  - layout;
  - message;
  - markdown;
  - composer;
  - runtime controls.

**Критерии выполнения:**

- Нет неиспользуемого frontend-кода в chat domain.
- Нет двух конкурирующих message components.
- CSS не содержит legacy styles для удаленных элементов.
- Type-check и lint проходят.

## 5. Definition of Done

- `pnpm run type-check` проходит в `apps/web`.
- `pnpm run lint` проходит в `apps/web`.
- Unit tests для message rendering и composer cleanup проходят.
- Playwright/manual smoke покрывает:
  - empty chat;
  - normal message;
  - long markdown answer;
  - code block;
  - table;
  - RAG sources;
  - attachments;
  - streaming abort;
  - waiting input;
  - confirmation prompt;
  - auto rename after first message.
- React Profiler не показывает массовый rerender старых сообщений при streaming.
- На desktop и mobile нет horizontal overflow страницы.

## 6. Рекомендуемый порядок PR

1. Message layout + markdown rendering.
2. Structured blocks fallback + tests.
3. Composer cleanup + accessibility.
4. Smart scroll.
5. Streaming render performance.
6. Chat state boundaries.
7. Auto rename after first message.
8. Cleanup.

## 7. Риски

- Изменение markdown profile может поменять внешний вид старых ответов в истории.
- Удаление тяжелого assistant bubble может раскрыть проблемы с шириной таблиц/кода в существующем CSS.
- Разделение state boundaries может затронуть sidebar/status behavior.
- Auto rename зависит от backend contract; перед frontend-фиксами нужно подтвердить, что title сохраняется на backend.

## 8. Не принимаем как Done

- "Выглядит лучше" без проверки markdown/table/code fixtures.
- Оптимизация без React Profiler.
- Auto rename только в UI cache без persistence.
- Fallback на полный refetch при каждом streaming/status event.
- Новый визуальный стиль, который не совпадает с рабочим характером портала.
