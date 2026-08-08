import { AlertCircle, FlaskConical, LoaderCircle, Sparkles, Wand2 } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import TransmuteModal from '@/components/TransmuteModal';
import type { EntityDetail } from '@/lib/api/entities';
import { resolveError } from '@/lib/apiError';
import type { DistillEngine, DistillResultOut, MemoryKind } from '@/lib/types';
import { cn } from '@/lib/utils';

const SLUG_PATTERN = /^[a-z][a-z0-9-]*$/;

type DistillTabProps = {
  readonly entity: EntityDetail;
  readonly canTransmute: boolean;
  readonly onTransmute: (
    targetSlug: string,
    targetName: string,
    kinds: readonly MemoryKind[] | null,
  ) => Promise<void>;
  readonly onDistill: (targetSkillSlug: string, engine: DistillEngine) => Promise<DistillResultOut>;
};

export default function DistillTab({
  entity,
  canTransmute,
  onTransmute,
  onDistill,
}: DistillTabProps) {
  const { t } = useTranslation();
  const [transmuteOpen, setTransmuteOpen] = useState(false);
  const [targetSlug, setTargetSlug] = useState('');
  const [engine, setEngine] = useState<DistillEngine>('heuristic');
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<DistillResultOut | null>(null);

  const slugValid = SLUG_PATTERN.test(targetSlug.trim());
  const ready = targetSlug.trim().length > 0 && slugValid;

  async function handleDistill() {
    if (!ready || submitting) return;
    setSubmitting(true);
    setErrorMessage(null);
    setResult(null);
    try {
      const out = await onDistill(targetSlug.trim(), engine);
      setResult(out);
    } catch (error) {
      setErrorMessage(resolveError(t, error, 'entityModal.distillTab.distill.error'));
    } finally {
      setSubmitting(false);
    }
  }

  const degraded = result?.warnings.includes('llm_unavailable_degraded_to_heuristic') === true;

  return (
    <section aria-labelledby="distill-tab-heading" className="space-y-5">
      <header>
        <h2 id="distill-tab-heading" className="text-sm font-semibold text-slate-900">
          {t('entityModal.tabs.distill')}
        </h2>
        <p className="mt-1 text-xs text-slate-500">{t('entityModal.distillTab.intro')}</p>
        <p className="mt-2 text-xs text-slate-500">
          {t('entityModal.distillTab.promoteMovedHint')}
        </p>
      </header>

      <article
        className="rounded-xl border border-blue-200 bg-blue-50/40 p-4"
        data-testid="distill-distill-section"
      >
        <div className="flex items-start gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-blue-100 text-blue-800">
            <Wand2 className="size-4" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-blue-900">
              {t('entityModal.distillTab.distill.title')}
            </h3>
            <p className="mt-1 text-xs text-blue-900/80">
              {t('entityModal.distillTab.distill.intro')}
            </p>

            <div className="mt-3 grid items-start gap-3 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="distill-skill-slug"
                  className="block text-xs font-semibold uppercase tracking-wide text-slate-600"
                >
                  {t('entityModal.distillTab.distill.skillSlugLabel')}
                </label>
                <input
                  id="distill-skill-slug"
                  type="text"
                  value={targetSlug}
                  onChange={(e) => setTargetSlug(e.target.value)}
                  placeholder={t('entityModal.distillTab.distill.skillSlugPlaceholder')}
                  data-testid="distill-skill-slug"
                  className="mt-1.5 h-[38px] w-full rounded-lg border border-slate-300 px-3 font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                />
                {!slugValid && targetSlug.length > 0 ? (
                  <p className="mt-1 text-xs text-red-700">
                    {t('entityModal.distillTab.distill.skillSlugPattern')}
                  </p>
                ) : null}
              </div>
              <fieldset>
                <legend className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                  {t('entityModal.distillTab.distill.engineLabel')}
                </legend>
                <div className="mt-1.5 flex gap-2">
                  {(['heuristic', 'llm'] as const).map((value) => (
                    <label
                      key={value}
                      className={cn(
                        'flex h-[38px] cursor-pointer items-center gap-2 rounded-lg border px-3 text-sm',
                        engine === value
                          ? 'border-blue-500 bg-blue-50 text-blue-900'
                          : 'border-slate-200 bg-white text-slate-700',
                      )}
                    >
                      <input
                        type="radio"
                        name="distill-engine"
                        value={value}
                        checked={engine === value}
                        onChange={() => setEngine(value)}
                        className="size-4 accent-blue-600"
                        data-testid={`distill-engine-${value}`}
                      />
                      {t(`entityModal.distillTab.distill.engine.${value}`)}
                    </label>
                  ))}
                </div>
              </fieldset>
            </div>

            <button
              type="button"
              onClick={() => void handleDistill()}
              disabled={!ready || submitting}
              data-testid="distill-submit"
              className={cn(
                'mt-3 inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-semibold text-white',
                ready && !submitting
                  ? 'bg-blue-600 hover:bg-blue-700'
                  : 'cursor-not-allowed bg-blue-200',
              )}
            >
              {submitting ? (
                <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
              ) : (
                <Wand2 className="size-3.5" aria-hidden="true" />
              )}
              {submitting
                ? t('entityModal.distillTab.distill.submitting')
                : t('entityModal.distillTab.distill.submit')}
            </button>
          </div>
        </div>

        {errorMessage !== null ? (
          <div
            role="alert"
            className="mt-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
          >
            <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <p>{errorMessage}</p>
          </div>
        ) : null}

        {result !== null ? (
          <div className="mt-4 space-y-3" data-testid="distill-result-view">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-md bg-blue-100 px-2 py-0.5 font-mono text-xs text-blue-900">
                <Sparkles className="size-3" aria-hidden="true" />
                {t('entityModal.distillTab.distill.engineUsed', { engine: result.engine_used })}
              </span>
              <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
                {t('entityModal.distillTab.distill.createdCount', {
                  count: result.capability_market_created,
                })}
              </span>
              {result.gene_suggestion !== null && result.gene_suggestion !== '' ? (
                <span className="inline-flex items-center gap-1.5 rounded-md bg-purple-100 px-2 py-0.5 font-mono text-xs text-purple-900">
                  <FlaskConical className="size-3" aria-hidden="true" />
                  {t('entityModal.distillTab.distill.geneSuggestion')}: {result.gene_suggestion}
                </span>
              ) : null}
            </div>

            {degraded ? (
              <div
                role="note"
                className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"
                data-testid="distill-degraded-warning"
              >
                <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                <span>{t('entityModal.distillTab.distill.engineDegradedWarning')}</span>
              </div>
            ) : null}

            {result.warnings.length > 0 ? (
              <ul className="space-y-1" data-testid="distill-warnings">
                {result.warnings.map((warning) => (
                  <li
                    key={warning}
                    className="flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700"
                  >
                    <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                    <span>{warning}</span>
                  </li>
                ))}
              </ul>
            ) : null}

            {result.capability_candidates.length === 0 ? (
              <p className="rounded-lg border border-dashed border-slate-300 px-3 py-3 text-xs text-slate-500">
                {t('entityModal.distillTab.distill.noCandidates')}
              </p>
            ) : (
              <ul className="grid gap-2" data-testid="distill-candidates">
                {result.capability_candidates.map((candidate) => (
                  <li
                    key={candidate.name}
                    className="rounded-lg border border-slate-200 bg-white p-3"
                    data-testid="distill-candidate"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-sm font-semibold text-slate-900">
                        {candidate.name}
                      </span>
                      <span className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-600">
                        {candidate.type}
                      </span>
                    </div>
                    {candidate.description ? (
                      <p className="mt-1 text-xs text-slate-600">{candidate.description}</p>
                    ) : null}
                    {candidate.required_knowledge.length > 0 ? (
                      <p className="mt-2 flex flex-wrap items-center gap-1 text-xs">
                        <span className="text-slate-500">
                          {t('entityModal.distillTab.distill.requiredKnowledge')}:
                        </span>
                        {candidate.required_knowledge.map((slug) => (
                          <span
                            key={slug}
                            className="rounded-md bg-blue-50 px-1.5 py-0.5 font-mono text-blue-800 ring-1 ring-blue-100"
                          >
                            {slug}
                          </span>
                        ))}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : null}
      </article>

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
            <p className={`mt-1 text-xs ${canTransmute ? 'text-purple-900/80' : 'text-slate-500'}`}>
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
