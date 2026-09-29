import { useState } from 'react';
import { Button, DropdownMenu, type DropdownMenuItem } from '@/shared/ui';

type Props = {
  items: DropdownMenuItem[];
  label?: string;
  ariaLabel?: string;
  disabled?: boolean;
};

export default function MemoryActionsMenu({ items, label = 'Действия', ariaLabel, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ x: number; y: number } | null>(null);

  return <>
    <Button type="button" size="sm" variant="outline" aria-label={ariaLabel ?? label}
      aria-haspopup="menu" aria-expanded={open} disabled={disabled}
      onClick={(event) => {
        event.stopPropagation();
        const rect = event.currentTarget.getBoundingClientRect();
        setPosition({ x: Math.max(8, Math.min(rect.left, window.innerWidth - 184)), y: rect.bottom + 4 });
        setOpen((current) => !current);
      }}>
      {label}{label === 'Действия' ? ' ▾' : ''}
    </Button>
    <DropdownMenu items={items} isOpen={open} onClose={() => setOpen(false)} anchorPosition={position ?? undefined} />
  </>;
}
