import { AlertCircle, Cpu, LoaderCircle, Notebook, UserRound, Users } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router';
import BatchRestartModal, { type OutdatedInstanceRow } from '@/components/BatchRestartModal';
import WorkspaceHeader, {
  type WorkspaceHeaderStats,
  type WorkspaceHealth,
} from '@/components/WorkspaceHeader';
import type { WorkspaceHeaderMenuAction } from '@/components/WorkspaceHeaderMenu';
import { ApiError, api } from '@/lib/api';
import { batchRestartInstances } from '@/lib/api/instances';
import { fetchLiveStatus } from '@/lib/api/liveStatus';
import type {
  Employee,
  Instance,
  InstanceLoopState,
  LiveStatusItem,
  LoopStatus,
  Membership,
  Office,
} from '@/lib/types';
import { useSelectedStore } from '@/stores/selected';

type TabId = 'employees' | 'instances' | 'centralHub';

type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly total: number;
};

type CentralHub = {
  readonly id: string;
  readonly office_id: string;
  readonly content: string | null;
  readonly manual_notes: string | null;
  readonly created_at: string;
};

type Toast = {
  readonly kind: 'success' | 'error';
  readonly message: string;
};

const LIVE_STATUS_INTERVAL_MS = 2000;
const TOAST_AUTO_DISMISS_MS = 3000;

const GLOW_TO_STATUS: Readonly<Record<string, LoopStatus | 'unknown'>> = {
  '#10b981': 'running',
  '#eab308': 'idle',
  '#94a3b8': 'paused',
  '#ef4444': 'interrupted',
  '#3b82f6': 'completed',
  '#dc2626': 'failed',
};

function deriveLoopStatus(glowColor: string): LoopStatus | 'unknown' {
  return GLOW_TO_STATUS[glowColor.toLowerCase()] ?? 'unknown';
}

function computeHealth(liveStatus: readonly LiveStatusItem[]): WorkspaceHealth {
  let worst: WorkspaceHealth = 'healthy';
  for (const item of liveStatus) {
    if (item.node_type !== 'instance') continue;
    const status = deriveLoopStatus(item.glow.color);
    if (status === 'failed') return 'failed';
    if (status === 'interrupted' || status === 'paused') {
      worst = 'warning';
    }
  }
  return worst;
}

function centralHubSizeBytes(hub: CentralHub | null): number {
  if (hub === null) return 0;
  const contentBytes = hub.content === null ? 0 : new TextEncoder().encode(hub.content).length;
  const notesBytes =
    hub.manual_notes === null ? 0 : new TextEncoder().encode(hub.manual_notes).length;
  return contentBytes + notesBytes;
}

