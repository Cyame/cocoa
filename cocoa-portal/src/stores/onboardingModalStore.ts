import { create } from 'zustand';

type OnboardingOpenOptions = {
  readonly baseClassSlug?: string;
};

type OnboardingModalState = {
  readonly isOpen: boolean;
  readonly baseClassSlug: string | null;
  readonly open: (options?: OnboardingOpenOptions) => void;
  readonly close: () => void;
};

export const useOnboardingModalStore = create<OnboardingModalState>((set) => ({
  isOpen: false,
  baseClassSlug: null,
  open: (options) =>
    set({
      isOpen: true,
      baseClassSlug: options?.baseClassSlug ?? null,
    }),
  close: () => set({ isOpen: false, baseClassSlug: null }),
}));
