import React, { useState } from 'react';
import Popover from '@shared/ui/Popover';
import styles from './RoundButton.module.css';

export interface RoundButtonAction {
  label: string;
  disabled?: boolean;
  onClick: () => void;
}

export interface RoundButtonProps {
  /** Button text/content */
  text: string;
  /** Button color variant */
  color: 'green' | 'blue' | 'gray' | 'red' | 'yellow';
  /** Tooltip text */
  tooltip?: string;
  /** Dropdown actions */
  actions?: RoundButtonAction[];
  /** Additional CSS classes */
  className?: string;
  /** Click handler for the button itself */
  onClick?: (event: React.MouseEvent) => void;
  /** Button size */
  size?: 'sm' | 'md' | 'lg';
  /** Whether to show animated spinner for blue color */
  animated?: boolean;
}

const getColorClass = (color: RoundButtonProps['color']) => {
  switch (color) {
    case 'green':
      return styles.green;
    case 'blue':
      return styles.blue;
    case 'gray':
      return styles.gray;
    case 'red':
      return styles.red;
    case 'yellow':
      return styles.yellow;
    default:
      return styles.gray;
  }
};

const getSizeClass = (size: RoundButtonProps['size']) => {
  switch (size) {
    case 'sm':
      return styles.small;
    case 'md':
      return styles.medium;
    case 'lg':
      return styles.large;
    default:
      return styles.medium;
  }
};

export default function RoundButton({
  text,
  color,
  tooltip,
  actions = [],
  className = '',
  onClick,
  size = 'md',
  animated = false,
}: RoundButtonProps) {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [dropdownAnchor, setDropdownAnchor] = useState<{
    x: number;
    y: number;
  } | null>(null);

  const handleClick = (event: React.MouseEvent) => {
    event.stopPropagation();

    if (actions.length > 0) {
      const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
      const menuWidth = 200;
      const menuHeight = 150;

      // Calculate position relative to viewport with better margins
      let x = rect.right + 8;
      if (rect.right + menuWidth + 16 > window.innerWidth) {
        x = rect.left - menuWidth - 8;
      }

      let y = rect.top;
      if (rect.bottom + menuHeight + 16 > window.innerHeight) {
        y = rect.bottom - menuHeight;
      }

      // Ensure we don't go off screen
      x = Math.max(8, Math.min(x, window.innerWidth - menuWidth - 8));
      y = Math.max(8, Math.min(y, window.innerHeight - menuHeight - 8));

      setDropdownAnchor({ x, y });
      setDropdownOpen(true);
    } else if (onClick) {
      onClick(event);
    }
  };

  const colorClass = getColorClass(color);
  const sizeClass = getSizeClass(size);

  return (
    <>
      <button
        className={`${styles.roundButton} ${colorClass} ${sizeClass} ${className}`}
        onClick={handleClick}
        title={tooltip}
        type="button"
      >
        {animated && color === 'blue' ? (
          <div className={styles.spinner}></div>
        ) : (
          text
        )}
      </button>

      {/* Actions Dropdown */}
      {actions.length > 0 && (
        <Popover
          open={dropdownOpen}
          onOpenChange={setDropdownOpen}
          anchor={dropdownAnchor || undefined}
          content={
            <div
              className={styles.popoverContent}
              onClick={e => e.stopPropagation()}
              onMouseDown={e => e.stopPropagation()}
            >
              {actions.map((action, index) => (
                <button
                  key={index}
                  className={`${styles.actionButton} ${action.disabled ? styles.disabled : ''}`}
                  disabled={action.disabled}
                  onClick={e => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (!action.disabled) {
                      action.onClick();
                      setDropdownOpen(false);
                    }
                  }}
                  onMouseDown={e => {
                    e.preventDefault();
                    e.stopPropagation();
                  }}
                  title={action.label}
                >
                  <span className={action.disabled ? styles.disabledText : ''}>
                    {action.label}
                  </span>
                </button>
              ))}
            </div>
          }
        />
      )}
    </>
  );
}
