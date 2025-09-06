import React from 'react'
import styles from './Select.module.css'

type Props = React.SelectHTMLAttributes<HTMLSelectElement> & { containerClassName?: string }

const Select = React.forwardRef<HTMLSelectElement, Props>(({ containerClassName, className, children, ...rest }, ref) => {
  return (
    <span className={[styles.root, containerClassName||''].join(' ')}>
      <select ref={ref} className={[styles.select, className||''].join(' ')} {...rest}>
        {children}
      </select>
      <svg className={styles.arrow} width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M7 10l5 5 5-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  )
})
Select.displayName = 'Select'
export default Select
