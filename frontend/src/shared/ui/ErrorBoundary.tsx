import React from 'react'

type State = { hasError: boolean, error?: any }
export default class ErrorBoundary extends React.Component<React.PropsWithChildren, State> {
  state: State = { hasError: false }
  static getDerivedStateFromError(error: any) { return { hasError: true, error } }
  componentDidCatch(error: any, errorInfo: any) { console.error('UI error:', error, errorInfo) }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{padding:24}}>
          <h2>Что-то пошло не так</h2>
          <div style={{opacity:.7, fontSize:14}}>{String(this.state.error || '')}</div>
          <button onClick={()=>this.setState({hasError:false, error: undefined})} style={{marginTop:12}}>Перезагрузить вид</button>
        </div>
      )
    }
    return this.props.children
  }
}
