import { create } from 'zustand';
import { type ReactNode } from 'react';

// Confirm dialog state
interface ConfirmDialogState {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel: string;
  cancelLabel: string;
  variant: 'danger' | 'warning' | 'info';
  onConfirm: (() => void) | null;
}

// UI state - modals, dropdowns, filters
interface UIState {
  modals: Record<string, boolean>;
  dropdowns: Record<string, boolean>;
  sidepanels: Record<string, boolean>;
  activeTabs: Record<string, string>; // page -> tab
  filters: Record<string, unknown>;
  confirmDialog: ConfirmDialogState;
  openModal: (id: string) => void;
  closeModal: (id: string) => void;
  toggleModal: (id: string) => void;
  openDropdown: (id: string) => void;
  closeDropdown: (id: string) => void;
  closeAllDropdowns: () => void;
  toggleDropdown: (id: string) => void;
  openSidepanel: (id: string) => void;
  closeSidepanel: (id: string) => void;
  setActiveTab: (page: string, tab: string) => void;
  setFilter: (key: string, value: unknown) => void;
  resetFilters: () => void;
  showConfirmDialog: (params: Omit<ConfirmDialogState, 'open'>) => void;
  hideConfirmDialog: () => void;
  confirmAndClose: () => void;
}

// Selection state (extends to admin pages)
interface SelectionState {
  selectedDocIds: string[];
  selectedUserIds: string[];
  selectedModelIds: string[];
  selectedTenantIds: string[];
  setSelected: (ids: string[]) => void;
  clearSelection: () => void;
  toggleSelection: (id: string) => void;
  // Admin selections
  setSelectedUsers: (ids: string[]) => void;
  setSelectedModels: (ids: string[]) => void;
  setSelectedTenants: (ids: string[]) => void;
  toggleUserSelection: (id: string) => void;
  toggleModelSelection: (id: string) => void;
  toggleTenantSelection: (id: string) => void;
}

// RAG view state
type RAGActionType = 'ingest' | 'reset' | 'cancel' | 'kill';

interface RAGViewState {
  focusedDocId?: string;
  setFocusedDoc: (id?: string) => void;
  lastAction?: { type: RAGActionType; id: string; timestamp: number };
  setLastAction: (action: { type: RAGActionType; id: string }) => void;
  clearLastAction: () => void;
}

// Combined store
type AppStore = UIState & SelectionState & RAGViewState;

export const useAppStore = create<AppStore>(set => ({
  // UI state
  modals: {},
  dropdowns: {},
  sidepanels: {},
  activeTabs: {},
  filters: {},

  // Confirm dialog
  confirmDialog: {
    open: false,
    title: '',
    message: null,
    confirmLabel: 'Confirm',
    cancelLabel: 'Cancel',
    variant: 'danger',
    onConfirm: null,
  },

  showConfirmDialog: params =>
    set(() => ({ confirmDialog: { ...params, open: true } })),

  hideConfirmDialog: () =>
    set(state => ({
      confirmDialog: { ...state.confirmDialog, open: false },
    })),

  confirmAndClose: () =>
    set(state => {
      if (state.confirmDialog.onConfirm) {
        state.confirmDialog.onConfirm();
      }
      return {
        confirmDialog: { ...state.confirmDialog, open: false },
      };
    }),

  openModal: id => set(state => ({ modals: { ...state.modals, [id]: true } })),

  closeModal: id =>
    set(state => ({ modals: { ...state.modals, [id]: false } })),

  toggleModal: id =>
    set(state => ({
      modals: { ...state.modals, [id]: !state.modals[id] },
    })),

  openDropdown: id =>
    set(state => ({ dropdowns: { ...state.dropdowns, [id]: true } })),

  closeDropdown: id =>
    set(state => ({ dropdowns: { ...state.dropdowns, [id]: false } })),

  closeAllDropdowns: () => set(() => ({ dropdowns: {} })),

  toggleDropdown: id =>
    set(state => ({
      dropdowns: { ...state.dropdowns, [id]: !state.dropdowns[id] },
    })),

  setFilter: (key, value) =>
    set(state => ({
      filters: { ...state.filters, [key]: value },
    })),

  resetFilters: () => set(() => ({ filters: {} })),

  openSidepanel: id =>
    set(state => ({ sidepanels: { ...state.sidepanels, [id]: true } })),

  closeSidepanel: id =>
    set(state => ({ sidepanels: { ...state.sidepanels, [id]: false } })),

  setActiveTab: (page, tab) =>
    set(state => ({
      activeTabs: { ...state.activeTabs, [page]: tab },
    })),

  // Selection state
  selectedDocIds: [],
  selectedUserIds: [],
  selectedModelIds: [],
  selectedTenantIds: [],

  setSelected: ids => set(() => ({ selectedDocIds: ids })),

  clearSelection: () => set(() => ({ selectedDocIds: [] })),

  toggleSelection: id =>
    set(state => ({
      selectedDocIds: state.selectedDocIds.includes(id)
        ? state.selectedDocIds.filter(d => d !== id)
        : [...state.selectedDocIds, id],
    })),

  // Admin selections
  setSelectedUsers: ids => set(() => ({ selectedUserIds: ids })),
  setSelectedModels: ids => set(() => ({ selectedModelIds: ids })),
  setSelectedTenants: ids => set(() => ({ selectedTenantIds: ids })),

  toggleUserSelection: id =>
    set(state => ({
      selectedUserIds: state.selectedUserIds.includes(id)
        ? state.selectedUserIds.filter(d => d !== id)
        : [...state.selectedUserIds, id],
    })),

  toggleModelSelection: id =>
    set(state => ({
      selectedModelIds: state.selectedModelIds.includes(id)
        ? state.selectedModelIds.filter(d => d !== id)
        : [...state.selectedModelIds, id],
    })),

  toggleTenantSelection: id =>
    set(state => ({
      selectedTenantIds: state.selectedTenantIds.includes(id)
        ? state.selectedTenantIds.filter(d => d !== id)
        : [...state.selectedTenantIds, id],
    })),

  // RAG view state
  focusedDocId: undefined,

  setFocusedDoc: id => set(() => ({ focusedDocId: id })),

  lastAction: undefined,

  setLastAction: action =>
    set(() => ({
      lastAction: { ...action, timestamp: Date.now() },
    })),

  clearLastAction: () => set(() => ({ lastAction: undefined })),
}));

// Selectors for better performance
export const useModalOpen = (id: string) =>
  useAppStore(state => state.modals[id] || false);

export const useDropdownOpen = (id: string) =>
  useAppStore(state => state.dropdowns[id] || false);

export const useRAGFilters = () => useAppStore(state => state.filters);

export const useSelectedDocs = () => useAppStore(state => state.selectedDocIds);

export const useFocusedDoc = () => useAppStore(state => state.focusedDocId);

// Admin selectors
export const useSelectedUsers = () =>
  useAppStore(state => state.selectedUserIds);
export const useSelectedModels = () =>
  useAppStore(state => state.selectedModelIds);
export const useSelectedTenants = () =>
  useAppStore(state => state.selectedTenantIds);
export const useSidepanelOpen = (id: string) =>
  useAppStore(state => state.sidepanels[id] || false);
export const useActiveTab = (page: string) =>
  useAppStore(state => state.activeTabs[page] || '');
