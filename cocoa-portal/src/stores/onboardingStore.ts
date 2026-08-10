import { create } from 'zustand';
import { isValidSlug, SLUG_PATTERN, toSlug } from '@/lib/slug';
import type {
  BaseClass,
  EmployeeRuntimeConfig,
  EntityConfigOverride,
  KnowledgeEnvEntry,
  KnowledgeFileEntry,
  KnowledgeScope,
  OnboardingPayload,
} from '@/lib/types';

export { isValidSlug, SLUG_PATTERN, toSlug };

const TOTAL_STEPS = 3;

export type OnboardingStep = 1 | 2 | 3;

export type KnowledgeRow = {
  readonly id: string;
  readonly key: string;
  readonly value: string;
};

export type KnowledgeFileRow = {
  readonly id: string;
  readonly name: string;
  readonly sizeBytes: number;
  readonly file: File;
};

export type OnboardingState = {
  readonly step: OnboardingStep;
  readonly selectedBaseClass: BaseClass | null;
  readonly displayName: string;
  readonly slug: string;
  readonly slugTouched: boolean;
  readonly providerId: string;
  readonly model: string;
  readonly description: string;
  readonly knowledgeRows: readonly KnowledgeRow[];
  readonly knowledgeFiles: readonly KnowledgeFileRow[];
  readonly knowledgeScope: KnowledgeScope;
  readonly namespaceId: string;
  readonly submitError: string | null;
  readonly setStep: (step: OnboardingStep) => void;
  readonly next: () => void;
  readonly back: () => void;
  readonly setSelectedBaseClass: (baseClass: BaseClass | null) => void;
  readonly setDisplayName: (displayName: string) => void;
  readonly setSlug: (slug: string) => void;
  readonly setSlugTouched: (slugTouched: boolean) => void;
  readonly setProviderId: (providerId: string) => void;
  readonly setModel: (model: string) => void;
  readonly setDescription: (description: string) => void;
  readonly setNamespaceId: (namespaceId: string) => void;
  readonly addKnowledgeRow: () => void;
  readonly updateKnowledgeRow: (id: string, patch: { key?: string; value?: string }) => void;
  readonly removeKnowledgeRow: (id: string) => void;
  readonly addKnowledgeFile: (file: KnowledgeFileRow) => void;
  readonly removeKnowledgeFile: (id: string) => void;
  readonly setKnowledgeScope: (scope: KnowledgeScope) => void;
  readonly setSubmitError: (error: string | null) => void;
  readonly buildPayload: () => OnboardingPayload;
  readonly reset: () => void;
};

const INITIAL_STATE: Pick<
  OnboardingState,
  | 'step'
  | 'selectedBaseClass'
  | 'displayName'
  | 'slug'
  | 'slugTouched'
  | 'providerId'
  | 'model'
  | 'description'
  | 'knowledgeRows'
  | 'knowledgeFiles'
  | 'knowledgeScope'
  | 'namespaceId'
  | 'submitError'
> = {
  step: 1,
  selectedBaseClass: null,
  displayName: '',
  slug: '',
  slugTouched: false,
  providerId: '',
  model: '',
  description: '',
  knowledgeRows: [],
  knowledgeFiles: [],
  knowledgeScope: 'instance',
  namespaceId: '',
  submitError: null,
};

function makeRowId(): string {
  return `env-${Math.random().toString(36).slice(2, 10)}-${Date.now().toString(36)}`;
}

function pruneEmptyEnv(rows: readonly KnowledgeRow[]): readonly KnowledgeEnvEntry[] {
  const out: KnowledgeEnvEntry[] = [];
  for (const row of rows) {
    const key = row.key.trim();
    if (key.length === 0) continue;
    out.push({ key, value: row.value });
  }
  return out;
}

function projectFiles(files: readonly KnowledgeFileRow[]): readonly KnowledgeFileEntry[] {
  return files.map((entry) => ({
    name: entry.name,
    size_bytes: entry.sizeBytes,
  }));
}

