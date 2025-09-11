import React from 'react'
import styles from './Button.module.css'

type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'ghost' | 'danger'
  size?: 'md' | 'sm' | 'small'
}

export default function Button({ variant='primary', size='md', className='', ...rest }: Props) {
  const sizeClass = size === 'small' ? 'sm' : size
  const cls = [styles.btn, styles[variant], styles[sizeClass], className].join(' ')
  return <button {...rest} className={cls} />
}
