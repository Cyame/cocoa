import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type ComposerSettingsState = {
  readonly showThinkingChain: boolean;
  readonly renderMarkdown: boolean;
  readonly setShowThinkingChain: (value: boolean) => void;
  readonly setRenderMarkdown: (value: boolean) => void;
};

export const useComposerSettingsStore = create<ComposerSettingsState>()(
  persist(
    (set) => ({
      showThinkingChain: false,
      renderMarkdown: true,
      setShowThinkingChain: (value) => set({ showThinkingChain: value }),
      setRenderMarkdown: (value) => set({ renderMarkdown: value }),
    }),
    { name: 'eyot-composer-settings' },
  ),
);
