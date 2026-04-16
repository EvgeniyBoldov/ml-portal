# Entity Builder Pattern

## 🎯 Концепция

**Entity Builder Pattern** - это архитектурный подход для построения UI на основе сущностей с переиспользуемыми блоками и формами.

### 🏗️ Основная идея

```
Entity (данные) → Forms (определения) → Blocks (блоки) → Pages (страницы)
```

- **Entity** - чистая бизнес-модель сущности
- **Forms** - описания полей для отображения
- **Blocks** - стилизованные блоки на основе ContentBlock
- **Pages** - компоновка блоков по tab'ам

---

## 📋 Структура

```
📁 shared/
├── 📁 interfaces/
│   ├── 📁 entities/           # Entity интерфейсы
│   │   ├── Agent.interface.ts
│   │   ├── RbacRule.interface.ts
│   │   ├── Limit.interface.ts
│   │   └── index.ts
│   └── 📁 forms/              # Form definitions
│       ├── AgentForms.ts
│       ├── RbacRuleForms.ts
│       ├── LimitForms.ts
│       └── index.ts
│
├── 📁 ui/
│   ├── 📁 atoms/              # Atomic компоненты (Input, Select, Badge...)
│   ├── 📁 blocks/             # Base блоки (ContentBlock, EntityInfoBlock...)
│   ├── 📁 builders/           # Builder компоненты
│   │   ├── EntityBuilder/
│   │   └── FormBuilder/
│   └── 📁 entity-blocks/      # Ready-to-use Entity блоки
│       ├── AgentBlocks/
│       ├── RbacBlocks/
│       ├── LimitBlocks/
│       └── index.ts
│
└── 📁 mappers/               # API ↔ Entity конвертеры
    ├── Agent.mapper.ts
    ├── RbacRule.mapper.ts
    ├── Limit.mapper.ts
    └── index.ts
```

---

## 🎯 Компоненты

### 1. Entity Interface

Чистый TypeScript интерфейс сущности:

```typescript
// shared/interfaces/entities/Limit.interface.ts
export interface Limit {
  id: string;
  name: string;
  description?: string;
  type: 'token' | 'request' | 'time';
  value: number;
  period?: 'minute' | 'hour' | 'day';
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
```

### 2. Form Definition

Описание полей для отображения:

```typescript
// shared/interfaces/forms/LimitForms.ts
export const LimitInfoForm: FormDefinition[] = [
  {
    key: 'name',
    type: 'input',
    label: 'Название',
    required: true,
    placeholder: 'Например: API Rate Limit',
  },
  {
    key: 'description',
    type: 'textarea',
    label: 'Описание',
    rows: 2,
    placeholder: 'Описание лимита...',
  },
  {
    key: 'type',
    type: 'select',
    label: 'Тип лимита',
    options: [
      { value: 'token', label: 'Токены' },
      { value: 'request', label: 'Запросы' },
      { value: 'time', label: 'Время' },
    ],
  },
  {
    key: 'value',
    type: 'number',
    label: 'Значение',
    required: true,
  },
  {
    key: 'is_active',
    type: 'switch',
    label: 'Активен',
  },
];
```

### 3. Entity Block

Готовый блок на основе ContentBlock:

```typescript
// shared/ui/entity-blocks/LimitBlocks/LimitInfoBlock.tsx
export function LimitInfoBlock({ 
  limit, 
  mode, 
  onChange 
}: LimitInfoBlockProps) {
  return (
    <ContentBlock
      title="Основная информация"
      icon="gauge"
      iconVariant="info"
      width="1/2"
      editable={mode === 'edit'}
      fields={LimitInfoForm}
      data={limit}
      onChange={onChange}
    />
  );
}
```

### 4. Mapper

Конвертация API в Entity:

```typescript
// shared/mappers/Limit.mapper.ts
export class LimitMapper {
  static fromApi(apiLimit: ApiLimit): Limit {
    return {
      id: apiLimit.id,
      name: apiLimit.name,
      description: apiLimit.description,
      type: apiLimit.type,
      value: apiLimit.value,
      period: apiLimit.period,
      is_active: apiLimit.is_active,
      created_at: apiLimit.created_at,
      updated_at: apiLimit.updated_at,
    };
  }

  static toApi(limit: Partial<Limit>): Partial<ApiLimit> {
    return {
      name: limit.name,
      description: limit.description,
      type: limit.type,
      value: limit.value,
      period: limit.period,
      is_active: limit.is_active,
    };
  }
}
```

---

## 🔄 Использование в Pages

