import { AlertCircle, ExternalLink, LoaderCircle, Recycle, Search, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { EntityInstanceStatus } from '@/lib/types';
import { cn } from '@/lib/utils';

type StatusFilter = 'all' | EntityInstanceStatus['loop_status'];

const STATUS_PRIORITY: Readonly<Record<EntityInstanceStatus['loop_status'], number>> = {
  failed: 0,
  interrupted: 1,
  paused: 2,
  running: 3,
  idle: 4,
  completed: 5,
};

const STATUS_BADGE_CLASS: Readonly<Record<EntityInstanceStatus['loop_status'], string>> = {
  running: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  idle: 'border-yellow-200 bg-yellow-50 text-yellow-800',
  paused: 'border-slate-200 bg-slate-100 text-slate-700',
  interrupted: 'border-orange-200 bg-orange-50 text-orange-800',
  completed: 'border-blue-200 bg-blue-50 text-blue-800',
  failed: 'border-red-200 bg-red-50 text-red-800',
};

type InstancesTabProps = {
  readonly instances: readonly EntityInstanceStatus[];
  readonly isLoading: boolean;
  readonly errorMessage: string | null;
  readonly onReap: (instance: EntityInstanceStatus) => void;
  readonly onDelete: (instance: EntityInstanceStatus) => void;
};

export default function InstancesTab({
  instances,
  isLoading,
  errorMessage,
  onReap,
  onDelete,
}: InstancesTabProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [onlyFailed, setOnlyFailed] = useState(false);
  const [onlyRunning, setOnlyRunning] = useState(false);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return instances
      .filter((inst) => {
        if (onlyFailed && inst.loop_status !== 'failed') return false;
        if (onlyRunning && inst.loop_status !== 'running') return false;
        if (statusFilter !== 'all' && inst.loop_status !== statusFilter) return false;
        if (q === '') return true;
        return (
          inst.id.toLowerCase().includes(q) ||
          (inst.pod_name ?? '').toLowerCase().includes(q) ||
          inst.loop_status.includes(q)
        );
      })
      .slice()
      .sort((a, b) => {
        const pa = STATUS_PRIORITY[a.loop_status] ?? 99;
        const pb = STATUS_PRIORITY[b.loop_status] ?? 99;
        if (pa !== pb) return pa - pb;
        return b.spawn_time.localeCompare(a.spawn_time);
      });
  }, [instances, query, onlyFailed, onlyRunning, statusFilter]);

  const counters = useMemo(() => {
    const counts = { running: 0, idle: 0, failed: 0 };
    for (const inst of instances) {
      if (inst.loop_status === 'running') counts.running += 1;
      else if (inst.loop_status === 'idle') counts.idle += 1;
      else if (inst.loop_status === 'failed') counts.failed += 1;
    }
    return counts;
  }, [instances]);

  const totalInstances = instances.length;
  const healthKind: 'healthy' | 'degraded' = counters.failed > 0 ? 'degraded' : 'healthy';

  return (
    <section aria-labelledby="instances-tab-heading" className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="instances-tab-heading" className="text-sm font-semibold text-slate-900">
          {t('entityModal.tabs.instances')}
        </h2>
        <span
          className={cn(
            'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold',
            healthKind === 'healthy'
              ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
              : 'border-red-200 bg-red-50 text-red-800',
          )}
          data-testid="instances-health"
        >
          {t(
            healthKind === 'healthy'
              ? 'entityModal.instancesTab.healthHealthy'
              : 'entityModal.instancesTab.healthDegraded',
          )}
        </span>
      </header>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <CounterCard label={t('entityModal.instancesTab.total')} value={totalInstances} />
        <CounterCard label={t('entityModal.instancesTab.running')} value={counters.running} />
        <CounterCard label={t('entityModal.instancesTab.idle')} value={counters.idle} />
        <CounterCard label={t('entityModal.instancesTab.failed')} value={counters.failed} />
      </dl>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5">
          <Search className="size-4 shrink-0 text-slate-400" aria-hidden="true" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('entityModal.instancesTab.searchPlaceholder')}
            data-testid="instances-search"
            className="w-48 bg-transparent text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none"
          />
        </div>
        <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-slate-700">
          <input
            type="checkbox"
            checked={onlyFailed}
            onChange={(e) => setOnlyFailed(e.target.checked)}
            data-testid="instances-only-failed"
            className="size-4 accent-red-600"
          />
          {t('entityModal.instancesTab.onlyFailed')}
        </label>
        <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-slate-700">
          <input
            type="checkbox"
            checked={onlyRunning}
            onChange={(e) => setOnlyRunning(e.target.checked)}
            data-testid="instances-only-running"
            className="size-4 accent-emerald-600"
          />
          {t('entityModal.instancesTab.onlyRunning')}
        </label>
        <label className="inline-flex items-center gap-2 text-xs text-slate-700">
          <span className="font-semibold uppercase tracking-wide text-slate-500">
            {t('entityModal.instancesTab.filterByStatus')}
          </span>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
            data-testid="instances-status-filter"
            className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <option value="all">{t('entityModal.instancesTab.allStatuses')}</option>
            {(['running', 'idle', 'paused', 'interrupted', 'completed', 'failed'] as const).map(
              (s) => (
                <option key={s} value={s}>
                  {t(`instance.loopStatus.${s}`)}
                </option>
              ),
            )}
          </select>
        </label>
      </div>

      {errorMessage !== null ? (
        <div
          role="alert"
          className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800"
        >
          <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
          <p>{errorMessage}</p>
        </div>
      ) : null}

      {isLoading ? (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-slate-300 p-6 text-sm text-slate-500">
          <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
          {t('entityModal.instancesTab.loading')}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
          <p className="text-sm font-semibold text-slate-900">
            {t('entityModal.instancesTab.emptyTitle')}
          </p>
          <p className="mt-2 text-xs text-slate-500">{t('entityModal.instancesTab.emptyDetail')}</p>
          <button
            type="button"
            className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-800 transition-colors hover:bg-blue-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            data-testid="instances-spawn-cta"
          >
            {t('entityModal.instancesTab.spawnCta')}
          </button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <table
            className="min-w-full divide-y divide-slate-200 text-sm"
            data-testid="instances-table"
          >
            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-3 py-2">{t('entityModal.instancesTab.columnId')}</th>
                <th className="px-3 py-2">{t('entityModal.instancesTab.columnStatus')}</th>
                <th className="px-3 py-2">{t('entityModal.instancesTab.columnContinuations')}</th>
                <th className="px-3 py-2">{t('entityModal.instancesTab.columnPod')}</th>
                <th className="px-3 py-2">{t('entityModal.instancesTab.columnSpawn')}</th>
                <th className="px-3 py-2">{t('entityModal.instancesTab.columnActive')}</th>
                <th className="px-3 py-2 text-right">
                  {t('entityModal.instancesTab.columnActions')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((inst) => (
                <InstanceRow key={inst.id} instance={inst} onReap={onReap} onDelete={onDelete} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function CounterCard({ label, value }: { readonly label: string; readonly value: number }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</dd>
    </div>
  );
}

function InstanceRow({
  instance,
  onReap,
  onDelete,
}: {
  readonly instance: EntityInstanceStatus;
  readonly onReap: (inst: EntityInstanceStatus) => void;
  readonly onDelete: (inst: EntityInstanceStatus) => void;
}) {
  const { t } = useTranslation();
  const shortId = instance.id.slice(0, 8);
  const podShort = instance.pod_name ? instance.pod_name.slice(0, 32) : '—';
  return (
    <tr data-testid={`instance-row-${instance.id}`}>
      <td className="px-3 py-2 font-mono text-xs text-slate-900" title={instance.id}>
        {shortId}
      </td>
      <td className="px-3 py-2">
        <span
          className={cn(
            'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold',
            STATUS_BADGE_CLASS[instance.loop_status],
          )}
        >
          {t(`instance.loopStatus.${instance.loop_status}`)}
        </span>
      </td>
      <td className="px-3 py-2 font-mono text-xs tabular-nums text-slate-700">
        {instance.continuation_count}
      </td>
      <td className="px-3 py-2 font-mono text-xs text-slate-700" title={instance.pod_name ?? ''}>
        {podShort}
      </td>
      <td className="px-3 py-2 font-mono text-xs text-slate-700">{instance.spawn_time}</td>
      <td className="px-3 py-2 font-mono text-xs text-slate-700">
        {instance.last_active_at ?? '—'}
      </td>
      <td className="px-3 py-2">
        <div className="flex items-center justify-end gap-1.5">
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded-md border border-transparent px-2 py-1 text-xs font-medium text-blue-700 transition-colors hover:border-blue-200 hover:bg-blue-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            title={t('entityModal.instancesTab.goToWorkspace')}
            data-testid="instance-go-workspace"
          >
            <ExternalLink className="size-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => onReap(instance)}
            data-testid="instance-reap"
            className="inline-flex items-center gap-1 rounded-md border border-transparent px-2 py-1 text-xs font-medium text-emerald-700 transition-colors hover:border-emerald-200 hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
            title={t('entityModal.instancesTab.reap')}
          >
            <Recycle className="size-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => onDelete(instance)}
            data-testid="instance-delete"
            className="inline-flex items-center gap-1 rounded-md border border-transparent px-2 py-1 text-xs font-medium text-red-700 transition-colors hover:border-red-200 hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
            title={t('entityModal.instancesTab.delete')}
          >
            <Trash2 className="size-3.5" aria-hidden="true" />
          </button>
        </div>
      </td>
    </tr>
  );
}
