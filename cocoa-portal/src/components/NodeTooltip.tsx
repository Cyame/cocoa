import { MessageSquare, RefreshCw, Search } from 'lucide-react';
import type { ReactElement } from 'react';
import { useTranslation } from 'react-i18next';
import type { TopologyNode } from '@/lib/types';

type NodeTooltipProps = {
  readonly node: TopologyNode;
  readonly onOpen: () => void;
};

export function NodeTooltip({ node, onOpen }: NodeTooltipProps): ReactElement {
  const { t } = useTranslation();
  const isInstance = node.instanceId !== null;
  return (
    <foreignObject
      x={-160}
      y={-224}
      width={320}
      height={160}
      data-testid={`topology-tooltip-${node.id}`}
    >
      <div className="mx-auto min-w-40 max-w-80 rounded-lg border border-slate-200 bg-white p-3 text-left text-xs text-slate-700 shadow-xl">
        <div className="flex items-center justify-between gap-3">
          <strong className="truncate text-sm text-slate-950">{node.label}</strong>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium">{node.status}</span>
        </div>
        <p className="mt-1 truncate font-mono text-slate-500">{node.slug}</p>
        {isInstance ? (
          <div className="mt-2 grid grid-cols-2 gap-1 border-t border-slate-100 pt-2">
            <span>{t('topology.continuationCount')}</span>
            <span className="text-right">—</span>
            <span>{t('topology.lastCheckpoint')}</span>
            <span className="text-right">—</span>
            <span>{t('topology.outdated')}</span>
            <span
              className={node.outdated ? 'text-right font-semibold text-red-600' : 'text-right'}
            >
              {node.outdated ? t('topology.yes') : t('topology.no')}
            </span>
          </div>
        ) : null}
        {isInstance ? (
          <div className="mt-2 flex flex-wrap gap-1 border-t border-slate-100 pt-2">
            <button
              type="button"
              onClick={onOpen}
              className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-1 hover:bg-slate-200"
            >
              <Search className="size-3" />
              {t('topology.viewDetails')}
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-1 hover:bg-slate-200"
            >
              <MessageSquare className="size-3" />
              {t('topology.chatInComposer')}
            </button>
            {node.outdated ? (
              <button
                type="button"
                className="inline-flex items-center gap-1 rounded bg-amber-500 px-2 py-1 text-white hover:bg-amber-600"
              >
                <RefreshCw className="size-3" />
                {t('topology.restartToUpdate')}
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </foreignObject>
  );
}
