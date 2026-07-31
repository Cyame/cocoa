import { create } from 'zustand';

export type DeployProgressPhase = 'running' | 'success' | 'failed' | 'cancelled' | 'timeout';

export type DeployProgressJob = {
  readonly recordId: string;
  readonly instanceId: string;
  readonly workspaceId: string;
  readonly startedAt: number;
  readonly minimized: boolean;
  readonly phase: DeployProgressPhase;
  readonly currentStep: number;
  readonly stepStatus: string;
  readonly message: string | null;
  readonly stepNames: readonly string[];
};

type DeployProgressState = {
  readonly job: DeployProgressJob | null;
  start: (input: {
    readonly recordId: string;
    readonly instanceId: string;
    readonly workspaceId: string;
    readonly stepNames?: readonly string[];
  }) => void;
  patch: (partial: Partial<DeployProgressJob>) => void;
  minimize: () => void;
  expand: () => void;
  clear: () => void;
};

const DEFAULT_STEPS = [
  'ensure_namespace',
  'configmap',
  'secret',
  'pvc',
  'deployment',
  'service',
  'network_policy',
  'healthz_watch',
  'status_update',
] as const;

export const useDeployProgressStore = create<DeployProgressState>((set, get) => ({
  job: null,
  start: (input) =>
    set({
      job: {
        recordId: input.recordId,
        instanceId: input.instanceId,
        workspaceId: input.workspaceId,
        startedAt: Date.now(),
        minimized: false,
        phase: 'running',
        currentStep: 0,
        stepStatus: 'running',
        message: null,
        stepNames: input.stepNames ?? DEFAULT_STEPS,
      },
    }),
  patch: (partial) => {
    const current = get().job;
    if (current === null) return;
    set({ job: { ...current, ...partial } });
  },
  minimize: () => {
    const current = get().job;
    if (current === null) return;
    set({ job: { ...current, minimized: true } });
  },
  expand: () => {
    const current = get().job;
    if (current === null) return;
    set({ job: { ...current, minimized: false } });
  },
  clear: () => set({ job: null }),
}));
