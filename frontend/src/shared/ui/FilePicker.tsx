import React, { useRef } from 'react'
import Button from './Button'
import styles from './FilePicker.module.css'

type Props = {
  onFileSelected: (file: File | null) => void
  accept?: string
  disabled?: boolean
  label?: string
}

export default function FilePicker({ onFileSelected, accept, disabled, label='Choose file' }: Props) {
  const ref = useRef<HTMLInputElement>(null)
  return (
    <div className={styles.wrap}>
      <input
        ref={ref}
        type="file"
        className={styles.inputHidden}
        accept={accept}
        onChange={e => onFileSelected(e.target.files?.[0] || null)}
        disabled={disabled}
      />
      <Button onClick={() => ref.current?.click()} disabled={disabled}>{label}</Button>
    </div>
  )
}
