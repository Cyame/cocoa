import { LoaderCircle, Lock, Plus, Search, Trash2, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  type AiGeneCatalogItem,
  attachAiGeneToEntity,
  detachAiGeneFromEntity,
  listAiGenes,
} from '@/lib/api/aiGenes';
import type { EntityDetail } from '@/lib/api/entities';
import { resolveError } from '@/lib/apiError';
import type { AiGene, AiGeneKind } from '@/lib/types';
import { cn } from '@/lib/utils';

type AiGenesTabProps = {
  readonly entity: EntityDetail;
  readonly onRefresh: () => Promise<void>;
  readonly onNotify: (kind: 'success' | 'error', message: string) => void;
};

const KIND_LABEL: Readonly<Record<AiGeneKind, string>> = {
  'tool-gene': 'tool-gene',
  'meta-gene': 'meta-gene',
  genome: 'genome',
  'workflow-gene': 'workflow-gene',
};

export default function AiGenesTab({ entity, onRefresh, onNotify }: AiGenesTabProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [catalog, setCatalog] = useState<readonly AiGeneCatalogItem[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [attachBusy, setAttachBusy] = useState<string | null>(null);
  const [pickerQuery, setPickerQuery] = useState('');

  const geneLookup = useMemo(() => buildGeneLookup(entity), [entity]);
  const attachedSlugs = useMemo(() => new Set(geneLookup.all.map((g) => g.slug)), [geneLookup]);

  const loadCatalog = useCallback(async () => {
    setCatalogLoading(true);
    setCatalogError(null);
    try {
      const page = await listAiGenes();
      setCatalog(page.items);
    } catch (error) {
      setCatalogError(resolveError(t, error));
    } finally {
      setCatalogLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (!showAddModal) return;
    void loadCatalog();
  }, [showAddModal, loadCatalog]);

  const slugToId = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of catalog) {
      map.set(item.slug, item.id);
    }
    return map;
  }, [catalog]);

  const filtered = useMemo(() => {
    if (query.trim() === '') return geneLookup.all;
    const q = query.trim().toLowerCase();
    return geneLookup.all.filter(
      (g) =>
        g.slug.includes(q) ||
        g.name.toLowerCase().includes(q) ||
        g.tags.some((tag) => tag.toLowerCase().includes(q)),
    );
  }, [geneLookup, query]);

  const pickerItems = useMemo(() => {
    const q = pickerQuery.trim().toLowerCase();
    return catalog.filter((gene) => {
      if (gene.scope === 'system') return false;
      if (attachedSlugs.has(gene.slug)) return false;
      if (q === '') return true;
      return (
        gene.slug.includes(q) ||
        gene.name.toLowerCase().includes(q) ||
        (gene.tags ?? []).some((tag) => tag.toLowerCase().includes(q))
      );
    });
  }, [attachedSlugs, catalog, pickerQuery]);

  const fromBase = useMemo(
    () => filtered.filter((g) => g.source === 'from_base_class'),
    [filtered],
  );
  const extras = useMemo(() => filtered.filter((g) => g.source === 'extra_added'), [filtered]);

  const handleAttach = async (gene: AiGeneCatalogItem) => {
    setAttachBusy(gene.id);
    try {
      await attachAiGeneToEntity(entity.id, gene.id);
      setShowAddModal(false);
      setPickerQuery('');
      await onRefresh();
      onNotify('success', t('entityModal.aiGenesTab.attachSuccess'));
    } catch (error) {
      onNotify('error', resolveError(t, error, 'entityModal.aiGenesTab.attachFailed'));
    } finally {
      setAttachBusy(null);
    }
  };

  const handleRemove = async (gene: AiGene) => {
    if (gene.source === 'from_base_class') return;
    let geneId = slugToId.get(gene.slug);
    if (geneId === undefined) {
      try {
        const page = await listAiGenes();
        geneId = page.items.find((item) => item.slug === gene.slug)?.id;
      } catch {
        onNotify('error', t('entityModal.aiGenesTab.detachFailed'));
        return;
      }
    }
    if (geneId === undefined) {
      onNotify('error', t('entityModal.aiGenesTab.detachFailed'));
      return;
    }
    try {
      await detachAiGeneFromEntity(entity.id, geneId);
      await onRefresh();
      onNotify('success', t('entityModal.aiGenesTab.detachSuccess'));
    } catch (error) {
      onNotify('error', resolveError(t, error, 'entityModal.aiGenesTab.detachFailed'));
    }
  };

  return (
    <section aria-labelledby="genes-tab-heading" className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="genes-tab-heading" className="text-sm font-semibold text-slate-900">
          {t('entityModal.tabs.ai_genes')}
        </h2>
        <button
          type="button"
          onClick={() => setShowAddModal(true)}
          data-testid="genes-add-extra"
          className="inline-flex items-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-800 transition-colors hover:bg-blue-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
        >
          <Plus className="size-3.5" aria-hidden="true" />
          {t('entityModal.aiGenesTab.addExtra')}
        </button>
      </header>

      <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5">
        <Search className="size-4 shrink-0 text-slate-400" aria-hidden="true" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('entityModal.aiGenesTab.addExtraSearchPlaceholder')}
          className="w-full bg-transparent text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none"
          data-testid="genes-search"
        />
      </div>

      {filtered.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500">
          {t('entityModal.aiGenesTab.addExtraEmpty')}
        </p>
      ) : (
        <div className="space-y-4">
          {fromBase.length > 0 ? (
            <GeneGroup
              heading={t('entityModal.aiGenesTab.fromBaseClass')}
              headingKey="fromBaseClass"
              genes={fromBase}
              locked
              lockedHint={t('entityModal.aiGenesTab.lockedHint')}
              moveLabel={t('entityModal.aiGenesTab.moveToBaseClass')}
              removeLabel={t('entityModal.aiGenesTab.remove')}
              onRemove={(g) => void handleRemove(g)}
            />
          ) : null}
          {extras.length > 0 ? (
            <GeneGroup
              heading={t('entityModal.aiGenesTab.extraAdded')}
              headingKey="extraAdded"
              genes={extras}
              lockedHint={t('entityModal.aiGenesTab.lockedHint')}
              moveLabel={t('entityModal.aiGenesTab.moveToBaseClass')}
              removeLabel={t('entityModal.aiGenesTab.remove')}
              onRemove={(g) => void handleRemove(g)}
            />
          ) : null}
        </div>
      )}

      {showAddModal ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="genes-add-modal-title"
          className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/40 p-4"
          data-testid="genes-add-modal"
        >
          <div className="flex max-h-[min(80vh,560px)] w-full max-w-lg flex-col rounded-xl border border-slate-200 bg-white shadow-lg">
            <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-4 py-3">
              <div>
                <h3 id="genes-add-modal-title" className="text-sm font-semibold text-slate-900">
                  {t('entityModal.aiGenesTab.addExtraTitle')}
                </h3>
                <p className="mt-0.5 text-xs text-slate-500">
                  {t('entityModal.aiGenesTab.attachPick')}
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setShowAddModal(false);
                  setPickerQuery('');
                }}
                className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                aria-label={t('entityModal.aiGenesTab.cancelPick')}
              >
                <X className="size-4" aria-hidden="true" />
              </button>
            </header>
            <div className="border-b border-slate-100 px-4 py-2">
              <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5">
                <Search className="size-4 shrink-0 text-slate-400" aria-hidden="true" />
                <input
                  type="text"
                  value={pickerQuery}
                  onChange={(e) => setPickerQuery(e.target.value)}
                  placeholder={t('entityModal.aiGenesTab.addExtraSearchPlaceholder')}
                  className="w-full bg-transparent text-sm focus:outline-none"
                />
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
              {catalogLoading ? (
                <div className="flex items-center justify-center gap-2 py-8 text-sm text-slate-500">
                  <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                  {t('entityModal.aiGenesTab.loading')}
                </div>
              ) : catalogError ? (
                <p role="alert" className="px-2 py-4 text-sm text-red-600">
                  {catalogError}
                </p>
              ) : pickerItems.length === 0 ? (
                <p className="px-2 py-8 text-center text-sm text-slate-500">
                  {t('entityModal.aiGenesTab.addExtraEmpty')}
                </p>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {pickerItems.map((gene) => (
                    <li key={gene.id} className="flex items-center justify-between gap-2 px-2 py-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-slate-900">{gene.name}</p>
                        <p className="truncate font-mono text-xs text-slate-500">{gene.slug}</p>
                      </div>
                      <button
                        type="button"
                        disabled={attachBusy === gene.id}
                        onClick={() => void handleAttach(gene)}
                        className="shrink-0 rounded-md bg-blue-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
                      >
                        {attachBusy === gene.id
                          ? t('entityModal.aiGenesTab.loading')
                          : t('entityModal.aiGenesTab.attach')}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function buildGeneLookup(entity: EntityDetail): { readonly all: readonly AiGene[] } {
  const capabilities = Array.isArray(entity.capabilities) ? entity.capabilities : [];
  const aiGenes = Array.isArray(entity.ai_genes) ? entity.ai_genes : [];
  const capTagsByName = new Map<string, readonly string[]>();
  for (const cap of capabilities) {
    const tags = Array.isArray(cap.tags) ? cap.tags : [];
    if (tags.length > 0) capTagsByName.set(cap.name, tags);
  }
  const derived: AiGene[] = aiGenes.map((g) => ({
    slug: g.slug,
    name: g.slug,
    kind: 'tool-gene',
    tags: capTagsByName.get(g.slug) ?? [],
    source: g.source,
  }));
  return { all: derived };
}

function GeneGroup({
  heading,
  headingKey,
  genes,
  locked,
  lockedHint,
  moveLabel,
  removeLabel,
  onRemove,
}: {
  readonly heading: string;
  readonly headingKey: 'fromBaseClass' | 'extraAdded';
  readonly genes: readonly AiGene[];
  readonly locked?: boolean;
  readonly lockedHint: string;
  readonly moveLabel: string;
  readonly removeLabel: string;
  readonly onRemove: (gene: AiGene) => void;
}) {
  return (
    <section
      aria-labelledby={`genes-${headingKey}`}
      data-testid={`genes-group-${headingKey}`}
      className="overflow-hidden rounded-lg border border-slate-200 bg-white"
    >
      <header className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        <span id={`genes-${headingKey}`}>{heading}</span>
        <span className="tabular-nums">{genes.length}</span>
      </header>
      <ul className="divide-y divide-slate-100">
        {genes.map((gene) => (
          <li
            key={gene.slug}
            className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
            data-testid={`gene-row-${gene.slug}`}
          >
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-1.5 truncate font-mono text-xs text-slate-900">
                {locked ? (
                  <Lock className="size-3 shrink-0 text-slate-400" aria-hidden="true" />
                ) : null}
                {gene.slug}
              </p>
              <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                <span className="rounded-full bg-slate-100 px-2 py-0.5 font-mono">
                  {KIND_LABEL[gene.kind]}
                </span>
                {gene.tags.length > 0 ? (
                  <span className="flex flex-wrap gap-1">
                    {gene.tags.map((tag) => (
                      <span
                        key={tag}
                        className="rounded-full border border-slate-200 bg-white px-2 py-0.5 font-mono text-xs text-slate-600"
                      >
                        {tag}
                      </span>
                    ))}
                  </span>
                ) : null}
              </p>
            </div>
            {locked ? (
              <button
                type="button"
                disabled
                className={cn(
                  'inline-flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-medium text-slate-500',
                  'cursor-not-allowed',
                )}
                title={lockedHint}
              >
                {moveLabel}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onRemove(gene)}
                data-testid="gene-remove"
                className="inline-flex items-center gap-1 rounded-md border border-transparent px-2 py-1 text-xs font-medium text-red-700 transition-colors hover:border-red-200 hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
              >
                <Trash2 className="size-3.5" aria-hidden="true" />
                {removeLabel}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
