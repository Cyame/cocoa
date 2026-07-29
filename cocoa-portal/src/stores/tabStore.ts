import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

export type TopologyTab = {
  readonly id: string;
  readonly label: string;
  readonly instanceId: string;
};

type TabState = {
  readonly tabs: readonly TopologyTab[];
  readonly activeTabId: string;
  readonly addTab: (tab: TopologyTab) => void;
  readonly removeTab: (id: string) => void;
  readonly setActiveTab: (id: string) => void;
};

export const useTabStore = create<TabState>()(
  persist(
    (set) => ({
      tabs: [],
      activeTabId: 'topology',
      addTab: (tab) =>
        set((state) => ({
          tabs: state.tabs.some((item) => item.id === tab.id) ? state.tabs : [...state.tabs, tab],
          activeTabId: tab.id,
        })),
      removeTab: (id) =>
        set((state) => ({
          tabs: state.tabs.filter((tab) => tab.id !== id),
          activeTabId: state.activeTabId === id ? 'topology' : state.activeTabId,
        })),
      setActiveTab: (activeTabId) => set({ activeTabId }),
    }),
    {
      name: 'cocoa.topology.tabs',
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);
