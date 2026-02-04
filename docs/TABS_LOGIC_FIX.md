# Tabs Logic Fix - Admin Pages Architecture

## 🎯 **Проблема**
Неправильная логика табов в админских страницах после рефакторинга.

## 📋 **Правильная логика табов по режимам:**

### **Create Mode (Создание)**
```
┌─────────────────────────────────┐
│         Entity Info             │
│  - Все поля редактируемые      │
│  - Slug доступен для редакта   │
│  - Нет табов с версиями        │
└─────────────────────────────────┘
```

### **Edit Mode (Редактирование)**
```
┌─────────────────────────────────┐
│  [Обзор]  [Версии]  [Настройки] │
├─────────────────────────────────┤
│ Entity Info (slug НЕ редакт.)   │
│ - Основная информация          │
│ - Статус контейнера            │
└─────────────────────────────────┘
```

### **View Mode (Просмотр)**
```
┌─────────────────────────────────┐
│  [Обзор]  [Версии]  [Настройки] │
├─────────────────────────────────┤
│ Entity Info (только чтение)     │
│ - Основная информация          │
│ - Статус контейнера            │
└─────────────────────────────────┘
```

## 🏗️ **Архитектура по типам сущностей:**

### **Policy (естественно имеет табы)**
```
Create Mode: EntityInfoBlock (без табов)
Edit Mode:   TabsLayout(Overview + Versions)
View Mode:   TabsLayout(Overview + Versions)
```

### **Prompt (split layout)**
```
Create Mode: EntityInfoBlock (без табов)
Edit Mode:   SplitLayout(EntityInfoBlock + VersionsBlock)
View Mode:   TabsLayout(Overview(SplitLayout) + Versions)
```

### **Baseline (split layout)**
```
Create Mode: EntityInfoBlock (без табов)
Edit Mode:   SplitLayout(EntityInfoBlock + VersionsBlock)
View Mode:   TabsLayout(Overview(SplitLayout) + Versions)
```

## 🔄 **Навигация между версиями:**

### **From Entity Page → Version Page**
```
Policy Editor → Versions Tab → "Подробнее" → PolicyVersionPage
Prompt Editor → Versions Tab → "Подробнее" → PromptVersionPage
Baseline Editor → Versions Tab → "Подробнее" → BaselineVersionPage
```

### **Version Page Logic**
```
View Mode: Показать версию + кнопка "Редактировать"
Edit Mode: Редактирование версии
Create Mode: Создание новой версии
```

## 🎯 **Исправления в коде:**

### **1. PolicyEditorPage**
```tsx
{isCreate ? (
  // Create mode - без табов
  <EntityInfoBlock />
) : (
  // Edit/View modes - с табами
  <TabsLayout tabs={[Overview, Versions]} />
)}
```

### **2. PromptEditorPage**
```tsx
{isNew ? (
  // Create mode - без табов
  <EntityInfoBlock />
) : isEditMode ? (
  // Edit mode - split layout
  <SplitLayout left={EntityInfoBlock} right={VersionsBlock} />
) : (
  // View mode - tabs с split внутри
  <TabsLayout tabs={[
    { id: 'overview', content: <SplitLayout /> },
    { id: 'versions', content: <VersionsBlock /> }
  ]} />
)}
```

### **3. BaselineEditorPage**
```tsx
{isCreate ? (
  // Create mode - без табов
  <EntityInfoBlock />
) : isEditMode ? (
  // Edit mode - split layout
  <SplitLayout left={EntityInfoBlock} right={VersionsBlock} />
) : (
  // View mode - tabs с split внутри
  <TabsLayout tabs={[
    { id: 'overview', content: <SplitLayout /> },
    { id: 'versions', content: <VersionsBlock /> }
  ]} />
)}
```

## 🔧 **Ключевые моменты:**

### **Slug Field Logic**
```tsx
const fields = isCreate ? [
  { key: 'slug', disabled: false }  // Create - можно редактировать
] : [
  { key: 'slug', disabled: true }   // Edit/View - только чтение
];
```

### **Create Button Logic**
```tsx
showCreateButton={isEditable}  // Только в edit режиме
```

### **Status Context**
```tsx
// Policy - статус контейнера
status={formData.is_active ? 'active' : 'inactive'}

// Prompt/Baseline - статус версии
status={selectedVersion?.status}
```

## 📊 **Сравнение до/после:**

| Компонент | Create | Edit | View |
|-----------|--------|------|------|
| **Policy** | EntityInfo | Tabs | Tabs |
| **Prompt** | EntityInfo | Split | Tabs(Split) |
| **Baseline** | EntityInfo | Split | Tabs(Split) |

## 🎯 **Результат:**
1. **Create mode** - чистый, без лишних табов
2. **Edit mode** - логичный split для prompt/baseline, tabs для policy  
3. **View mode** - консистентные tabs везде
4. **Slug** - правильно блокируется в edit/view
5. **Навигация** - понятный flow между страницами

**Логика табов теперь соответствует ожиданиям пользователя!** 🚀
