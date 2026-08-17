import { create } from 'zustand';

// biome-ignore lint/complexity/noBannedTypes: placeholder — will be populated in P4-P9
type AppStore = {};

const useAppStore = create<AppStore>(() => ({}));

export default useAppStore;
