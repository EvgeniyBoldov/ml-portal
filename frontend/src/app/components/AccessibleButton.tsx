import React from 'react'
import Button from '@shared/ui/Button'
import styles from './AccessibleButton.module.css'

interface AccessibleButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost' | 'danger'
  size?: 'md' | 'sm' | 'small'
  loading?: boolean
  icon?: React.ReactNode
  children: React.ReactNode
  ariaLabel?: string
  ariaDescribedBy?: string
  ariaExpanded?: boolean
  ariaControls?: string
  ariaPressed?: boolean
}

const AccessibleButton = React.forwardRef<HTMLButtonElement, AccessibleButtonProps>(
  ({
    variant = 'primary',
    size = 'md',
    loading = false,
    icon,
    children,
    ariaLabel,
    ariaDescribedBy,
    ariaExpanded,
    ariaControls,
    ariaPressed,
    disabled,
    className = '',
    ...rest
  }, ref) => {
    const sizeClass = size === 'small' ? 'sm' : size
    const cls = [styles.btn, styles[variant], styles[sizeClass], className].join(' ')
    
    return (
      <button
        ref={ref}
        className={cls}
        disabled={disabled || loading}
        aria-label={ariaLabel}
        aria-describedby={ariaDescribedBy}
        aria-expanded={ariaExpanded}
        aria-controls={ariaControls}
        aria-pressed={ariaPressed}
        aria-busy={loading}
        {...rest}
      >
        {loading && (
          <span 
            className={styles.spinner} 
            aria-hidden="true"
            role="status"
          />
        )}
        {icon && !loading && (
          <span className={styles.icon} aria-hidden="true">
            {icon}
          </span>
        )}
        <span className={loading ? styles.hidden : ''}>
          {children}
        </span>
      </button>
    )
  }
)

AccessibleButton.displayName = 'AccessibleButton'

export default AccessibleButton
