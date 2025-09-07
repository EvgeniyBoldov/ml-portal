import React from 'react'
import styles from './Badge.module.css'

type Props = React.HTMLAttributes<HTMLSpanElement> & {
  tone?: 'neutral' | 'success' | 'warn' | 'danger' | 'info'
  children: React.ReactNode
  className?: string
}

export default function Badge({ tone='neutral', className='', children, ...rest }: Props) {
  return (
    <span
      {...rest}
      className={[styles.badge, styles[tone], className].join(' ')}
    >
      {children}
    </span>
  )
}
