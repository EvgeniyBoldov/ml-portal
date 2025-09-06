import React from 'react'
import styles from './Modal.module.css'
import Button from './Button'

type Props = {
  open: boolean
  title?: string
  onClose: () => void
  footer?: React.ReactNode
  children?: React.ReactNode
}

export default function Modal({ open, title, onClose, children, footer }: Props) {
  if (!open) return null
  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div className={styles.modal} onClick={e=>e.stopPropagation()}>
        <div className={styles.head}>
          <div className={styles.title}>{title}</div>
          <Button size="sm" variant="ghost" onClick={onClose}>✕</Button>
        </div>
        <div className={styles.body}>{children}</div>
        {footer && <div className={styles.foot}>{footer}</div>}
      </div>
    </div>
  )
}
