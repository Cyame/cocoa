import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

const TOPOLOGY_MODE_STORAGE_KEY = 'cocoa.topology.mode';

export type InteractionMode = 'select' | 'connect' | 'move';

type SelectedState = {
  readonly workspaceId: string | null;
  readonly instanceId: string | null;
  readonly interactionMode: InteractionMode;
  readonly setWorkspaceId: (workspaceId: string | null) => void;
  readonly setInstanceId: (instanceId: string | null) => void;
  readonly setInteractionMode: (interactionMode: InteractionMode) => void;
  /** @deprecated Use setWorkspaceId */
  readonly setOfficeId: (workspaceId: string | null) => void;
  /** @deprecated Use workspaceId */
  readonly officeId: string | null;
};

type PersistedSelection = Pick<SelectedState, 'interactionMode'>;

export const useSelectedStore = create<SelectedState>()(
  persist<SelectedState, [], [], PersistedSelection>(
    (set) => ({
      workspaceId: null,
      officeId: null,
      instanceId: null,
      interactionMode: 'select',
      setWorkspaceId: (workspaceId) => set({ workspaceId, officeId: workspaceId }),
      setOfficeId: (workspaceId) => set({ workspaceId, officeId: workspaceId }),
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
