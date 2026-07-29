import { create } from 'zustand';

type OnboardingModalState = {
  readonly isOpen: boolean;
  readonly open: () => void;
  readonly close: () => void;
};

export const useOnboardingModalStore = create<OnboardingModalState>((set) => ({
  isOpen: false,
  open: () => set({ isOpen: true }),
  close: () => set({ isOpen: false }),
}));
