import { create } from 'zustand';

export type EntityModalTabId = 'basic' | 'capabilities' | 'ai_genes' | 'instances' | 'distill';

type EntityModalState = {
  readonly entityId: string | null;
  readonly initialTab: EntityModalTabId | null;
  readonly open: (entityId: string, initialTab?: EntityModalTabId | null) => void;
  readonly close: () => void;
};

export const useEntityModalStore = create<EntityModalState>((set) => ({
  entityId: null,
  initialTab: null,
  open: (entityId, initialTab = null) => set({ entityId, initialTab }),
  close: () => set({ entityId: null, initialTab: null }),
}));
