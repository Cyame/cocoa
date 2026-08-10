import { ChevronRight, LoaderCircle, Wrench } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { ActivityItem } from '@/lib/composerTranscript';
import { cn } from '@/lib/utils';

export function ActivityBlock({ activities }: { readonly activities: readonly ActivityItem[] }) {
  if (activities.length === 0) return null;

  return (
    <div className="mb-1 space-y-1">
      {activities.map((item) => {
        if (item.kind === 'thinking') {
          return <ThinkingFold key={`act-${item.id}`} item={item} />;
        }
        return <ToolUseCard key={`act-${item.id}`} item={item} />;
      })}
    </div>
  );
}

function ThinkingFold({ item }: { readonly item: ActivityItem }) {
  const { t } = useTranslation();
  const content = item.deltas.trim();
  const isActive = item.status !== 'end';
  return (
    <details
      className="rounded border border-amber-200 bg-amber-50 text-[11px] text-amber-900"
      data-testid="activity-thinking"
    >
      <summary className="flex cursor-pointer select-none items-center gap-1 px-2 py-1 font-medium">
        <ChevronRight
          className="size-3 shrink-0 transition-transform open:rotate-90"
          aria-hidden="true"
        />
        {t('composer.activity.thinkingLabel')}
        {isActive ? (
          <LoaderCircle className="size-3 animate-spin text-amber-500" aria-hidden="true" />
        ) : null}
      </summary>
      {content ? (
        <pre className="whitespace-pre-wrap break-words border-t border-amber-200 px-2 py-1 font-sans opacity-90">
          {content}
        </pre>
      ) : null}
    </details>
  );
}

function ToolUseCard({ item }: { readonly item: ActivityItem }) {
  const { t } = useTranslation();
  const isActive = item.status !== 'end';
  const displayDeltas = item.deltas.trim();

  if (item.isDelegation) {
    const agentName = item.toolName ?? 'agent';
    return (
      <div
        className={cn(
          'flex items-center gap-1.5 rounded px-2 py-1 text-[11px]',
          isActive ? 'bg-violet-50 text-violet-800' : 'bg-slate-100 text-slate-600',
        )}
        data-testid="activity-delegation"
      >
        {isActive ? (
          <LoaderCircle className="size-3 animate-spin shrink-0" aria-hidden="true" />
        ) : (
          <ChevronRight className="size-3 shrink-0" aria-hidden="true" />
        )}
        <span>{t('composer.activity.delegated', { agent: agentName })}</span>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'rounded border px-2 py-1 text-[11px]',
        isActive
          ? 'border-slate-300 bg-slate-50 text-slate-800'
          : 'border-slate-200 bg-slate-50/60 text-slate-600',
      )}
      data-testid="activity-tool-use"
    >
      <div className="flex items-center gap-1.5">
        <Wrench className="size-3 shrink-0 text-slate-400" aria-hidden="true" />
        <span className="font-mono font-medium">{item.toolName}</span>
        <ToolStatusBadge status={item.status} />
        {isActive ? (
          <LoaderCircle className="size-3 animate-spin text-slate-400" aria-hidden="true" />
        ) : null}
      </div>
      {displayDeltas ? (
        <pre className="mt-0.5 whitespace-pre-wrap break-words font-sans opacity-80">
          {displayDeltas}
        </pre>
      ) : null}
    </div>
  );
}

function ToolStatusBadge({ status }: { readonly status: ActivityItem['status'] }) {
  const cls =
    status === 'start'
      ? 'bg-blue-100 text-blue-700'
      : status === 'delta'
        ? 'bg-amber-100 text-amber-700'
        : 'bg-emerald-100 text-emerald-700';
  return <span className={`rounded px-1 py-0.5 text-[9px] font-medium ${cls}`}>{status}</span>;
}
