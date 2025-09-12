import React from 'react'

export function FilterIcon({ active=false, size=14 }: { active?: boolean, size?: number }) {
  const stroke = active ? 'var(--primary)' : 'currentColor'
  const fill = active ? 'var(--primary)' : 'none'
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" style={{ verticalAlign: 'middle' }}>
      <path d="M3 5h18l-7 8v5l-4 2v-7L3 5z" fill={fill} stroke={stroke} strokeWidth="1.5"/>
    </svg>
  )
}

export function MoreVerticalIcon({ size=14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" style={{ verticalAlign: 'middle' }}>
      <circle cx="12" cy="6" r="2" fill="currentColor"/>
      <circle cx="12" cy="12" r="2" fill="currentColor"/>
      <circle cx="12" cy="18" r="2" fill="currentColor"/>
    </svg>
  )
}