### Старый подход (много кода):
```typescript
// ❌ 200+ строк логики в компоненте
const [formData, setFormData] = useState({...});
const handleFieldChange = (key, value) => {...};
const handleSubmit = async () => {...};
// ... много boilerplate
```

### Новый подход (минимум кода):
```typescript
// ✅ 20 строк - только data fetching
export function LimitPage() {
  const { slug } = useParams<{ slug: string }>();
  const mode = getEditMode();
  
  const { data: apiLimit } = useQuery({
    queryKey: qk.limits.detail(slug!),
    queryFn: () => limitsApi.get(slug!),
  });
  
  const limit = apiLimit ? LimitMapper.fromApi(apiLimit) : null;
  
  return (
    <EntityPageV2 title="Лимит" mode={mode}>
      <Tab title="Обзор" layout="grid">
        <LimitInfoBlock 
          limit={limit} 
          mode={mode} 
          onChange={handleChange} 
        />
        <LimitMetaBlock limit={limit} />
      </Tab>
    </EntityPageV2>
  );
}
```

---

## 🎯 Преимущества

### 1. **Минимум кода в Pages**
Pages только для data fetching и навигации

### 2. **Переиспользование**
- Forms можно комбинировать в разных блоках
- Blocks можно использовать в разных контекстах
- Entity можно отображать по-разному

### 3. **Консистентность**
- Все блоки используют ContentBlock
- Единый стиль и поведение
- Стандартные атомарные компоненты

### 4. **Гибкость**
```typescript
// Для карточек в экспериментах
export function LimitCard({ limit }: { limit: Limit }) {
  return (
    <Card>
      <LimitCompactBlock limit={limit} mode="view" />
    </Card>
  );
}

// Для таблиц
export function LimitTableRow({ limit }: { limit: Limit }) {
  return <LimitInlineBlock limit={limit} mode="view" />;
}
```

### 5. **Централизованные изменения**
- Изменили Entity - обновились все формы
- Изменили Form - обновились все блоки
- Изменили Block - обновились все страницы

---

## 🚀 Пилот: Limits

Первый пилотный проект - **Limits**:

1. **Создать Entity Interface** - `Limit.interface.ts`
2. **Создать Form Definitions** - `LimitForms.ts`
3. **Создать Entity Blocks** - `LimitInfoBlock`, `LimitMetaBlock`
4. **Создать Mapper** - `Limit.mapper.ts`
5. **Переделать LimitPage** - использовать новые блоки

### Почему Limits?
- ✅ Простая структура (5-7 полей)
- ✅ Уже есть страница для рефакторинга
- ✅ Не сложная бизнес-логика
- ✅ Хороший пример для паттерна

---

## 📋 Правила разработки

### 1. **Entity Interface**
- Только бизнес-поля, без UI примесей
- Вычисляемые поля (displayName, isActive)
- Строгая типизация

### 2. **Form Definition**
- Описание полей для отображения
- Валидация и required поля
- Options для select полей
- Custom render для сложных компонентов

### 3. **Entity Block**
- На основе ContentBlock
- Использует EntityBuilder или FormBuilder
- Принимает Entity и mode
- Передает onChange наверх

### 4. **Mapper**
- fromApi: API → Entity
- toApi: Entity → API  
- Чистые функции, без side effects

### 5. **Page**
- Только data fetching
- Компоновка блоков по tab'ам
- Минимум логики

---

## 🎯 Roadmap

### Phase 1: Pilot (Limits)
- [ ] Limit Interface
- [ ] Limit Forms  
- [ ] Limit Blocks
- [ ] Limit Mapper
- [ ] Refactor LimitPage

### Phase 2: Expand (RbacRule)
- [ ] RbacRule Interface
- [ ] RbacRule Forms
- [ ] RbacRule Blocks
- [ ] RbacRule Mapper
- [ ] Refactor RbacRulePage

### Phase 3: Scale (Agent, Tenant, etc.)
- [ ] Agent Interface + Forms + Blocks
- [ ] Tenant Interface + Forms + Blocks
- [ ] Другие сущности

---

## 🔄 Migration Strategy

1. **Создаем новую структуру** параллельно со старой
2. **Пилот на Limits** - проверяем подход
3. **Постепенный рефактор** - одна сущность за раз
4. **Удаление старого кода** - после полной миграции

---

## 📝 Notes

- **Не ломает доменный подход** - усиливает его
- **Сохраняет границы** - domain vs presentation  
- **Масштабируемо** - легко добавлять новые сущности
- **Поддерживаемо** - централизованные изменения

---

*Created: 2026-02-17*
*Status: Draft - Pilot Phase*
