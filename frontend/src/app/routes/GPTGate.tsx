import React, { useEffect, useState } from 'react'
import { useAuth } from '@app/store/auth'
import { useNavigate } from 'react-router-dom'

export default function GPTGate({ children }: { children: React.ReactNode }) {
  const { user, fetchMe } = useAuth()
  const [checked, setChecked] = useState(false)
  const nav = useNavigate()

  useEffect(() => {
    (async () => {
      try { await fetchMe() } finally { setChecked(true) }
    })()
  }, [])

  useEffect(() => {
    if (checked && !user) nav('/login')
  }, [checked, user])

  if (!checked) return null
  if (!user) return null
  return <>{children}</>
}
