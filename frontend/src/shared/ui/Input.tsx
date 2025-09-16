import React from 'react'
import styles from './Input.module.css'

type Props = React.InputHTMLAttributes<HTMLInputElement> & {
  error?: boolean
}

export default function Input(props: Props) {
  return <input {...props} className={[styles.input, props.className||''].join(' ')} />
}
