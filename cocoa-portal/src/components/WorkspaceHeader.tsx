import { Building2, Cpu, LoaderCircle, Notebook, Sparkles, Users } from 'lucide-react';
import type { ReactElement } from 'react';
import { useTranslation } from 'react-i18next';
import WorkspaceHeaderMenu, {
  type WorkspaceHeaderMenuAction,
} from '@/components/WorkspaceHeaderMenu';
import type { Office } from '@/lib/types';
import { cn } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * Discrete health states derived from the live-status snapshot.
 *
 * - ``healthy`` — every instance is running / idle / completed
 * - ``warning`` — at least one paused / interrupted instance
 * - ``failed``  — at least one failed instance
 * - ``unknown`` — no live-status data yet (initial load)
 */
export type WorkspaceHealth = 'healthy' | 'warning' | 'failed' | 'unknown';

export type WorkspaceHeaderStats = {
  readonly entityCount: number;
  readonly instanceCount: number;
  readonly membershipCount: number;
  readonly centralHubSizeBytes: number;
};

export type WorkspaceHeaderProps = {
  readonly workspace: Office;
  readonly stats: WorkspaceHeaderStats;
  readonly health: WorkspaceHealth;
  readonly outdatedInstanceCount: number;
  readonly isLoading?: boolean;
  readonly onSummonEntity: () => void;
  readonly onMenuAction: (action: WorkspaceHeaderMenuAction) => void;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const HEALTH_BADGE: Readonly<
  Record<WorkspaceHealth, { readonly labelKey: string; readonly className: string }>
> = {
  healthy: {
    labelKey: 'workspaceHeader.health.healthy',
    className: 'bg-emerald-100 text-emerald-800',
  },
  warning: {
    labelKey: 'workspaceHeader.health.warning',
    className: 'bg-amber-100 text-amber-800',
  },
  failed: {
    labelKey: 'workspaceHeader.health.failed',
    className: 'bg-red-100 text-red-800',
  },
  unknown: {
    labelKey: 'workspaceHeader.health.unknown',
    className: 'bg-slate-100 text-slate-600',
  },
};

const HEALTH_DOT: Readonly<Record<WorkspaceHealth, string>> = {
  healthy: 'bg-emerald-500',
  warning: 'bg-amber-500',
  failed: 'bg-red-500',
  unknown: 'bg-slate-400',
};

function formatCentralHubSize(bytes: number): string {
  if (bytes <= 0) return '0 KB';
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const kb = bytes / 1024;
  if (kb < 1024) {
    // Round to 1 decimal for compactness.
    const rounded = Math.round(kb * 10) / 10;
    return `${Number.isInteger(rounded) ? rounded.toFixed(0) : rounded.toFixed(1)} KB`;
  }
  const mb = kb / 1024;
  return `${Math.round(mb * 10) / 10} MB`;
}

function daysSince(
  iso: string,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const diffMs = Date.now() - then;
  if (diffMs < 60_000) return t('workspaceHeader.createdJustNow');
  const days = Math.floor(diffMs / (24 * 60 * 60 * 1000));
  if (days <= 0) return t('workspaceHeader.createdJustNow');
  // i18next plural: with the count set, the resource picks _one vs _other.
  return t('workspaceHeader.createdDaysAgo', { count: days });
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function WorkspaceHeader({
  workspace,
  stats,
  health,
  outdatedInstanceCount,
  isLoading = false,
  onSummonEntity,
  onMenuAction,
}: WorkspaceHeaderProps): ReactElement {
  const { t } = useTranslation();
  const healthMeta = HEALTH_BADGE[health];
  const centralHubLabel = formatCentralHubSize(stats.centralHubSizeBytes);

  return (
    <header
      className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/80"
      data-testid="workspace-header"
    >
      <div className="mx-auto flex max-w-6xl items-start gap-4 px-4 py-4 sm:px-6 sm:py-5 lg:px-8">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
          <Building2 className="size-6" aria-hidden="true" />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <p className="font-mono text-xs text-slate-500">{workspace.slug}</p>
            <span className="text-xs text-slate-400">·</span>
            <p className="text-xs text-slate-500" data-testid="workspace-header-created">
              {daysSince(workspace.created_at, t)}
            </p>
          </div>
          <div className="mt-0.5 flex items-center gap-3">
            <h1
              className="truncate text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl"
              data-testid="workspace-header-title"
            >
              {workspace.name}
            </h1>
            <span
              className={cn(
                'inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold',
                healthMeta.className,
              )}
              data-testid="workspace-header-health"
              data-health={health}
            >
              <span className={cn('size-2 rounded-full', HEALTH_DOT[health])} aria-hidden="true" />
              {t(healthMeta.labelKey)}
            </span>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={onSummonEntity}
            disabled={isLoading}
            data-testid="workspace-header-summon"
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 active:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Sparkles className="size-4" aria-hidden="true" />
            <span className="hidden sm:inline">{t('workspaceHeader.summonEntity')}</span>
            <span className="sm:hidden">{t('workspaceHeader.summonEntity')}</span>
          </button>
          <WorkspaceHeaderMenu
            outdatedInstanceCount={outdatedInstanceCount}
            onAction={onMenuAction}
          />
        </div>
      </div>

      <div className="mx-auto grid max-w-6xl grid-cols-2 gap-2 px-4 pb-4 sm:grid-cols-4 sm:px-6 sm:pb-5 lg:px-8">
        <StatCard
          icon={Users}
          label={t('workspaceHeader.statsEntities')}
          value={stats.entityCount}
          testId="workspace-header-stat-entities"
        />
        <StatCard
          icon={Cpu}
          label={t('workspaceHeader.statsInstances')}
          value={stats.instanceCount}
          testId="workspace-header-stat-instances"
          suffix={
            outdatedInstanceCount > 0 ? (
              <span
                className="ml-1 inline-flex items-center rounded-full bg-amber-100 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-amber-800"
                data-testid="workspace-header-outdated-badge"
              >
                {t('workspaceHeader.menuBatchRestartBadge', {
                  count: outdatedInstanceCount,
                })}
              </span>
            ) : null
          }
        />
        <StatCard
          icon={Notebook}
          label={t('workspaceHeader.statsMemberships')}
          value={stats.membershipCount}
          testId="workspace-header-stat-memberships"
        />
        <StatCard
          icon={Cpu}
          label={t('workspaceHeader.statsCentralHub')}
          value={centralHubLabel}
          isText
          testId="workspace-header-stat-central-hub"
        />
      </div>

      {isLoading ? (
        <div
          className="flex items-center justify-center gap-2 border-t border-slate-100 bg-slate-50 py-1.5 text-xs text-slate-500"
          aria-live="polite"
        >
          <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
          {t('common.loading')}
        </div>
      ) : null}
    </header>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

type StatCardProps = {
  readonly icon: typeof Users;
  readonly label: string;
  readonly value: number | string;
  readonly isText?: boolean;
  readonly suffix?: ReactElement | null;
  readonly testId?: string;
};

function StatCard({
  icon: Icon,
  label,
  value,
  isText,
  suffix,
  testId,
}: StatCardProps): ReactElement {
  return (
    <div
      className="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5"
      data-testid={testId}
    >
      <span className="grid size-8 shrink-0 place-items-center rounded-md bg-white text-slate-600 shadow-sm">
        <Icon className="size-4" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <p className="text-[10px] font-medium uppercase tracking-wider text-slate-500">{label}</p>
        <p
          className={cn(
            'mt-0.5 inline-flex items-baseline font-semibold text-slate-900',
            isText ? 'text-sm font-mono' : 'text-lg tabular-nums',
          )}
        >
          {value}
          {suffix}
        </p>
      </div>
    </div>
  );
}
