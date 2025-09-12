import React from 'react'

export default function EmptyState({ title, description, action }: { title: string, description?: string, action?: React.ReactNode }) {
  return (
    <div style={{ display: 'grid', placeItems: 'center', minHeight: 260, textAlign: 'center', gap: 8 }}>
      <div style={{ fontWeight: 600, fontSize: 18 }}>{title}</div>
      {description && <div style={{ opacity: .75 }}>{description}</div>}
      {action}
    </div>
  )
}
