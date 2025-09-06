import React, { useEffect } from 'react'
import { createPortal } from 'react-dom'
import styles from './Popover.module.css'
import Button from './Button'

type Props = {
  open: boolean
  title?: string
  anchor: { x: number, y: number } | null
  onClose: () => void
  children: React.ReactNode
  footer?: React.ReactNode
}

export default function Popover({ open, title, anchor, onClose, children, footer }: Props) {
  useEffect(() => {
    function onEsc(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    function onClick(e: MouseEvent) {
      const el = document.getElementById('__popover__')
      if (!el) return
      if (!el.contains(e.target as Node)) onClose()
    }
    if (open) {
      document.addEventListener('keydown', onEsc)
      document.addEventListener('mousedown', onClick)
    }
    return () => {
      document.removeEventListener('keydown', onEsc)
      document.removeEventListener('mousedown', onClick)
    }
  }, [open, onClose])

  if (!open || !anchor) return null
  const style: React.CSSProperties = { left: Math.round(anchor.x), top: Math.round(anchor.y) }
  return createPortal(
    <div id="__popover__" className={styles.root} style={style}>
      {title && <div className={styles.head}><div className={styles.title}>{title}</div><Button size="sm" variant="ghost" onClick={onClose}>✕</Button></div>}
      <div className={styles.body}>{children}</div>
      {footer && <div className={styles.footer}>{footer}</div>}
    </div>,
    document.body
  )
}
