import { AlertCircle, FlaskConical } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import TransmuteModal from '@/components/TransmuteModal';
import type { EntityDetail } from '@/lib/api/entities';

type DistillTabProps = {
  readonly entity: EntityDetail;
  readonly canTransmute: boolean;
  readonly onTransmute: (
    targetSlug: string,
    targetName: string,
    kinds: readonly import('@/lib/types').MemoryKind[] | null,
  ) => Promise<void>;
};

export default function DistillTab({ entity, canTransmute, onTransmute }: DistillTabProps) {
  const { t } = useTranslation();
  const [transmuteOpen, setTransmuteOpen] = useState(false);

  return (
    <section aria-labelledby="distill-tab-heading" className="space-y-5">
      <header>
        <h2 id="distill-tab-heading" className="text-sm font-semibold text-slate-900">
          {t('entityModal.tabs.distill')}
        </h2>
        <p className="mt-1 text-xs text-slate-500">{t('entityModal.distillTab.intro')}</p>
        <p className="mt-2 text-xs text-slate-500">{t('entityModal.distillTab.promoteMovedHint')}</p>
      </header>

      <article
        className={`rounded-xl border p-4 ${canTransmute ? 'border-purple-200 bg-purple-50/40' : 'border-slate-200 bg-slate-50'}`}
        data-testid="distill-transmute-section"
      >
        <div className="flex items-start gap-3">
          <span
            className={`grid size-9 place-items-center rounded-lg ${canTransmute ? 'bg-purple-100 text-purple-800' : 'bg-slate-100 text-slate-500'}`}
          >
            <FlaskConical className="size-4" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h3
              className={`text-sm font-semibold ${canTransmute ? 'text-purple-900' : 'text-slate-700'}`}
            >
              {t('transmuteModal.title')}
            </h3>
            <p
              className={`mt-1 text-xs ${canTransmute ? 'text-purple-900/80' : 'text-slate-500'}`}
            >
              {canTransmute
                ? t('transmuteModal.summary')
                : t('entityModal.errors.permission', { cap: 'can_transmute_entity' })}
            </p>
            <button
              type="button"
              onClick={() => setTransmuteOpen(true)}
              disabled={!canTransmute}
              data-testid="distill-open-transmute"
              className="mt-3 inline-flex items-center gap-2 rounded-lg bg-purple-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-purple-700 disabled:cursor-not-allowed disabled:bg-purple-200"
            >
              <FlaskConical className="size-3.5" aria-hidden="true" />
              {t('transmuteModal.open')}
            </button>
          </div>
        </div>
      </article>

      {!canTransmute ? (
        <div
          role="note"
          className="flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600"
        >
          <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <span>{t('entityModal.errors.permission', { cap: 'can_transmute_entity' })}</span>
        </div>
      ) : null}

      <p className="text-xs text-slate-500" data-testid="distill-entity-id">
        {entity.slug}
      </p>

      {transmuteOpen ? (
        <TransmuteModal
          entity={entity}
          onClose={() => setTransmuteOpen(false)}
          onSubmit={onTransmute}
        />
      ) : null}
    </section>
  );
}
