import { FlaskConical, Sparkles, X } from 'lucide-react';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import type { TransmuteResult } from '@/lib/api/entities';
import { cn } from '@/lib/utils';

type DistillResultModalProps = {
  readonly result: TransmuteResult | null;
  readonly onClose: () => void;
};

export default function DistillResultModal({ result, onClose }: DistillResultModalProps) {
  const { t } = useTranslation();

  useEffect(() => {
    if (result === null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [result, onClose]);

  if (result === null) return null;

  const preview = result.manifest_preview ?? {};
  const fieldValue = (key: string): string => {
    const v = preview[key as keyof typeof preview];
    if (v === undefined || v === null) return '—';
    if (Array.isArray(v)) return v.length === 0 ? '—' : v.join(', ');
    if (typeof v === 'string') return v;
    if (typeof v === 'number' || typeof v === 'boolean') return String(v);
    return JSON.stringify(v);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="distill-result-title"
      className="fixed inset-0 z-[60] grid place-items-center bg-slate-950/60 p-4"
      data-testid="distill-result-modal"
    >
      <div className="flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-purple-200 bg-white shadow-2xl">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="grid size-10 place-items-center rounded-lg bg-purple-100 text-purple-800">
              <FlaskConical className="size-5" aria-hidden="true" />
            </span>
            <div>
              <h2 id="distill-result-title" className="text-base font-semibold text-slate-950">
                {t('entityModal.distillResult.title')}
              </h2>
              <p className="text-xs text-slate-500">{t('entityModal.distillResult.subtitle')}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('entityModal.distillResult.close')}
            data-testid="distill-result-close"
            className="grid size-8 place-items-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </header>

        <div className="space-y-5 overflow-y-auto px-5 py-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {t('entityModal.distillResult.newBaseClass')}
              </p>
              <p
                className="mt-1 font-mono text-lg text-slate-950"
                data-testid="distill-result-slug"
              >
                {result.new_base_class_slug}
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {t('entityModal.distillResult.newBaseClassName')}
              </p>
              <p
                className="mt-1 text-sm font-medium text-slate-900"
                data-testid="distill-result-name"
              >
                {result.new_base_class_name}
              </p>
            </div>
          </div>

          <section
            aria-labelledby="distill-result-manifest-heading"
            className="rounded-lg border border-slate-200 bg-slate-50 p-4"
          >
            <h3
              id="distill-result-manifest-heading"
              className="text-xs font-semibold uppercase tracking-wide text-slate-500"
            >
              {t('entityModal.distillResult.manifestHeading')}
            </h3>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              <Row
                label={t('entityModal.distillResult.fieldProviderConfig')}
                value={fieldValue('provider_config')}
                mono
              />
              <Row
                label={t('entityModal.distillResult.fieldDefaultModel')}
                value={fieldValue('default_model')}
                mono
              />
              <Row
                label={t('entityModal.distillResult.fieldCommands')}
                value={fieldValue('commands')}
                mono
              />
              <Row
                label={t('entityModal.distillResult.fieldDefaultCapabilities')}
                value={fieldValue('default_capabilities')}
                mono
              />
              <Row
                label={t('entityModal.distillResult.fieldDefaultGeneRefs')}
                value={fieldValue('default_gene_refs')}
                mono
              />
              <Row
                label={t('entityModal.distillResult.fieldHasKnowledge')}
                value={fieldValue('has_knowledge')}
                mono
              />
              <Row
                label={t('entityModal.distillResult.fieldSystemPrompt')}
                value={fieldValue('system_prompt')}
              />
            </dl>
          </section>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {t('entityModal.distillResult.genesWritten')}
              </p>
              <ChipList
                values={result.default_gene_refs ?? []}
                emptyText={t('entityModal.distillResult.none')}
              />
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {t('entityModal.distillResult.knowledgeMounted')}
              </p>
              <ChipList
                values={result.has_knowledge ?? []}
                emptyText={t('entityModal.distillResult.none')}
              />
            </div>
          </div>
        </div>

        <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            data-testid="distill-result-close-2"
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            {t('entityModal.distillResult.close')}
          </button>
          <Link
            to={`/namespaces?tab=base-classes&focus=${encodeURIComponent(result.new_base_class_slug)}`}
            data-testid="distill-result-summon"
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-sm font-medium text-blue-800 transition-colors hover:bg-blue-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500',
            )}
          >
            <Sparkles className="size-4" aria-hidden="true" />
            {t('entityModal.distillResult.summonEntity')}
          </Link>
          <Link
            to={`/base-classes/${encodeURIComponent(result.new_base_class_slug)}`}
            data-testid="distill-result-view"
            className="inline-flex items-center gap-1.5 rounded-lg bg-purple-600 px-3 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-purple-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500"
          >
            {t('entityModal.distillResult.viewBaseClass')}
          </Link>
        </footer>
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  readonly label: string;
  readonly value: string;
  readonly mono?: boolean;
}) {
  return (
    <>
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className={cn('text-sm text-slate-900', mono ? 'font-mono break-words' : 'break-words')}>
        {value}
      </dd>
    </>
  );
}

function ChipList({
  values,
  emptyText,
}: {
  readonly values: readonly string[];
  readonly emptyText: string;
}) {
  if (values.length === 0) {
    return <p className="mt-1.5 text-xs text-slate-500">{emptyText}</p>;
  }
  return (
    <ul className="mt-1.5 flex flex-wrap gap-1">
      {values.map((value) => (
        <li
          key={value}
          className="inline-flex items-center rounded-md bg-white px-2 py-0.5 font-mono text-xs text-slate-700 ring-1 ring-slate-200"
        >
          {value}
        </li>
      ))}
    </ul>
  );
}
