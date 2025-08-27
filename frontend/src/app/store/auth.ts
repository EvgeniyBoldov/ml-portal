import { create } from "zustand";

type Role = "admin" | "user";
type State = {
  token?: string;
  role?: Role;
  setAuth: (token?: string, role?: Role) => void;
  logout: () => void;
};

export const useAuth = create<State>((set) => ({
  token: undefined,
  role: undefined,
  setAuth: (token, role) => set({ token, role }),
  logout: () => set({ token: undefined, role: undefined }),
}));
