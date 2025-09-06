import { create } from 'zustand'
import * as api from '@shared/api/auth'

export type User = { id: string; login: string; fio?: string; role?: string }

type State = {
  user: User | null
  loading: boolean
  login: (login: string, password: string) => Promise<void>
  fetchMe: () => Promise<void>
  logout: () => Promise<void>
}

export const useAuth = create<State>((set, get) => ({
  user: null,
  loading: false,

  async login(login, password) {
    set({ loading: true })
    try {
      await api.login(login, password)
      const me = await api.me()
      set({ user: me })
    } finally {
      set({ loading: false })
    }
  },

  async fetchMe() {
    set({ loading: true })
    try {
      const me = await api.me()
      set({ user: me })
    } catch {
      set({ user: null })
    } finally {
      set({ loading: false })
    }
  },

  async logout() {
    try { await api.logout() } finally { set({ user: null }) }
  }
}))
