import { create } from 'zustand';

export type EntityModalTabId = 'basic' | 'capabilities' | 'ai_genes' | 'instances' | 'distill';

type EntityModalState = {
  readonly entityId: string | null;
  readonly open: (entityId: string) => void;
  readonly close: () => void;
};

export const useEntityModalStore = create<EntityModalState>((set) => ({
  entityId: null,
  open: (entityId) => set({ entityId }),
  close: () => set({ entityId: null }),
}));
