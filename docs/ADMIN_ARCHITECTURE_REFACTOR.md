# Admin Architecture Refactor

## Overview

Complete refactor of admin pages using unified layout system with reusable components.

## Architecture

### Layout System

#### BaseLayout Components
- **BaseLayout** - Root container with layout type
- **SplitLayout** - Two-column layout (Prompt/Baseline)
- **TabsLayout** - Tabbed interface (Policy)

#### Reusable Blocks
- **EntityInfoBlock** - Entity metadata with optional status
- **VersionsBlock** - Version list with actions
- **StatusBlock** - Status display with badge and actions

### Page Patterns

#### Prompt/Baseline Pages
```
Create Mode: EntityInfoBlock
Edit Mode: SplitLayout(EntityInfoBlock + VersionsBlock)  
View Mode: Tabs(Overview(SplitLayout) + Versions(VersionsBlock))
```

#### Policy Pages
```
Create Mode: EntityInfoBlock
Edit/View Mode: TabsLayout(Overview(EntityInfoBlock) + Versions(VersionsBlock))
```

## Status Management

### useStatusConfig Hook
Centralized status configuration for all entity types:
```typescript
const statusConfig = useStatusConfig('prompt' | 'baseline' | 'policy');
// statusConfig.labels[status] - display labels
// statusConfig.tones[status] - badge tones
```

### Status Context
- **Prompt/Baseline**: Status belongs to version
- **Policy**: Status belongs to container (is_active) + version status

## Component Structure

### EntityInfoBlock
- Left column: Entity fields (name, slug, description)
- Right column: Status badge (when showStatus=true)
- Uses flexbox layout for proper alignment
- Responsive: stacks vertically on mobile

### VersionsBlock
- Full width version list
- Built-in DataTable with status badges
- Action buttons per version (view, activate, archive, delete)
- Create new version button

### StatusBlock
- Compact mode: badge + version number
- Full mode: badge + metadata + actions
- Used within EntityInfoBlock

## CSS Architecture

### Flexbox over Grid
- EntityInfoBlock uses flexbox for two-column layout
- Proper alignment with `align-items: flex-start`
- Mobile responsive with flex-direction: column

### CSS Variables
All components use theme variables:
- `--bg-primary`, `--text-primary`, `--border-color`
- `--spacing-sm`, `--spacing-md`, `--spacing-lg`

## Migration Results

### Before (1000+ lines)
- 3 pages with different architectures
- Duplicated STATUS constants
- Manual ContentGrid layouts
- Inline DataTable implementations

### After (~500 lines)
- 3 pages with unified architecture
- 1 useStatusConfig hook
- Reusable components
- Consistent styling

## Benefits

1. **Consistency** - All pages look and behave the same
2. **Maintainability** - Changes in one place affect all pages
3. **Extensibility** - New pages can use existing components
4. **Type Safety** - Full TypeScript coverage
5. **Responsive** - Mobile-friendly layouts

## Usage Examples

### Create New Entity Page
```tsx
<EntityInfoBlock
  entity={formData}
  entityType="prompt"
  editable={true}
  fields={fields}
  onFieldChange={handleChange}
/>
```

### Split Layout for Edit Mode
```tsx
<SplitLayout
  left={<EntityInfoBlock />}
  right={<VersionsBlock />}
/>
```

### Tabs Layout for Policy
```tsx
<TabsLayout
  tabs={[
    { id: 'overview', content: <EntityInfoBlock /> },
    { id: 'versions', content: <VersionsBlock /> }
  ]}
/>
```

## File Structure

```
src/shared/ui/
├── BaseLayout/
│   ├── BaseLayout.tsx
│   ├── BaseLayout.module.css
│   └── index.ts
├── EntityInfoBlock/
│   ├── EntityInfoBlock.tsx
│   ├── EntityInfoBlock.module.css
│   └── index.ts
├── VersionsBlock/
│   ├── VersionsBlock.tsx
│   ├── VersionsBlock.module.css
│   └── index.ts
├── StatusBlock/
│   ├── StatusBlock.tsx
│   ├── StatusBlock.module.css
│   └── index.ts
└── hooks/
    └── useStatusConfig.ts
```

## Future Enhancements

1. **Tool/Model Pages** - Apply same pattern
2. **Advanced Filtering** - Add to VersionsBlock
3. **Bulk Actions** - Multi-select in VersionsBlock
4. **Real-time Updates** - SSE integration for status changes
5. **Accessibility** - ARIA labels and keyboard navigation
