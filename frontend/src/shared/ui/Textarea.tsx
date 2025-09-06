import React from 'react'
import styles from './Textarea.module.css'

type Props = React.TextareaHTMLAttributes<HTMLTextAreaElement>

const Textarea = React.forwardRef<HTMLTextAreaElement, Props>((props, ref) => {
  return <textarea {...props} ref={ref} className={[styles.textarea, props.className||''].join(' ')} />
})
Textarea.displayName = 'Textarea'

export default Textarea
