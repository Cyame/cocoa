import { create } from 'zustand';

type ComposerDraftState = {
  /** Prefill text from topology "chat in Composer"; consumed once by ComposerPanel. */
  draft: string | null;
  setDraft: (text: string) => void;
  consumeDraft: () => string | null;
};

export const useComposerDraftStore = create<ComposerDraftState>((set, get) => ({
  draft: null,
  setDraft: (text) => set({ draft: text }),
  consumeDraft: () => {
    const { draft } = get();
    if (draft !== null) set({ draft: null });
    return draft;
  },
}));
