import { create } from 'zustand'
import * as auth from '@shared/api/auth'

export type User = { id: string; login?: string; fio?: string; role?: string }

type State = {
  user: User | null
  loading: boolean
  error?: string | null
}

type Actions = {
  login: (login: string, password: string) => Promise<void>
  fetchMe: () => Promise<User | null>
  logout: () => Promise<void>
}

export const useAuth = create<State & Actions>((set, get) => ({
  user: null,
  loading: false,
  error: null,

  async login(login, password) {
    set({ loading: true, error: null })
    try {
      await auth.login(login, password)
      await get().fetchMe()
    } catch (e: any) {
      set({ error: e?.message || 'Login failed' })
      throw e
    } finally {
      set({ loading: false })
    }
  },

  async fetchMe() {
    set({ loading: true, error: null })
    try {
      const me = await auth.me()
      set({ user: me || null })
      return me || null
    } catch {
      set({ user: null })
      return null
    } finally {
      set({ loading: false })
    }
  },

  async logout() {
    try { await auth.logout() } finally { set({ user: null }) }
  }
}))
