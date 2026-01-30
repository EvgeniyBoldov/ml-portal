# Правила разработки Frontend

## Общие принципы

1. **TypeScript strict mode** — никаких `any`, полная типизация
2. **CSS Modules** — никаких inline styles, styled-components, Tailwind
3. **Компоненты из shared/ui** — не создавать дубликаты
4. **Максимум 250 строк** — разбивать большие компоненты

## Компоненты

### Структура компонента

```tsx
// 1. Imports
import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@shared/ui';
import styles from './MyComponent.module.css';

// 2. Types
interface MyComponentProps {
  id: string;
  onSave: (data: FormData) => void;
}

// 3. Component
export function MyComponent({ id, onSave }: MyComponentProps) {
  // Hooks first
  const [state, setState] = useState('');
  const { data, isLoading } = useQuery(...);
  
  // Handlers
  const handleSubmit = () => {
    onSave(data);
  };
  
  // Early returns
  if (isLoading) return <Skeleton />;
  
  // Render
  return (
    <div className={styles.container}>
      ...
    </div>
  );
}
```

### Правила именования

```tsx
// Props interface = ComponentName + Props
interface AgentCardProps { ... }

// Event handlers = handle + Event
const handleClick = () => { ... };
const handleSubmit = () => { ... };

// Boolean props = is/has/should prefix
interface Props {
  isLoading: boolean;
  hasError: boolean;
  shouldAutoFocus: boolean;
}
```

## CSS Modules

### Naming

```css
/* kebab-case для классов */
.container { }
.header-title { }
.action-button { }

/* Модификаторы через -- */
.button--primary { }
.button--disabled { }
```

### Структура файла

```css
/* 1. Container/wrapper */
.container { }

/* 2. Layout elements */
.header { }
.content { }
.footer { }

/* 3. Components */
.title { }
.button { }

/* 4. States/modifiers */
.container--loading { }
.button--disabled { }

/* 5. Responsive */
@media (max-width: 768px) { }
```

## React Query

### Query Keys

**ВСЕГДА** использовать фабрику `qk` из `@shared/api/keys.ts`:

```tsx
// ✅ Правильно
const { data } = useQuery({
  queryKey: qk.agents.list(),
  queryFn: () => agentsApi.list(),
});

// ❌ Неправильно
const { data } = useQuery({
  queryKey: ['agents', 'list'],  // Hardcoded!
  queryFn: () => agentsApi.list(),
});
```

### Mutations

```tsx
const mutation = useMutation({
  mutationFn: (data: AgentCreate) => agentsApi.create(data),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: qk.agents.all });
    showSuccess('Агент создан');
  },
  onError: () => {
    showError('Ошибка создания агента');
  },
});
```

### Query Options

```tsx
// Default options в QueryClient
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,      // 30 seconds
      gcTime: 5 * 60_000,     // 5 minutes
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
```

## Zustand

### Только для UI state

```tsx
// ✅ Правильно — UI state
const useAppStore = create((set) => ({
  sidebarOpen: false,
  selectedItems: [],
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
}));

// ❌ Неправильно — серверные данные
const useAgentsStore = create((set) => ({
  agents: [],  // Должно быть в React Query!
  fetchAgents: async () => { ... },
}));
```

## Формы

### Controlled inputs

```tsx
const [formData, setFormData] = useState<FormData>({
  name: '',
  description: '',
});

const handleChange = (field: keyof FormData) => (
  e: React.ChangeEvent<HTMLInputElement>
) => {
  setFormData((prev) => ({ ...prev, [field]: e.target.value }));
};

return (
  <Input
    value={formData.name}
    onChange={handleChange('name')}
  />
);
```

### Validation

```tsx
const validate = (data: FormData): Record<string, string> => {
  const errors: Record<string, string> = {};
  
  if (!data.name.trim()) {
    errors.name = 'Название обязательно';
  }
  
  if (data.name.length > 100) {
    errors.name = 'Максимум 100 символов';
  }
  
  return errors;
};
```

## Accessibility

### Обязательные атрибуты

```tsx
// Кнопки с иконками
<Button aria-label="Удалить" onClick={handleDelete}>
  <Icon name="trash" />
</Button>

// Модальные окна
<Modal
  aria-labelledby="modal-title"
  aria-describedby="modal-description"
>
  <h2 id="modal-title">Заголовок</h2>
  <p id="modal-description">Описание</p>
</Modal>

// Формы
<label htmlFor="name">Название</label>
<Input id="name" aria-required="true" />
```

### Keyboard navigation

- `Escape` закрывает модалки/поповеры
- `Tab` для навигации
- `Enter` для подтверждения
- Focus trap в модалках

## Imports

### Порядок импортов

```tsx
// 1. React
import React, { useState, useEffect } from 'react';

// 2. Third-party
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';

// 3. Shared
import { Button, Input } from '@shared/ui';
import { agentsApi } from '@shared/api';
import { qk } from '@shared/api/keys';

// 4. Domain
import { AgentCard } from '../components';

// 5. Local
import styles from './AgentsPage.module.css';
```

## Error Handling

### API errors

```tsx
const { data, error, isError } = useQuery({
  queryKey: qk.agents.detail(id),
  queryFn: () => agentsApi.get(id),
});

if (isError) {
  return <ErrorMessage error={error} />;
}
```

### Error boundaries

```tsx
<ErrorBoundary fallback={<ErrorFallback />}>
  <AgentEditor />
</ErrorBoundary>
```

## Testing

### Unit tests

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AgentCard } from './AgentCard';

describe('AgentCard', () => {
  it('renders agent name', () => {
    render(<AgentCard agent={mockAgent} />);
    expect(screen.getByText(mockAgent.name)).toBeInTheDocument();
  });
  
  it('calls onEdit when edit button clicked', async () => {
    const onEdit = vi.fn();
    render(<AgentCard agent={mockAgent} onEdit={onEdit} />);
    
    await userEvent.click(screen.getByRole('button', { name: /edit/i }));
    
    expect(onEdit).toHaveBeenCalledWith(mockAgent.id);
  });
});
```
