import type { TFunction } from 'i18next';
import { LoaderCircle, Pencil, Plus, Trash2, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError } from '@/lib/api';
import {
  type AiGeneCatalogItem,
  createAiGene,
  deleteAiGene,
  listAiGenes,
  updateAiGene,
} from '@/lib/api/aiGenes';
import {
  type CapabilityMarketEntry,
  createCapability,
  deleteCapability,
  listCapabilityMarket,
  updateCapability,
  type CapabilityType,
} from '@/lib/api/capabilityMarket';
import {
  type CatalogUserGene,
  createUserGene,
  deleteUserGene,
  listUserGenes,
  updateUserGene,
} from '@/lib/api/users';
import { toSlug } from '@/lib/slug';

type TFn = TFunction;

const CAPABILITY_TYPES: readonly CapabilityType[] = ['skill', 'tool', 'mcp', 'lsp', 'command'];
const SCOPES = ['org', 'namespace'] as const;

function ScopeBadge({ scope, t }: { readonly scope: string; readonly t: TFn }) {
  return (
    <span className="rounded-md bg-blue-50 px-2 py-0.5 font-mono text-xs text-blue-700">
      {t(`namespaces.scope.${scope}`, { defaultValue: scope })}
    </span>
  );
}

function ReadonlyBadge({ t }: { readonly t: TFn }) {
  return (
    <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
      {t('namespaces.readonly')}
    </span>
  );
}

type CatalogFormState = {
  readonly slug: string;
  readonly name: string;
  readonly description: string;
  readonly type: CapabilityType;
  readonly scope: (typeof SCOPES)[number];
  readonly effectScope: CatalogUserGene['effect_scope'];
};

const emptyForm = (): CatalogFormState => ({
  slug: '',
  name: '',
  description: '',
  type: 'skill',
  scope: 'org',
  effectScope: 'org',
});

