# Masonry Grid Layout System

## Overview

Advanced auto-adjusting grid layout that efficiently fills space with blocks of different heights. Similar to Masonry layout but with CSS Grid implementation.

## Key Features

### 🏗️ Auto-Height Adjustment
- Blocks automatically stretch to match tallest block in row
- Left block 10 cells + right blocks 2×6 cells → left stretches to 12 cells
- Perfect square/rectangle formation

### 📐 Flexible Sizing
- **Constraints**: 1/2, 1/3, 2/3 as maximum limits
- **Auto-fit**: Blocks fill available space efficiently
- **Responsive**: Adapts to screen size automatically

### 🎯 Smart Grid Algorithm
```css
grid-template-columns: repeat(
  auto-fit,
  minmax(min(var(--min-col-width, 300px), 100% / var(--max-cols, 4)), 1fr)
);
```

## Usage Examples

### Basic Masonry Grid
```tsx
<MasonryGrid gap="md" minColWidth={280} maxCols={2}>
  <ContentBlock title="Block 1">Content 1</ContentBlock>
  <ContentBlock title="Block 2">Content 2</ContentBlock>
  <ContentBlock title="Block 3">Content 3</ContentBlock>
</MasonryGrid>
```

### EntityInfoBlock with Auto-Adjustment
```tsx
<EntityInfoBlock
  entity={entity}
  entityType="prompt"
  showStatus={true}
  status="active"
>
  {/* Auto-adjusts: 
   - Left: Entity info (stretches to match status height)
   - Right: Status block
  */}
</EntityInfoBlock>
```

### Three-Column Layout
```tsx
<MasonryGrid 
  gap="lg" 
  minColWidth={250} 
  maxCols={3}
  data-layout="three-column"
>
  <Block height="small" />  {/* Stretches to medium */}
  <Block height="medium" />
  <Block height="large" />  {/* Stays large */}
</MasonryGrid>
```

## Layout Patterns

### Two-Column (EntityInfoBlock)
```
┌─────────────────┬─────────┐
│   Entity Info   │ Status  │ ← Status stretches
│   (10 cells)    │ (6)     │   to match height
│                 │         │
│                 │         │
└─────────────────┴─────────┘
```

### Three-Column Auto-Balance
```
┌─────────┬─────────┬─────────┐
│ Block 1 │ Block 2 │ Block 3 │
│ (8)     │ (6)     │ (10)    │ ← Block 1 stretches
│         │         │         │   to 10 cells
└─────────┴─────────┴─────────┘
```

## CompactStatusBlock

### Inline Status Display
Like ToolsGroup - label and value inline without header:

```tsx
<CompactStatusBlock
  label="Status"
  value="Active"
  tone="success"
  inline={true}
/>
```

### Card Status Display
```tsx
<CompactStatusBlock
  label="Health"
  value="Healthy"
  tone="success"
/>
```

## CSS Variables

### Grid Configuration
```css
--min-col-width: 300px;  /* Minimum column width */
--max-cols: 4;           /* Maximum columns */
```

### Responsive Breakpoints
```css
/* Mobile: 1 column */
@media (max-width: 768px) {
  grid-template-columns: 1fr;
}

/* Tablet: 2 columns for 3-col layout */
@media (max-width: 1024px) {
  [data-layout="three-column"] {
    grid-template-columns: 1fr 1fr;
  }
}
```

## Animation System

### Staggered Fade-In
```css
.masonryGrid > * {
  animation: fadeInUp 0.3s ease-out forwards;
  opacity: 0;
}

.masonryGrid > *:nth-child(1) { animation-delay: 0.05s; }
.masonryGrid > *:nth-child(2) { animation-delay: 0.1s; }
/* ... */
```

## Performance Benefits

### ✅ Efficient Space Usage
- No empty gaps
- Perfect rectangles
- Maximum content density

### ✅ Responsive Design
- Auto-adapts to screen size
- Maintains proportions
- Mobile-first approach

### ✅ Developer Experience
- Simple configuration
- Predictable behavior
- Type-safe props

## Comparison with Other Layouts

| Feature | MasonryGrid | Flexbox | CSS Grid Manual |
|---------|-------------|---------|----------------|
| Auto-height | ✅ | ❌ | ❌ |
| Space efficiency | ✅ | ❌ | ⚠️ |
| Responsive | ✅ | ✅ | ⚠️ |
| Complexity | Low | Medium | High |

## Migration from Flexbox

### Before (Flexbox)
```tsx
<div style={{ display: 'flex', gap: '1rem' }}>
  <div style={{ flex: 2 }}>Content</div>
  <div style={{ flex: 1 }}>Status</div>
</div>
```

### After (MasonryGrid)
```tsx
<MasonryGrid gap="md" maxCols={2}>
  <ContentBlock>Content</Content>
  <StatusBlock>Status</StatusBlock>
</MasonryGrid>
```

## Best Practices

### 🎯 Use Cases
- **Entity pages**: Info + status blocks
- **Dashboards**: Mixed content heights
- **Card layouts**: Variable content
- **Admin panels**: Form + sidebar

### ⚠️ Avoid
- **Fixed height content**: Use regular grid
- **Simple two-column**: Flexbox might be simpler
- **Tabular data**: Use Table component

### 🔧 Configuration Tips
```tsx
// For entity pages
minColWidth={280}
maxCols={2}

// For dashboards
minColWidth={300}
maxCols={4}

// For mobile-first
minColWidth={100}
maxCols={1}
```

## Future Enhancements

1. **Dynamic minColWidth** based on content
2. **Drag-and-drop** reordering
3. **Virtual scrolling** for large grids
4. **Grid templates** for common patterns
5. **Accessibility** improvements