function buildRuntimeConfig(state: OnboardingState): EmployeeRuntimeConfig | null {
  const env = pruneEmptyEnv(state.knowledgeRows);
  const files = projectFiles(state.knowledgeFiles);
  if (env.length === 0 && files.length === 0) return null;
  return {
    knowledge_env: env,
    knowledge_files: files,
  };
}

function buildConfigOverride(state: OnboardingState): EntityConfigOverride | null {
  const providerId = (state.providerId ?? '').trim();
  const model = (state.model ?? '').trim();
  const runtimeConfig = buildRuntimeConfig(state);
  if (providerId.length === 0 && model.length === 0 && runtimeConfig === null) {
    return null;
  }
  return {
    provider_id: providerId.length > 0 ? providerId : null,
    model: model.length > 0 ? model : null,
    ...(runtimeConfig !== null ? { runtime_config: runtimeConfig } : {}),
  };
}

export const useOnboardingStore = create<OnboardingState>()((set, get) => ({
  ...INITIAL_STATE,
  setStep: (step) => set({ step }),
  next: () =>
    set((current) => {
      if (current.step >= TOTAL_STEPS) return current;
      const nextStep = (current.step + 1) as OnboardingStep;
      return { step: nextStep };
    }),
  back: () =>
    set((current) => {
      if (current.step <= 1) return current;
      const nextStep = (current.step - 1) as OnboardingStep;
      return { step: nextStep };
    }),
  setSelectedBaseClass: (selectedBaseClass) => set({ selectedBaseClass }),
  setDisplayName: (displayName) => {
    const trimmed = displayName;
    set((current) => {
      if (current.slugTouched) {
        return { displayName: trimmed };
      }
      return { displayName: trimmed, slug: toSlug(trimmed) };
    });
  },
  setSlug: (slug) => set({ slug, slugTouched: true }),
  setSlugTouched: (slugTouched) => set({ slugTouched }),
  setProviderId: (providerId) => set({ providerId }),
  setModel: (model) => set({ model }),
  setDescription: (description) => set({ description }),
  setNamespaceId: (namespaceId) => set({ namespaceId }),
  addKnowledgeRow: () =>
    set((current) => ({
      knowledgeRows: [...current.knowledgeRows, { id: makeRowId(), key: '', value: '' }],
    })),
  updateKnowledgeRow: (id, patch) =>
    set((current) => ({
      knowledgeRows: current.knowledgeRows.map((row) =>
        row.id === id ? { ...row, ...patch } : row,
      ),
    })),
  removeKnowledgeRow: (id) =>
    set((current) => ({
      knowledgeRows: current.knowledgeRows.filter((row) => row.id !== id),
    })),
  addKnowledgeFile: (file) =>
    set((current) => ({
      knowledgeFiles: [...current.knowledgeFiles, file],
    })),
  removeKnowledgeFile: (id) =>
    set((current) => ({
      knowledgeFiles: current.knowledgeFiles.filter((entry) => entry.id !== id),
    })),
  setKnowledgeScope: (knowledgeScope) => set({ knowledgeScope }),
  setSubmitError: (submitError) => set({ submitError }),
  buildPayload: () => {
    const state = get();
    const presetSlug = state.selectedBaseClass?.slug ?? '';
    const description = state.description.trim();
    const configOverride = buildConfigOverride(state);
    return {
      name: state.displayName.trim(),
      slug: state.slug.trim(),
      preset_slug: presetSlug,
      display_name: state.displayName.trim(),
      namespace_id: state.namespaceId,
      system_prompt: description.length > 0 ? description : null,
      config_override: configOverride,
    };
  },
  reset: () => set({ ...INITIAL_STATE }),
}));

export const TOTAL_ONBOARDING_STEPS = TOTAL_STEPS;