function CatalogFormModal({
  title,
  mode,
  showSlug,
  showType,
  showScope,
  useEffectScope,
  initial,
  busy,
  errorMessage,
  onClose,
  onSubmit,
  t,
}: {
  readonly title: string;
  readonly mode: 'create' | 'edit';
  readonly showSlug: boolean;
  readonly showType: boolean;
  readonly showScope: boolean;
  readonly useEffectScope: boolean;
  readonly initial: CatalogFormState;
  readonly busy: boolean;
  readonly errorMessage: string | null;
  readonly onClose: () => void;
  readonly onSubmit: (values: CatalogFormState) => void;
  readonly t: TFn;
}) {
  const [values, setValues] = useState(initial);

  useEffect(() => {
    setValues(initial);
  }, [initial]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/40 p-4"
      data-testid="catalog-form-modal"
    >
      <div className="w-full max-w-lg rounded-xl border border-slate-200 bg-white p-5 shadow-lg">
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-base font-semibold text-slate-950">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label={t('namespaces.cancel')}
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </div>
        <div className="mt-4 space-y-3">
          {showSlug && mode === 'create' ? (
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">
                {t('namespaces.genesSlug')}
              </span>
              <input
                value={values.slug}
                onChange={(e) => setValues((v) => ({ ...v, slug: toSlug(e.target.value, 64) }))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              />
            </label>
          ) : null}
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">{t('namespaces.name')}</span>
            <input
              value={values.name}
              onChange={(e) => {
                const name = e.target.value;
                setValues((v) => ({
                  ...v,
                  name,
                  slug:
                    mode === 'create' && showSlug && (v.slug === '' || v.slug === toSlug(v.name))
                      ? toSlug(name, 64)
                      : v.slug,
                }));
              }}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
            />
          </label>
          {showType ? (
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">{t('namespaces.type')}</span>
              <select
                value={values.type}
                onChange={(e) =>
                  setValues((v) => ({ ...v, type: e.target.value as CapabilityType }))
                }
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              >
                {CAPABILITY_TYPES.map((capType) => (
                  <option key={capType} value={capType}>
                    {capType}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {showScope ? (
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">
                {t('namespaces.scopeLabel')}
              </span>
              <select
                value={useEffectScope ? values.effectScope : values.scope}
                onChange={(e) => {
                  const next = e.target.value;
                  if (useEffectScope) {
                    setValues((v) => ({
                      ...v,
                      effectScope: next as CatalogUserGene['effect_scope'],
                    }));
                  } else {
                    setValues((v) => ({
                      ...v,
                      scope: next as (typeof SCOPES)[number],
                    }));
                  }
                }}
                disabled={mode === 'edit'}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 disabled:bg-slate-50"
              >
                {useEffectScope ? (
                  <>
                    <option value="org">{t('namespaces.scope.org')}</option>
                    <option value="namespace">{t('namespaces.scope.namespace')}</option>
                    <option value="workspace">{t('namespaces.scope.workspace')}</option>
                    <option value="platform">{t('namespaces.scope.platform')}</option>
                  </>
                ) : (
                  SCOPES.map((s) => (
                    <option key={s} value={s}>
                      {t(`namespaces.scope.${s}`)}
                    </option>
                  ))
                )}
              </select>
            </label>
          ) : null}
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">
              {t('namespaces.genesDescription')}
            </span>
            <textarea
              value={values.description}
              onChange={(e) => setValues((v) => ({ ...v, description: e.target.value }))}
              rows={3}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
            />
          </label>
        </div>
        {errorMessage ? (
          <p role="alert" className="mt-3 text-sm text-red-600">
            {errorMessage}
          </p>
        ) : null}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            {t('namespaces.cancel')}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onSubmit(values)}
            className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
          >
            {busy ? t('common.loading') : t('namespaces.save')}
          </button>
        </div>
      </div>
    </div>
  );
}

export function DeepSeaGenesPanel({ t }: { readonly t: TFn }) {
  const [genes, setGenes] = useState<readonly AiGeneCatalogItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [modal, setModal] = useState<
    | { mode: 'create' }
    | { mode: 'edit'; gene: AiGeneCatalogItem }
    | null
  >(null);
  const [formBusy, setFormBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const page = await listAiGenes();
      setGenes(page.items);
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : String(error));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const initialForm = useMemo((): CatalogFormState => {
    if (modal?.mode === 'edit') {
      return {
        slug: modal.gene.slug,
        name: modal.gene.name,
        description: modal.gene.description ?? '',
        type: 'skill',
        scope: 'org',
        effectScope: 'org',
      };
    }
    return emptyForm();
  }, [modal]);

  const handleDelete = async (gene: AiGeneCatalogItem) => {
    if (gene.readonly === true || gene.scope === 'system') return;
    const ok = window.confirm(t('namespaces.confirmDelete', { name: gene.name }));
    if (!ok) return;
    try {
      await deleteAiGene(gene.id);
      await load();
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : String(error));
    }
  };

  const handleSubmit = async (values: CatalogFormState) => {
    setFormBusy(true);
    setFormError(null);
    try {
      if (modal?.mode === 'create') {
        await createAiGene({
          slug: values.slug,
          name: values.name.trim(),
          description: values.description.trim() || null,
          scope: values.scope,
        });
      } else if (modal?.mode === 'edit') {
        await updateAiGene(modal.gene.id, {
          name: values.name.trim(),
          description: values.description.trim() || null,
        });
      }
      setModal(null);
      await load();
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : String(error));
    } finally {
      setFormBusy(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-3 py-16 text-sm text-slate-500">
        <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
        {t('common.loading')}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-900">{t('namespaces.aiGenesTitle')}</h2>
          <p className="mt-1 text-sm text-slate-500">{t('namespaces.aiGenesDetail')}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setFormError(null);
            setModal({ mode: 'create' });
          }}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500"
        >
          <Plus className="size-4" aria-hidden="true" />
          {t('namespaces.createAiGene')}
        </button>
      </div>
      {errorMessage ? (
        <p role="alert" className="text-sm text-red-600">
          {errorMessage}
        </p>
      ) : null}
      {genes.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center text-sm text-slate-500">
          {t('namespaces.aiGenesEmpty')}
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <table className="min-w-full text-sm" data-testid="ai-genes-table">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">{t('namespaces.name')}</th>
                <th className="px-4 py-3">{t('namespaces.genesSlug')}</th>
                <th className="px-4 py-3">{t('namespaces.scopeLabel')}</th>
                <th className="px-4 py-3">{t('namespaces.readonly')}</th>
                <th className="px-4 py-3">{t('namespaces.entityActions')}</th>
              </tr>
            </thead>
            <tbody>
              {genes.map((gene) => {
                const readonly = gene.readonly === true || gene.scope === 'system';
                return (
                  <tr key={gene.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-900">{gene.name}</p>
                      {gene.description ? (
                        <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">
                          {gene.description}
                        </p>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500">{gene.slug}</td>
                    <td className="px-4 py-3">
                      <ScopeBadge scope={gene.scope ?? 'org'} t={t} />
                    </td>
                    <td className="px-4 py-3">
                      {readonly ? <ReadonlyBadge t={t} /> : <span className="text-slate-400">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          disabled={readonly}
                          onClick={() => {
                            setFormError(null);
                            setModal({ mode: 'edit', gene });
                          }}
                          className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 disabled:opacity-40"
                        >
                          <Pencil className="size-3.5" aria-hidden="true" />
                          {t('namespaces.edit')}
                        </button>
                        <button
                          type="button"
                          disabled={readonly}
                          onClick={() => void handleDelete(gene)}
                          className="inline-flex items-center gap-1 text-red-700 hover:text-red-800 disabled:opacity-40"
                        >
                          <Trash2 className="size-3.5" aria-hidden="true" />
                          {t('namespaces.delete')}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {modal !== null ? (
        <CatalogFormModal
          title={modal.mode === 'create' ? t('namespaces.createAiGene') : t('namespaces.edit')}
          mode={modal.mode}
          showSlug
          showType={false}
          showScope={modal.mode === 'create'}
          useEffectScope={false}
          initial={initialForm}
          busy={formBusy}
          errorMessage={formError}
          onClose={() => setModal(null)}
          onSubmit={(values) => void handleSubmit(values)}
          t={t}
        />
      ) : null}
    </div>
  );
}

export function HumanGenesPanel({ t }: { readonly t: TFn }) {
  const [genes, setGenes] = useState<readonly CatalogUserGene[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [modal, setModal] = useState<
    | { mode: 'create' }
    | { mode: 'edit'; gene: CatalogUserGene }
    | null
  >(null);
  const [formBusy, setFormBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const genePage = await listUserGenes();
      setGenes(genePage.items);
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : String(error));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const initialForm = useMemo((): CatalogFormState => {
    if (modal?.mode === 'edit') {
      return {
        slug: modal.gene.slug,
        name: modal.gene.name,
        description: modal.gene.description ?? '',
        type: 'skill',
        scope: 'org',
        effectScope: modal.gene.effect_scope,
      };
    }
    return emptyForm();
  }, [modal]);

  const isReadonlyGene = (gene: CatalogUserGene) => gene.kind === 'builtin';

  const handleDelete = async (gene: CatalogUserGene) => {
    if (isReadonlyGene(gene)) return;
    const ok = window.confirm(t('namespaces.confirmDelete', { name: gene.name }));
    if (!ok) return;
    try {
      await deleteUserGene(gene.id);
      await load();
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : String(error));
    }
  };

  const handleSubmit = async (values: CatalogFormState) => {
    setFormBusy(true);
    setFormError(null);
    try {
      if (modal?.mode === 'create') {
        await createUserGene({
          slug: values.slug,
          name: values.name.trim(),
          effect_scope: values.effectScope,
          description: values.description.trim() || null,
        });
      } else if (modal?.mode === 'edit') {
        await updateUserGene(modal.gene.id, {
          name: values.name.trim(),
          effect_scope: values.effectScope,
          description: values.description.trim() || null,
        });
      }
      setModal(null);
      await load();
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : String(error));
    } finally {
      setFormBusy(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-3 py-16 text-sm text-slate-500">
        <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
        {t('common.loading')}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-900">{t('namespaces.genesTitle')}</h2>
          <p className="mt-1 text-sm text-slate-500">{t('namespaces.genesDetail')}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setFormError(null);
            setModal({ mode: 'create' });
          }}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500"
        >
          <Plus className="size-4" aria-hidden="true" />
          {t('namespaces.createUserGene')}
        </button>
      </div>
      {errorMessage ? (
        <p role="alert" className="text-sm text-red-600">
          {errorMessage}
        </p>
      ) : null}
      {genes.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center text-sm text-slate-500">
          {t('namespaces.genesEmpty')}
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <table className="min-w-full text-sm" data-testid="user-genes-table">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">{t('namespaces.name')}</th>
                <th className="px-4 py-3">{t('namespaces.genesSlug')}</th>
                <th className="px-4 py-3">{t('namespaces.scopeLabel')}</th>
                <th className="px-4 py-3">{t('namespaces.readonly')}</th>
                <th className="px-4 py-3">{t('namespaces.entityActions')}</th>
              </tr>
            </thead>
            <tbody>
              {genes.map((gene) => {
                const readonly = isReadonlyGene(gene);
                return (
                  <tr key={gene.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3 font-medium text-slate-900">{gene.name}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-700">{gene.slug}</td>
                    <td className="px-4 py-3">
                      <ScopeBadge scope={gene.effect_scope} t={t} />
                    </td>
                    <td className="px-4 py-3">
                      {readonly ? <ReadonlyBadge t={t} /> : <span className="text-slate-400">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          disabled={readonly}
                          onClick={() => {
                            setFormError(null);
                            setModal({ mode: 'edit', gene });
                          }}
                          className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 disabled:opacity-40"
                        >
                          <Pencil className="size-3.5" aria-hidden="true" />
                          {t('namespaces.edit')}
                        </button>
                        <button
                          type="button"
                          disabled={readonly}
                          onClick={() => void handleDelete(gene)}
                          className="inline-flex items-center gap-1 text-red-700 hover:text-red-800 disabled:opacity-40"
                        >
                          <Trash2 className="size-3.5" aria-hidden="true" />
                          {t('namespaces.delete')}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {modal !== null ? (
        <CatalogFormModal
          title={modal.mode === 'create' ? t('namespaces.createUserGene') : t('namespaces.edit')}
          mode={modal.mode}
          showSlug={modal.mode === 'create'}
          showType={false}
          showScope
          useEffectScope
          initial={initialForm}
          busy={formBusy}
          errorMessage={formError}
          onClose={() => setModal(null)}
          onSubmit={(values) => void handleSubmit(values)}
          t={t}
        />
      ) : null}
    </div>
  );
}

export function CapabilityMarketTab({ t }: { readonly t: TFn }) {
  const [entries, setEntries] = useState<readonly CapabilityMarketEntry[]>([]);
  const [hideSystem, setHideSystem] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [modal, setModal] = useState<
    | { mode: 'create' }
    | { mode: 'edit'; entry: CapabilityMarketEntry }
    | null
  >(null);
  const [formBusy, setFormBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const page = await listCapabilityMarket();
      setEntries(page.items);
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : String(error));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(
    () => (hideSystem ? entries.filter((e) => e.scope !== 'system') : entries),
    [entries, hideSystem],
  );

  const initialForm = useMemo((): CatalogFormState => {
    if (modal?.mode === 'edit') {
      return {
        slug: '',
        name: modal.entry.name,
        description: modal.entry.description ?? '',
        type: (modal.entry.type as CapabilityType) ?? 'skill',
        scope: modal.entry.scope === 'namespace' ? 'namespace' : 'org',
        effectScope: 'org',
      };
    }
    return emptyForm();
  }, [modal]);

  const isReadonlyEntry = (entry: CapabilityMarketEntry) =>
    entry.readonly === true || entry.scope === 'system';

  const handleDelete = async (entry: CapabilityMarketEntry) => {
    if (isReadonlyEntry(entry)) return;
    const ok = window.confirm(t('namespaces.confirmDelete', { name: entry.name }));
    if (!ok) return;
    try {
      await deleteCapability(entry.id);
      await load();
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : String(error));
    }
  };

  const handleSubmit = async (values: CatalogFormState) => {
    setFormBusy(true);
    setFormError(null);
    try {
      if (modal?.mode === 'create') {
        await createCapability({
          name: values.name.trim(),
          type: values.type,
          description: values.description.trim() || null,
          scope: values.scope,
        });
      } else if (modal?.mode === 'edit') {
        await updateCapability(modal.entry.id, {
          name: values.name.trim(),
          type: values.type,
          description: values.description.trim() || null,
        });
      }
      setModal(null);
      await load();
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : String(error));
    } finally {
      setFormBusy(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-3 py-16 text-sm text-slate-500">
        <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
        {t('common.loading')}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-900">
            {t('namespaces.capabilityMarketTitle')}
          </h2>
          <p className="mt-1 text-sm text-slate-500">{t('namespaces.capabilityMarketDetail')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-600">
            <input
              type="checkbox"
              checked={hideSystem}
              onChange={(e) => setHideSystem(e.target.checked)}
              className="rounded border-slate-300"
            />
            {t('namespaces.hideSystem')}
          </label>
          <button
            type="button"
            onClick={() => {
              setFormError(null);
              setModal({ mode: 'create' });
            }}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500"
          >
            <Plus className="size-4" aria-hidden="true" />
            {t('namespaces.createCapability')}
          </button>
        </div>
      </div>
      {errorMessage ? (
        <p role="alert" className="text-sm text-red-600">
          {errorMessage}
        </p>
      ) : null}
      {visible.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center text-sm text-slate-500">
          {t('namespaces.capabilityMarketEmpty')}
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <table className="min-w-full text-sm" data-testid="capability-market-table">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">{t('namespaces.name')}</th>
                <th className="px-4 py-3">{t('namespaces.type')}</th>
                <th className="px-4 py-3">{t('namespaces.scopeLabel')}</th>
                <th className="px-4 py-3">{t('namespaces.readonly')}</th>
                <th className="px-4 py-3">{t('namespaces.entityActions')}</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((entry) => {
                const readonly = isReadonlyEntry(entry);
                return (
                  <tr key={entry.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-900">{entry.name}</p>
                      {entry.description ? (
                        <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">
                          {entry.description}
                        </p>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-600">{entry.type}</td>
                    <td className="px-4 py-3">
                      <ScopeBadge scope={entry.scope} t={t} />
                    </td>
                    <td className="px-4 py-3">
                      {readonly ? <ReadonlyBadge t={t} /> : <span className="text-slate-400">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          disabled={readonly}
                          onClick={() => {
                            setFormError(null);
                            setModal({ mode: 'edit', entry });
                          }}
                          className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 disabled:opacity-40"
                        >
                          <Pencil className="size-3.5" aria-hidden="true" />
                          {t('namespaces.edit')}
                        </button>
                        <button
                          type="button"
                          disabled={readonly}
                          onClick={() => void handleDelete(entry)}
                          className="inline-flex items-center gap-1 text-red-700 hover:text-red-800 disabled:opacity-40"
                        >
                          <Trash2 className="size-3.5" aria-hidden="true" />
                          {t('namespaces.delete')}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {modal !== null ? (
        <CatalogFormModal
          title={
            modal.mode === 'create' ? t('namespaces.createCapability') : t('namespaces.edit')
          }
          mode={modal.mode}
          showSlug={false}
          showType
          showScope={modal.mode === 'create'}
          useEffectScope={false}
          initial={initialForm}
          busy={formBusy}
          errorMessage={formError}
          onClose={() => setModal(null)}
          onSubmit={(values) => void handleSubmit(values)}
          t={t}
        />
      ) : null}
    </div>
  );
}
