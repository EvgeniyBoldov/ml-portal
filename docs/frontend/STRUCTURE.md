# Структура Frontend

## Общая структура

```
apps/web/src/
├── main.tsx                 # Entry point
├── theme.css                # Global CSS variables
├── vite-env.d.ts           # Vite types
│
├── app/                     # Application layer
│   ├── AppProviders.tsx     # Provider tree
│   ├── router.tsx           # React Router config
│   ├── providers/           # Global providers
│   │   ├── SSEProvider.tsx
│   │   └── applyRagEvents.ts
│   └── store/               # Global Zustand stores
│       ├── app.store.ts
│       └── useChatStore.ts
│
├── domains/                 # Feature domains
│   ├── admin/               # Admin panel
│   │   ├── pages/
│   │   ├── components/
│   │   └── hooks/
│   ├── auth/                # Authentication
│   ├── chat/                # Chat interface
│   ├── rag/                 # RAG documents
│   ├── collections/         # Collections
│   ├── gpt/                 # Main GPT interface
│   └── profile/             # User profile
│
├── shared/                  # Shared code
│   ├── api/                 # API layer
│   │   ├── http.ts          # HTTP client
│   │   ├── keys.ts          # Query key factory
│   │   ├── hooks/           # React Query hooks
│   │   ├── agents.ts
│   │   ├── prompts.ts
│   │   ├── rag.ts
│   │   └── ...
│   ├── ui/                  # UI components
│   │   ├── Button.tsx
│   │   ├── Input.tsx
│   │   ├── Modal.tsx
│   │   ├── DataTable/
│   │   ├── EntityPage/
│   │   └── ...
│   ├── hooks/               # Shared hooks
│   ├── lib/                 # Utilities
│   │   ├── sse.ts
│   │   ├── format.ts
│   │   └── ...
│   ├── config.ts            # App config
│   └── schemas/             # Zod schemas
│
├── entities/                # Domain entities
│   └── auth/
│       └── model/
│           └── auth.store.ts
│
└── test/                    # Test utilities
```

## Domain Structure

Каждый домен следует структуре:

```
domains/admin/
├── pages/                   # Route pages
│   ├── AgentsPage.tsx
│   ├── AgentEditorPage.tsx
│   ├── PromptsPage.tsx
│   └── ...
├── components/              # Domain components
│   ├── AgentCard.tsx
│   └── ...
└── hooks/                   # Domain hooks
    └── useAgentForm.ts
```

## Shared UI Structure

```
shared/ui/
├── index.ts                 # Barrel export
├── Button.tsx
├── Button.module.css
├── Input.tsx
├── Input.module.css
├── Modal/
│   ├── Modal.tsx
│   ├── Modal.module.css
│   └── index.ts
├── DataTable/
│   ├── DataTable.tsx
│   ├── DataTable.module.css
│   └── index.ts
├── EntityPage/
│   ├── EntityPage.tsx
│   ├── EntityPage.module.css
│   └── index.ts
└── ...
```

## API Layer Structure

```
shared/api/
├── http.ts                  # Base HTTP client
├── keys.ts                  # Query key factory
├── index.ts                 # Barrel export
├── hooks/                   # React Query hooks
│   ├── useAdmin.ts
│   ├── useRagDocuments.ts
│   └── ...
├── agents.ts                # Agents API
├── prompts.ts               # Prompts API
├── rag.ts                   # RAG API
├── permissions.ts           # Permissions API
├── toolInstances.ts         # Tool Instances API
└── ...
```

## Naming Conventions

| Тип | Формат | Пример |
|-----|--------|--------|
| Компоненты | PascalCase | `AgentCard.tsx` |
| Hooks | camelCase с use | `useAgentForm.ts` |
| CSS Modules | kebab-case | `agent-card.module.css` |
| Utilities | camelCase | `formatDate.ts` |
| Constants | UPPER_SNAKE | `DEFAULT_PAGE_SIZE` |
| Types/Interfaces | PascalCase | `AgentResponse` |

## Import Aliases

```typescript
// tsconfig paths
{
  "@shared/*": ["src/shared/*"],
  "@domains/*": ["src/domains/*"],
  "@app/*": ["src/app/*"],
  "@entities/*": ["src/entities/*"]
}

// Usage
import { Button } from '@shared/ui';
import { agentsApi } from '@shared/api';
import { AgentsPage } from '@domains/admin/pages';
```

## File Organization Rules

1. **Один компонент = один файл**
2. **Компоненты < 250 строк** — выносить в подкомпоненты
3. **CSS только в .module.css** — никаких inline styles
4. **Index файлы только для barrel exports** — не прятать логику
5. **Hooks рядом с компонентами** — если используются только там
