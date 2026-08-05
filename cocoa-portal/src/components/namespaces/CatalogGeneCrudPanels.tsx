import type { TFunction } from 'i18next';
import { LoaderCircle, Pencil, Plus, Trash2, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError } from '@/lib/api';
import {
  type AiGeneCatalogItem,
  type CapabilityInline,
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
  readonly tagsText: string;
  readonly jsonText: string;
  readonly checkedCapabilities: readonly string[];
  readonly removedCapabilities: readonly string[];
};

const emptyForm = (): CatalogFormState => ({
  slug: '',
  name: '',
  description: '',
  type: 'skill',
  scope: 'org',
  effectScope: 'org',
  tagsText: '',
  jsonText: '',
  checkedCapabilities: [],
  removedCapabilities: [],
});

type CatalogJsonField = 'manifest' | 'configTemplate';

type JsonParseResult =
  | { readonly ok: true; readonly value: Record<string, unknown> | null }
  | { readonly ok: false };

/** Normalize a comma-separated tags input into kebab-case, deduped tags. */
export function normalizeTagsInput(text: string): readonly string[] | null {
  const tags = text
    .split(/[,,]/)
    .map((raw) =>
      raw
        .trim()
        .toLowerCase()
        .replace(/\s+/g, '-')
        .replace(/[^a-z0-9-]/g, '')
        .replace(/-{2,}/g, '-')
        .replace(/^-+|-+$/g, ''),
    )
    .filter((tag) => tag.length > 0);
  if (tags.length === 0) return null;
  return [...new Set(tags)];
}

/** Parse a JSON-object textarea value. Empty input maps to null; non-object or invalid JSON fails. */
export function parseJsonObjectInput(text: string): JsonParseResult {
  const trimmed = text.trim();
  if (trimmed === '') return { ok: true, value: null };
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return { ok: true, value: parsed as Record<string, unknown> };
    }
    return { ok: false };
  } catch {
    return { ok: false };
  }
}

/** Read the inline `capabilities` array of a manifest object, deduped by name. */
export function manifestCapabilities(
  manifest: Record<string, unknown> | null,
): readonly CapabilityInline[] {
  if (manifest === null) return [];
  const raw: unknown = manifest.capabilities;
  if (!Array.isArray(raw)) return [];
  const out: CapabilityInline[] = [];
  const seen = new Set<string>();
  for (const item of raw as unknown[]) {
    if (item === null || typeof item !== 'object' || Array.isArray(item)) continue;
    const record = item as Record<string, unknown>;
    const name = record.name;
    if (typeof name !== 'string' || name.length === 0 || seen.has(name)) continue;
    seen.add(name);
    const type = record.type;
    const description = record.description;
    out.push({
      name,
      type: typeof type === 'string' ? type : '',
      description: typeof description === 'string' ? description : null,
    });
  }
  return out;
}

/** Merge manifest-inline capabilities with the checkbox layer (checked minus removed) into the final submit list, deduped by name. */
export function resolveGeneCapabilities(
  manifest: Record<string, unknown> | null,
  checkedNames: readonly string[],
  removedNames: readonly string[],
  options: readonly CapabilityInline[],
): readonly CapabilityInline[] {
  const byName = new Map<string, CapabilityInline>();
  for (const cap of manifestCapabilities(manifest)) {
    if (!removedNames.includes(cap.name)) byName.set(cap.name, cap);
  }
  for (const name of checkedNames) {
    if (byName.has(name)) continue;
    const option = options.find((o) => o.name === name);
    if (option !== undefined) {
      byName.set(name, { name: option.name, type: option.type, description: option.description });
    }
  }
  return [...byName.values()];
}

/** Drop the inline `capabilities` key so the dedicated payload field stays the single write source; empty objects collapse to null. */
function stripManifestCapabilities(
  manifest: Record<string, unknown> | null,
): Record<string, unknown> | null {
  if (manifest === null) return null;
  if (!('capabilities' in manifest)) return manifest;
  const rest = Object.fromEntries(
    Object.entries(manifest).filter(([key]) => key !== 'capabilities'),
  );
  return Object.keys(rest).length > 0 ? rest : null;
}

