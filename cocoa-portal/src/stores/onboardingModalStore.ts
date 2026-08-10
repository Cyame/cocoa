import { create } from 'zustand';

type OnboardingOpenOptions = {
  readonly baseClassSlug?: string;
  readonly namespaceId?: string;
};

type OnboardingModalState = {
  readonly isOpen: boolean;
  readonly baseClassSlug: string | null;
  readonly namespaceId: string | null;
  readonly open: (options?: OnboardingOpenOptions) => void;
  readonly close: () => void;
};

export const useOnboardingModalStore = create<OnboardingModalState>((set) => ({
  isOpen: false,
  baseClassSlug: null,
  namespaceId: null,
  open: (options) =>
    set({
      isOpen: true,
      baseClassSlug: options?.baseClassSlug ?? null,
      namespaceId: options?.namespaceId ?? null,
    }),
  close: () => set({ isOpen: false, baseClassSlug: null, namespaceId: null }),
}));
