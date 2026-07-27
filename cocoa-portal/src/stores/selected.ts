import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

const TOPOLOGY_MODE_STORAGE_KEY = 'cocoa.topology.mode';

export type InteractionMode = 'select' | 'connect' | 'move';

type SelectedState = {
  readonly officeId: string | null;
  readonly instanceId: string | null;
  readonly interactionMode: InteractionMode;
  readonly setOfficeId: (officeId: string | null) => void;
  readonly setInstanceId: (instanceId: string | null) => void;
  readonly setInteractionMode: (interactionMode: InteractionMode) => void;
};

type PersistedSelection = Pick<SelectedState, 'interactionMode'>;

export const useSelectedStore = create<SelectedState>()(
  persist<SelectedState, [], [], PersistedSelection>(
    (set) => ({
      officeId: null,
      instanceId: null,
      interactionMode: 'select',
      setOfficeId: (officeId) => set({ officeId }),
      setInstanceId: (instanceId) => set({ instanceId }),
      setInteractionMode: (interactionMode) => set({ interactionMode }),
    }),
    {
      name: TOPOLOGY_MODE_STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      partialize: ({ interactionMode }) => ({ interactionMode }),
    },
  ),
);