function CatalogFormModal({
  title,
  mode,
  showSlug,
  showType,
  showScope,
  useEffectScope,
  showTags,
  jsonField,
  showCapabilities,
  capabilityOptions,
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
  readonly showTags: boolean;
  readonly jsonField: CatalogJsonField | null;
  readonly showCapabilities: boolean;
  readonly capabilityOptions: readonly CapabilityInline[];
  readonly initial: CatalogFormState;
  readonly busy: boolean;
  readonly errorMessage: string | null;
  readonly onClose: () => void;
  readonly onSubmit: (values: CatalogFormState) => void;
  readonly t: TFn;
}) {
  const [values, setValues] = useState(initial);
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => {
    setValues(initial);
    setValidationError(null);
  }, [initial]);

  const jsonLabelKey =
    jsonField === 'manifest'
      ? 'namespaces.genesManifestLabel'
      : 'namespaces.capabilityConfigTemplateLabel';
  const jsonPlaceholderKey =
    jsonField === 'manifest'
      ? 'namespaces.genesManifestPlaceholder'
      : 'namespaces.capabilityConfigTemplatePlaceholder';

  const dedupedOptions = useMemo(() => {
    const seen = new Set<string>();
    return capabilityOptions.filter((option) => {
      if (option.name.length === 0 || seen.has(option.name)) return false;
      seen.add(option.name);
      return true;
    });
  }, [capabilityOptions]);

  const parsedManifest = useMemo(() => {
    if (jsonField !== 'manifest') return null;
    const parsed = parseJsonObjectInput(values.jsonText);
    return parsed.ok ? parsed.value : null;
  }, [jsonField, values.jsonText]);

  const effectiveCapabilities = useMemo(
    () =>
      resolveGeneCapabilities(
        parsedManifest,
        values.checkedCapabilities,
        values.removedCapabilities,
        dedupedOptions,
      ),
    [parsedManifest, values.checkedCapabilities, values.removedCapabilities, dedupedOptions],
  );

  const toggleCapability = (name: string) => {
    const inManifest =
      parsedManifest !== null && manifestCapabilities(parsedManifest).some((c) => c.name === name);
    const isChecked = effectiveCapabilities.some((c) => c.name === name);
    setValues((v) => {
      if (isChecked) {
        return {
          ...v,
          checkedCapabilities: v.checkedCapabilities.filter((n) => n !== name),
          removedCapabilities:
            inManifest && !v.removedCapabilities.includes(name)
              ? [...v.removedCapabilities, name]
              : v.removedCapabilities,
        };
      }
      return {
        ...v,
        checkedCapabilities: v.checkedCapabilities.includes(name)
          ? v.checkedCapabilities
          : [...v.checkedCapabilities, name],
        removedCapabilities: v.removedCapabilities.filter((n) => n !== name),
      };
    });
  };

  const handleSubmit = () => {
    if (jsonField !== null) {
      const parsed = parseJsonObjectInput(values.jsonText);
      if (!parsed.ok) {
        setValidationError(t('namespaces.invalidJsonObject'));
        return;
      }
    }
    setValidationError(null);
    onSubmit(values);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/40 p-4"
      data-testid="catalog-form-modal"
    >
      <div className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-xl border border-slate-200 bg-white p-5 shadow-lg">
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
          {showTags ? (
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">
                {t('namespaces.genesTagsLabel')}
              </span>
              <input
                value={values.tagsText}
                onChange={(e) => setValues((v) => ({ ...v, tagsText: e.target.value }))}
                placeholder={t('namespaces.genesTagsPlaceholder')}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              />
            </label>
          ) : null}
          {jsonField !== null ? (
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">{t(jsonLabelKey)}</span>
              <textarea
                value={values.jsonText}
                onChange={(e) => setValues((v) => ({ ...v, jsonText: e.target.value }))}
                placeholder={t(jsonPlaceholderKey)}
                rows={4}
                spellCheck={false}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-xs outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              />
            </label>
          ) : null}
          {showCapabilities ? (
            <fieldset className="block text-sm" data-testid="gene-capabilities-picker">
              <legend className="mb-1 font-medium text-slate-700">
                {t('namespaces.geneCapabilitiesLabel')}
              </legend>
              <p className="mb-2 text-xs text-slate-500">{t('namespaces.geneCapabilitiesHint')}</p>
              {dedupedOptions.length === 0 ? (
                <p className="rounded-lg border border-dashed border-slate-200 px-3 py-2 text-xs text-slate-500">
                  {t('namespaces.geneCapabilitiesEmpty')}
                </p>
              ) : (
                <ul className="max-h-44 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2">
                  {dedupedOptions.map((option) => {
                    const checked = effectiveCapabilities.some((c) => c.name === option.name);
                    return (
                      <li key={option.name}>
                        <label className="flex items-start gap-2 rounded-md px-2 py-1.5 hover:bg-slate-50">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleCapability(option.name)}
                            className="mt-0.5 rounded border-slate-300"
                          />
                          <span className="min-w-0">
                            <span className="block truncate font-medium text-slate-800">
                              {option.name}
                            </span>
                            <span className="block text-xs text-slate-500">
                              <span className="font-mono">{option.type}</span>
                              {option.description ? ` — ${option.description}` : ''}
                            </span>
                          </span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}
              <div
                className="mt-2 rounded-lg bg-slate-50 px-3 py-2"
                data-testid="gene-capabilities-summary"
              >
                {effectiveCapabilities.length === 0 ? (
                  <p className="text-xs text-slate-500">{t('namespaces.geneCapabilitiesNone')}</p>
                ) : (
                  <>
                    <p className="text-xs font-medium text-slate-600">
                      {t('namespaces.geneCapabilitiesSummary', {
                        count: effectiveCapabilities.length,
                      })}
                    </p>
                    <ul className="mt-1 flex flex-wrap gap-1">
                      {effectiveCapabilities.map((cap) => (
                        <li
                          key={cap.name}
                          className="inline-flex items-center gap-1 rounded-md bg-white px-2 py-0.5 text-xs text-slate-700 ring-1 ring-slate-200"
                        >
                          {cap.name}
                          <span className="font-mono text-slate-400">{cap.type}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            </fieldset>
          ) : null}
        </div>
        {validationError ? (
          <p role="alert" className="mt-3 text-sm text-red-600">
            {validationError}
          </p>
        ) : null}
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
            onClick={handleSubmit}
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
  const [capabilityOptions, setCapabilityOptions] = useState<readonly CapabilityInline[]>([]);
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

  useEffect(() => {
    let cancelled = false;
    listCapabilityMarket()
      .then((page) => {
        if (cancelled) return;
        setCapabilityOptions(
          page.items.map((entry) => ({
            name: entry.name,
            type: entry.type,
            description: entry.description,
          })),
        );
      })
      .catch(() => {
        if (!cancelled) setCapabilityOptions([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const initialForm = useMemo((): CatalogFormState => {
    if (modal?.mode === 'edit') {
      const echoed = modal.gene.capabilities ?? manifestCapabilities(modal.gene.manifest ?? null);
      return {
        slug: modal.gene.slug,
        name: modal.gene.name,
        description: modal.gene.description ?? '',
        type: 'skill',
        scope: 'org',
        effectScope: 'org',
        tagsText: (modal.gene.tags ?? []).join(', '),
        jsonText:
          modal.gene.manifest != null ? JSON.stringify(modal.gene.manifest, null, 2) : '',
        checkedCapabilities: echoed.map((cap) => cap.name),
        removedCapabilities: [],
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
      const tags = normalizeTagsInput(values.tagsText);
      const parsed = parseJsonObjectInput(values.jsonText);
      if (!parsed.ok) {
        setFormError(t('namespaces.invalidJsonObject'));
        return;
      }
      const capabilities = resolveGeneCapabilities(
        parsed.value,
        values.checkedCapabilities,
        values.removedCapabilities,
        capabilityOptions,
      );
      const manifest = stripManifestCapabilities(parsed.value);
      if (modal?.mode === 'create') {
        await createAiGene({
          slug: values.slug,
          name: values.name.trim(),
          description: values.description.trim() || null,
          tags,
          manifest,
          capabilities,
          scope: values.scope,
        });
      } else if (modal?.mode === 'edit') {
        await updateAiGene(modal.gene.id, {
          name: values.name.trim(),
          description: values.description.trim() || null,
          tags,
          manifest,
          capabilities,
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
          showTags
          jsonField="manifest"
          showCapabilities
          capabilityOptions={capabilityOptions}
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
        tagsText: '',
        jsonText: '',
        checkedCapabilities: [],
        removedCapabilities: [],
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
          showTags={false}
          jsonField={null}
          showCapabilities={false}
          capabilityOptions={[]}
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
        tagsText: (modal.entry.tags ?? []).join(', '),
        jsonText:
          modal.entry.config_template != null
            ? JSON.stringify(modal.entry.config_template, null, 2)
            : '',
        checkedCapabilities: [],
        removedCapabilities: [],
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
      const tags = normalizeTagsInput(values.tagsText);
      const parsed = parseJsonObjectInput(values.jsonText);
      if (!parsed.ok) {
        setFormError(t('namespaces.invalidJsonObject'));
        return;
      }
      const configTemplate = parsed.value;
      if (modal?.mode === 'create') {
        await createCapability({
          name: values.name.trim(),
          type: values.type,
          description: values.description.trim() || null,
          config_template: configTemplate,
          tags,
          scope: values.scope,
        });
      } else if (modal?.mode === 'edit') {
        await updateCapability(modal.entry.id, {
          name: values.name.trim(),
          type: values.type,
          description: values.description.trim() || null,
          config_template: configTemplate,
          tags,
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
          showTags
          jsonField="configTemplate"
          showCapabilities={false}
          capabilityOptions={[]}
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
