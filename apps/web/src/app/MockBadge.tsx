import React from 'react';
const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true';
export default function MockBadge() {
  if (!USE_MOCKS) return null;
  const style: React.CSSProperties = {
    position: 'fixed',
    bottom: 12,
    right: 12,
    padding: '6px 10px',
    background: 'rgba(79,124,255,0.15)',
    border: '1px solid rgba(79,124,255,0.35)',
    borderRadius: 10,
    fontSize: 12,
    color: 'var(--text)',
    zIndex: 9999,
  };
  return <div style={style}>Mocks ON</div>;
}
