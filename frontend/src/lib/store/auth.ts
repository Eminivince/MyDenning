import { create } from "zustand";

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  organizationId: string | null;
  isAuthenticated: boolean;
  setAuth: (token: string, refreshToken: string) => void;
  setOrganization: (orgId: string) => void;
  logout: () => void;
  hydrate: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  refreshToken: null,
  organizationId: null,
  isAuthenticated: false,

  setAuth: (token, refreshToken) => {
    localStorage.setItem("access_token", token);
    localStorage.setItem("refresh_token", refreshToken);
    set({ token, refreshToken, isAuthenticated: true });
  },

  setOrganization: (orgId) => {
    localStorage.setItem("organization_id", orgId);
    set({ organizationId: orgId });
  },

  logout: () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("organization_id");
    set({ token: null, refreshToken: null, organizationId: null, isAuthenticated: false });
  },

  hydrate: () => {
    if (typeof window === "undefined") return;
    const token = localStorage.getItem("access_token");
    const refreshToken = localStorage.getItem("refresh_token");
    const organizationId = localStorage.getItem("organization_id");
    set({ token, refreshToken, organizationId, isAuthenticated: !!token });
  },
}));
