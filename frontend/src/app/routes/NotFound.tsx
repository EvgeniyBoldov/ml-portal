import React from 'react'
import { Link } from 'react-router-dom'
import Card from '@shared/ui/Card'

export default function NotFound() {
  return (
    <div style={{display:'grid', placeItems:'center', minHeight:'60vh', padding:24}}>
      <Card>
        <h2>Страница не найдена</h2>
        <p>Мы не нашли такую страницу. Перейти в <Link to="/gpt/chat">чат</Link> или <Link to="/login">войти</Link>.</p>
      </Card>
    </div>
  )
}