export default function OfficeDetailPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const setOfficeId = useSelectedStore((state) => state.setOfficeId);
  const [office, setOffice] = useState<Office | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>('employees');
  const [memberships, setMemberships] = useState<readonly Membership[]>([]);
  const [instances, setInstances] = useState<readonly Instance[]>([]);
  const [centralHub, setCentralHub] = useState<CentralHub | null>(null);
  const [employees, setEmployees] = useState<readonly Employee[]>([]);
  const [liveStatus, setLiveStatus] = useState<readonly LiveStatusItem[]>([]);
  const [loopStates, setLoopStates] = useState<Readonly<Record<string, InstanceLoopState>>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [isBatchRestartOpen, setIsBatchRestartOpen] = useState(false);
  const [isBatchRestarting, setIsBatchRestarting] = useState(false);

  const TABS = [
    { id: 'employees' as const, label: t('officeDetail.tabEmployees'), Icon: Users },
    { id: 'instances' as const, label: t('officeDetail.tabInstances'), Icon: Cpu },
    { id: 'centralHub' as const, label: t('officeDetail.tabCentralHub'), Icon: Notebook },
  ];

  useEffect(() => {
    if (id === undefined) return;
    setOfficeId(id);
    return () => setOfficeId(null);
  }, [id, setOfficeId]);

  useEffect(() => {
    if (id === undefined) return;
    const officeId = id;
    let isActive = true;

    async function loadHeaderData() {
      try {
        const results = await Promise.allSettled([
          api<Office>(`/offices/${officeId}`),
          api<OffsetPage<Membership>>(
            `/messaging/memberships?office_id=${encodeURIComponent(officeId)}`,
          ),
          api<OffsetPage<Instance>>(`/instances?office_id=${encodeURIComponent(officeId)}`),
          api<CentralHub>(`/central-hubs?office_id=${encodeURIComponent(officeId)}`).catch(
            () => null,
          ),
          api<OffsetPage<Employee>>(`/employees?limit=200`),
        ]);

        if (!isActive) return;

        const [officeResult, membershipResult, instanceResult, hubResult, employeeResult] = results;

        if (officeResult.status === 'fulfilled') setOffice(officeResult.value);
        if (membershipResult.status === 'fulfilled') setMemberships(membershipResult.value.items);
        if (instanceResult.status === 'fulfilled') setInstances(instanceResult.value.items);
        if (hubResult.status === 'fulfilled' && hubResult.value !== null) {
          setCentralHub(hubResult.value);
        }
        if (employeeResult.status === 'fulfilled' && Array.isArray(employeeResult.value.items)) {
          setEmployees(employeeResult.value.items);
        }
      } catch {
        // Best-effort: header renders with whatever subsets succeeded.
      } finally {
        if (isActive) setIsLoading(false);
      }
    }

    void loadHeaderData();
    return () => {
      isActive = false;
    };
  }, [id]);

  useEffect(() => {
    if (id === undefined) return;
    const officeId = id;
    let cancelled = false;
    let timerId: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      if (cancelled) return;
      try {
        const items = await fetchLiveStatus(officeId);
        if (!cancelled && Array.isArray(items)) setLiveStatus(items);
      } catch {
        // best-effort
      } finally {
        if (!cancelled) {
          timerId = setTimeout(poll, LIVE_STATUS_INTERVAL_MS);
        }
      }
    }

    timerId = setTimeout(poll, 0);
    return () => {
      cancelled = true;
      if (timerId !== null) clearTimeout(timerId);
    };
  }, [id]);

  useEffect(() => {
    if (id === undefined) return;
    const officeId = id;
    let isActive = true;

    async function loadTab() {
      setErrorMessage(null);
      try {
        if (activeTab === 'employees') {
          const [officeResponse, membershipPage] = await Promise.all([
            office === null ? api<Office>(`/offices/${officeId}`) : Promise.resolve(office),
            memberships.length > 0
              ? Promise.resolve({ items: memberships, total: memberships.length })
              : api<OffsetPage<Membership>>(
                  `/messaging/memberships?office_id=${encodeURIComponent(officeId)}`,
                ),
          ]);
          if (isActive) {
            setOffice(officeResponse);
            setMemberships(membershipPage.items);
          }
        } else if (activeTab === 'instances') {
          const [officeResponse, instancePage] = await Promise.all([
            office === null ? api<Office>(`/offices/${officeId}`) : Promise.resolve(office),
            instances.length > 0
              ? Promise.resolve({ items: instances, total: instances.length })
              : api<OffsetPage<Instance>>(`/instances?office_id=${encodeURIComponent(officeId)}`),
          ]);
          if (isActive) {
            setOffice(officeResponse);
            setInstances(instancePage.items);
          }
          const instanceItems = instancePage.items;
          const fetched = await Promise.allSettled(
            instanceItems.map((inst) =>
              api<InstanceLoopState>(`/instances/${encodeURIComponent(inst.id)}/status`).then(
                (state) => ({ id: inst.id, state }),
                () => null,
              ),
            ),
          );
          if (isActive) {
            setLoopStates((previous) => {
              const next: Record<string, InstanceLoopState> = { ...previous };
              for (const result of fetched) {
                if (result.status === 'fulfilled' && result.value !== null) {
                  next[result.value.id] = result.value.state;
                }
              }
              return next;
            });
          }
        } else {
          const [officeResponse, centralHubResponse] = await Promise.all([
            office === null ? api<Office>(`/offices/${officeId}`) : Promise.resolve(office),
            centralHub !== null
              ? Promise.resolve(centralHub)
              : api<CentralHub>(`/central-hubs?office_id=${encodeURIComponent(officeId)}`),
          ]);
          if (isActive) {
            setOffice(officeResponse);
            setCentralHub(centralHubResponse);
          }
        }
      } catch (error) {
        if (error instanceof ApiError) {
          if (isActive) setErrorMessage(error.message);
          return;
        }
        if (isActive) setErrorMessage(t('errors.network'));
      }
    }

    void loadTab();
    return () => {
      isActive = false;
    };
  }, [activeTab, id, office, memberships, instances, centralHub, t]);

  useEffect(() => {
    if (toast === null) return;
    const timerId = setTimeout(() => setToast(null), TOAST_AUTO_DISMISS_MS);
    return () => clearTimeout(timerId);
  }, [toast]);

  const employeeById = useMemo<Readonly<Record<string, Employee>>>(
    () => Object.fromEntries(employees.map((emp) => [emp.id, emp])),
    [employees],
  );

  const uniqueEntityCount = useMemo(() => {
    const ids = new Set<string>();
    for (const inst of instances) ids.add(inst.employee_id);
    return ids.size;
  }, [instances]);

  const outdatedInstanceCount = useMemo(
    () => liveStatus.filter((item) => item.outdated).length,
    [liveStatus],
  );

  const health = useMemo(() => computeHealth(liveStatus), [liveStatus]);

  const headerStats = useMemo<WorkspaceHeaderStats>(
    () => ({
      entityCount: uniqueEntityCount,
      instanceCount: instances.length,
      membershipCount: memberships.length,
      centralHubSizeBytes: centralHubSizeBytes(centralHub),
    }),
    [uniqueEntityCount, instances.length, memberships.length, centralHub],
  );

  const outdatedRows = useMemo<readonly OutdatedInstanceRow[]>(() => {
    if (outdatedInstanceCount === 0) return [];
    const membershipById = new Map<string, Membership>(memberships.map((m) => [m.id, m]));
    const rows: OutdatedInstanceRow[] = [];
    for (const item of liveStatus) {
      if (!item.outdated) continue;
      if (item.node_type !== 'instance') continue;
      const membership = membershipById.get(item.membership_id);
      if (membership === undefined || membership.instance_id === null) continue;
      const matchedInstance = instances.find((inst) => inst.id === membership.instance_id);
      if (matchedInstance === undefined) continue;
      const loopState = loopStates[matchedInstance.id];
      const loopStatus: LoopStatus | 'unknown' =
        loopState !== undefined ? loopState.loop_status : deriveLoopStatus(item.glow.color);
      const employee = employeeById[matchedInstance.employee_id];
      const employeeLabel = employee?.display_name ?? employee?.name ?? matchedInstance.employee_id;
      rows.push({
        instance_id: matchedInstance.id,
        employee_id: matchedInstance.employee_id,
        employee_label: employeeLabel,
        loop_status: loopStatus,
        active_hash: item.active_hash,
        outdated_for_iso: matchedInstance.updated_at,
        is_running: matchedInstance.status === 'running' || loopStatus === 'running',
      });
    }
    return rows;
  }, [liveStatus, instances, memberships, outdatedInstanceCount, loopStates, employeeById]);

  const handleSummonEntity = useCallback(() => {
    if (id === undefined) return;
    navigate(`/offices/${id}/employees`);
  }, [id, navigate]);

  const refreshHeader = useCallback(async () => {
    if (id === undefined) return;
    const officeId = id;
    setIsLoading(true);
    try {
      const results = await Promise.allSettled([
        api<Office>(`/offices/${officeId}`),
        api<OffsetPage<Membership>>(
          `/messaging/memberships?office_id=${encodeURIComponent(officeId)}`,
        ),
        api<OffsetPage<Instance>>(`/instances?office_id=${encodeURIComponent(officeId)}`),
        api<CentralHub>(`/central-hubs?office_id=${encodeURIComponent(officeId)}`).catch(
          () => null,
        ),
        fetchLiveStatus(officeId),
      ]);
      const [officeResult, membershipResult, instanceResult, hubResult, liveResult] = results;
      if (officeResult.status === 'fulfilled') setOffice(officeResult.value);
      if (membershipResult.status === 'fulfilled') setMemberships(membershipResult.value.items);
      if (instanceResult.status === 'fulfilled') setInstances(instanceResult.value.items);
      if (hubResult.status === 'fulfilled' && hubResult.value !== null) {
        setCentralHub(hubResult.value);
      }
      if (liveResult.status === 'fulfilled') {
        setLiveStatus(liveResult.value);
      }
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  const handleMenuAction = useCallback(
    (action: WorkspaceHeaderMenuAction) => {
      switch (action) {
        case 'batchRestart':
          setIsBatchRestartOpen(true);
          return;
        case 'editNameSlug':
          return;
        case 'softDelete':
          return;
        case 'refresh':
          void refreshHeader();
          return;
        default:
          return;
      }
    },
    [refreshHeader],
  );

  const handleBatchRestart = useCallback(
    async (selectedIds: readonly string[]): Promise<boolean> => {
      if (id === undefined) return false;
      setIsBatchRestarting(true);
      try {
        await batchRestartInstances(selectedIds, 'workspace batch restart');
        setToast({
          kind: 'success',
          message: t('batchRestart.successToast', { count: selectedIds.length }),
        });
        try {
          const items = await fetchLiveStatus(id);
          setLiveStatus(items);
        } catch {
          // best-effort
        }
        return true;
      } catch (error) {
        if (error instanceof ApiError) {
          setToast({ kind: 'error', message: error.message });
        } else {
          setToast({ kind: 'error', message: t('batchRestart.errorGeneric') });
        }
        return false;
      } finally {
        setIsBatchRestarting(false);
      }
    },
    [id, t],
  );

  if (id === undefined) {
    return <p className="p-6 text-sm text-red-700">{t('office.officeIdMissing')}</p>;
  }

  return (
    <div className="flex flex-col">
      {office !== null ? (
        <WorkspaceHeader
          workspace={office}
          stats={headerStats}
          health={health}
          outdatedInstanceCount={outdatedInstanceCount}
          isLoading={isLoading}
          onSummonEntity={handleSummonEntity}
          onMenuAction={handleMenuAction}
        />
      ) : null}

      <section
        className="mx-auto w-full max-w-6xl p-6 lg:p-8"
        aria-label={t('officeDetail.tablist')}
      >
        {toast !== null ? <ToastView toast={toast} /> : null}

        <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto border-b border-slate-200">
            <div
              role="tablist"
              aria-label={t('officeDetail.tablist')}
              className="flex min-w-max gap-1 px-3 pt-3"
            >
              {TABS.map(({ id: tabId, label, Icon }) => (
                <button
                  key={tabId}
                  type="button"
                  role="tab"
                  id={`tab-${tabId}`}
                  aria-selected={activeTab === tabId}
                  aria-controls={`panel-${tabId}`}
                  onClick={() => setActiveTab(tabId)}
                  className={`inline-flex items-center gap-2 rounded-t-lg border-b-2 px-4 py-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                    activeTab === tabId
                      ? 'border-blue-600 bg-blue-50 text-blue-700'
                      : 'border-transparent text-slate-500 hover:bg-slate-50 hover:text-slate-900'
                  }`}
                >
                  <Icon className="size-4" aria-hidden="true" />
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div
            id={`panel-${activeTab}`}
            role="tabpanel"
            aria-labelledby={`tab-${activeTab}`}
            className="min-h-64 p-4 sm:p-6"
          >
            {errorMessage !== null ? (
              <div
                role="alert"
                className="flex gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
              >
                <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                <p>{errorMessage}</p>
              </div>
            ) : null}

            {isLoading ? (
              <div className="flex min-h-52 items-center justify-center gap-3 text-sm text-slate-500">
                <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
                {t('common.loading')} {activeTab}
              </div>
            ) : null}

            {!isLoading && errorMessage === null && activeTab === 'employees' ? (
              memberships.length > 0 ? (
                <ul className="grid gap-3 sm:grid-cols-2">
                  {memberships.map((membership) => (
                    <li
                      key={membership.id}
                      className="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4"
                    >
                      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-white text-slate-600 shadow-sm">
                        <UserRound className="size-4" aria-hidden="true" />
                      </span>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-slate-900">
                          {membership.user_id ?? membership.instance_id}
                        </p>
                        <p className="mt-1 text-xs capitalize text-slate-500">{membership.role}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  Icon={Users}
                  title={t('officeDetail.emptyEmployeesTitle')}
                  detail={t('officeDetail.emptyEmployeesDetail')}
                />
              )
            ) : null}

            {!isLoading && errorMessage === null && activeTab === 'instances' ? (
              instances.length > 0 ? (
                <ul className="space-y-3">
                  {instances.map((instance) => (
                    <li
                      key={instance.id}
                      className="grid gap-3 rounded-lg border border-slate-200 p-4 sm:grid-cols-[1fr_auto] sm:items-center"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-slate-900">
                          {instance.employee_id}
                        </p>
                        <p className="mt-1 truncate font-mono text-xs text-slate-500">
                          {instance.workspace_path ?? instance.id}
                        </p>
                      </div>
                      <span className="w-fit rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                        {instance.status}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  Icon={Cpu}
                  title={t('officeDetail.emptyInstancesTitle')}
                  detail={t('officeDetail.emptyInstancesDetail')}
                />
              )
            ) : null}

            {!isLoading && errorMessage === null && activeTab === 'centralHub' ? (
              centralHub === null ? (
                <EmptyState
                  Icon={Notebook}
                  title={t('officeDetail.emptyCentralHubTitle')}
                  detail={t('officeDetail.emptyCentralHubDetail')}
                />
              ) : (
                <div className="grid gap-4 lg:grid-cols-2">
                  <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                    <h2 className="text-sm font-semibold text-slate-900">
                      {t('officeDetail.sharedContext')}
                    </h2>
                    <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-600">
                      {centralHub.content ?? t('officeDetail.noSharedContext')}
                    </p>
                  </article>
                  <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                    <h2 className="text-sm font-semibold text-slate-900">
                      {t('officeDetail.manualNotes')}
                    </h2>
                    <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-600">
                      {centralHub.manual_notes ?? t('officeDetail.noManualNotes')}
                    </p>
                  </article>
                </div>
              )
            ) : null}
          </div>
        </div>
      </section>

      <BatchRestartModal
        isOpen={isBatchRestartOpen}
        outdatedInstances={outdatedRows}
        totalInstanceCount={instances.length}
        onClose={() => {
          if (isBatchRestarting) return;
          setIsBatchRestartOpen(false);
        }}
        onConfirm={handleBatchRestart}
      />
    </div>
  );
}

type EmptyStateProps = {
  readonly Icon: typeof Users;
  readonly title: string;
  readonly detail: string;
};

function EmptyState({ Icon, title, detail }: EmptyStateProps) {
  return (
    <div className="grid min-h-52 place-items-center text-center">
      <div>
        <Icon className="mx-auto size-8 text-slate-400" aria-hidden="true" />
        <h2 className="mt-4 text-sm font-semibold text-slate-900">{title}</h2>
        <p className="mt-2 text-sm text-slate-500">{detail}</p>
      </div>
    </div>
  );
}

type ToastViewProps = {
  readonly toast: Toast;
};

function ToastView({ toast }: ToastViewProps) {
  const isError = toast.kind === 'error';
  return (
    <div
      role="status"
      aria-live="polite"
      className={`mb-6 flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm ${
        isError
          ? 'border-red-200 bg-red-50 text-red-800'
          : 'border-emerald-200 bg-emerald-50 text-emerald-800'
      }`}
      data-testid="office-detail-toast"
    >
      {isError ? <AlertCircle className="size-4 shrink-0" aria-hidden="true" /> : null}
      <p>{toast.message}</p>
    </div>
  );
}
