import {
  AlertCircle,
  Check,
  CircleAlert,
  LoaderCircle,
  Plus,
  Settings,
  TestTube2,
  Trash2,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '@/lib/api';
import { fetchBaseClassesPage } from '@/lib/api/baseClasses';
import {
  type CatalogModel,
  createOrganizationProvider,
  deleteOrganizationProvider,
  fetchCerebellumDefaults,
  fetchDefaultOrganization,
  fetchModelCatalog,
  fetchProviderCatalog,
  fetchSystemHub,
  listOrganizationProviders,
  type Organization,
  type OrganizationProvider,
  type ProviderCatalogEntry,
  type SetDefaultTarget,
  setProviderDefault,
  testOrganizationProvider,
  updateCerebellumDefaults,
  updateOrganizationProvider,
  updateSystemHub,
} from '@/lib/api/providers';
import type { BaseClass } from '@/lib/types';
import { cn } from '@/lib/utils';
import { useSessionStore } from '@/stores/session';

export default function OrganizationPage() {
  const { t } = useTranslation();
  const isSuperAdmin = useSessionStore((state) => state.user?.is_super_admin ?? false);

  const [org, setOrg] = useState<Organization | null>(null);
  const [providers, setProviders] = useState<readonly OrganizationProvider[]>([]);
  const [baseClasses, setBaseClasses] = useState<readonly BaseClass[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [systemHubProviderId, setSystemHubProviderId] = useState<string>('');
  const [systemHubModel, setSystemHubModel] = useState<string>('');
  const [cerebellumProviderId, setCerebellumProviderId] = useState<string>('');
  const [cerebellumModel, setCerebellumModel] = useState<string>('');
  const [hubSaving, setHubSaving] = useState(false);
  const [cerebellumSaving, setCerebellumSaving] = useState(false);
  const [hubError, setHubError] = useState<string | null>(null);
  const [cerebellumError, setCerebellumError] = useState<string | null>(null);

  const [catalogOpen, setCatalogOpen] = useState(false);
  const [customOpen, setCustomOpen] = useState(false);
  const [setDefaultOpen, setSetDefaultOpen] = useState<string | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const enabledProviders = useMemo(() => providers.filter((p) => p.enabled), [providers]);

  const loadAll = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const [orgData, providerRows, bcPage, hub, cerebellum] = await Promise.all([
        fetchDefaultOrganization(),
        listOrganizationProviders(),
        fetchBaseClassesPage({ limit: 100, offset: 0 }),
        fetchSystemHub(),
        fetchCerebellumDefaults(),
      ]);
      setOrg(orgData);
      setProviders(providerRows);
      setBaseClasses(
        bcPage.items.filter(
          (bc) =>
            bc.slug !== 'cerebellum-baseclass' &&
            !(bc.tags ?? []).some((tag) => tag === 'internal' || tag === 'system'),
        ),
      );
      setSystemHubProviderId(hub.provider_id ?? '');
      setSystemHubModel(hub.model ?? '');
      setCerebellumProviderId(cerebellum.provider_id ?? '');
      setCerebellumModel(cerebellum.model ?? '');
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setErrorMessage(t('organization.notAvailable'));
        return;
      }
      setErrorMessage(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  async function handleTest(providerId: string) {
    if (!isSuperAdmin) return;
    setTestingId(providerId);
    setActionError(null);
    try {
      await testOrganizationProvider(providerId);
      await loadAll();
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setTestingId(null);
    }
  }

  async function handleToggleEnabled(provider: OrganizationProvider) {
    if (!isSuperAdmin) return;
    setActionError(null);
    try {
      await updateOrganizationProvider(provider.id, { enabled: !provider.enabled });
      await loadAll();
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : t('errors.network'));
    }
  }

  async function handleDelete(providerId: string) {
    if (!isSuperAdmin) return;
    setActionError(null);
    try {
      await deleteOrganizationProvider(providerId);
      await loadAll();
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : t('errors.network'));
    }
  }

  async function saveSystemHub() {
    if (!isSuperAdmin) return;
    setHubSaving(true);
    setHubError(null);
    try {
      await updateSystemHub({
        provider_id: systemHubProviderId || null,
        model: systemHubModel || null,
      });
      await loadAll();
    } catch (error) {
      setHubError(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setHubSaving(false);
    }
  }

  async function saveCerebellumDefaults() {
    if (!isSuperAdmin) return;
    setCerebellumSaving(true);
    setCerebellumError(null);
    try {
      await updateCerebellumDefaults({
        provider_id: cerebellumProviderId || null,
        model: cerebellumModel || null,
      });
      await loadAll();
    } catch (error) {
      setCerebellumError(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setCerebellumSaving(false);
    }
  }

  return (
    <section className="mx-auto w-full max-w-5xl p-6 lg:p-8">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Settings className="size-6 text-slate-700" aria-hidden="true" />
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">{t('organization.title')}</h1>
            {org !== null ? (
              <p className="mt-1 text-sm text-slate-500">
                {org.name} <span className="font-mono text-xs">({org.slug})</span>
              </p>
            ) : null}
          </div>
        </div>
        {!isSuperAdmin ? (
          <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
            {t('organization.readOnlyHint')}
          </p>
        ) : null}
      </header>

      {isLoading ? (
        <div className="flex items-center gap-3 text-sm text-slate-500">
          <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
          {t('common.loading')}
        </div>
      ) : null}

      {errorMessage !== null ? (
        <div
          role="alert"
          className="mb-6 flex gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
        >
          <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
          <p>{errorMessage}</p>
        </div>
      ) : null}

      {actionError !== null ? (
        <div
          role="alert"
          className="mb-6 flex gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
          <p>{actionError}</p>
        </div>
      ) : null}

      {!isLoading && org !== null ? (
        <div className="space-y-8">
          <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
            <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
              <div>
                <h2 className="text-base font-semibold text-slate-900">
                  {t('organization.providers.title')}
                </h2>
                <p className="mt-1 text-xs text-slate-500">
                  {t('organization.providers.subtitle')}
                </p>
              </div>
              {isSuperAdmin ? (
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setCatalogOpen(true)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <Plus className="size-3.5" aria-hidden="true" />
                    {t('organization.providers.enableCatalog')}
                  </button>
                  <button
                    type="button"
                    onClick={() => setCustomOpen(true)}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500"
                  >
                    <Plus className="size-3.5" aria-hidden="true" />
                    {t('organization.providers.addCustom')}
                  </button>
                </div>
              ) : null}
            </header>

            {providers.length === 0 ? (
              <p className="px-5 py-8 text-sm text-slate-500">
                {t('organization.providers.empty')}
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm" data-testid="organization-providers-table">
                  <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-3">{t('organization.providers.columns.name')}</th>
                      <th className="px-4 py-3">{t('organization.providers.columns.origin')}</th>
                      <th className="px-4 py-3">{t('organization.providers.columns.model')}</th>
                      <th className="px-4 py-3">{t('organization.providers.columns.status')}</th>
                      <th className="px-4 py-3">{t('organization.providers.columns.test')}</th>
                      {isSuperAdmin ? (
                        <th className="px-4 py-3">{t('organization.providers.columns.actions')}</th>
                      ) : null}
                    </tr>
                  </thead>
                  <tbody>
                    {providers.map((provider) => (
                      <tr key={provider.id} className="border-b border-slate-100 last:border-0">
                        <td className="px-4 py-3">
                          <p className="font-medium text-slate-900">{provider.name}</p>
                          <p className="font-mono text-xs text-slate-500">{provider.slug}</p>
                        </td>
                        <td className="px-4 py-3 capitalize text-slate-600">{provider.origin}</td>
                        <td className="px-4 py-3 font-mono text-xs text-slate-700">
                          {provider.default_model}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={cn(
                              'inline-flex rounded-full px-2 py-0.5 text-xs font-medium',
                              provider.enabled
                                ? 'bg-emerald-50 text-emerald-700'
                                : 'bg-slate-100 text-slate-600',
                            )}
                          >
                            {provider.enabled
                              ? t('organization.providers.enabled')
                              : t('organization.providers.disabled')}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          {provider.last_test_status === 'ok' ? (
                            <span className="inline-flex items-center gap-1 text-xs text-emerald-700">
                              <Check className="size-3.5" aria-hidden="true" />
                              {t('organization.providers.testOk')}
                            </span>
                          ) : provider.last_test_status === 'error' ? (
                            <span className="inline-flex items-center gap-1 text-xs text-red-700">
                              <CircleAlert className="size-3.5" aria-hidden="true" />
                              {t('organization.providers.testFailed')}
                            </span>
                          ) : (
                            <span className="text-xs text-slate-400">
                              {t('organization.providers.notTested')}
                            </span>
                          )}
                        </td>
                        {isSuperAdmin ? (
                          <td className="px-4 py-3">
                            <div className="flex flex-wrap gap-1.5">
                              <button
                                type="button"
                                onClick={() => void handleTest(provider.id)}
                                disabled={testingId === provider.id}
                                data-testid={`provider-test-${provider.id}`}
                                className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                              >
                                {testingId === provider.id ? (
                                  <LoaderCircle
                                    className="size-3 animate-spin"
                                    aria-hidden="true"
                                  />
                                ) : (
                                  <TestTube2 className="size-3" aria-hidden="true" />
                                )}
                                {t('organization.providers.test')}
                              </button>
                              <button
                                type="button"
                                onClick={() => setSetDefaultOpen(provider.id)}
                                className="rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                              >
                                {t('organization.providers.setDefault')}
                              </button>
                              <button
                                type="button"
                                onClick={() => void handleToggleEnabled(provider)}
                                className="rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                              >
                                {provider.enabled
                                  ? t('organization.providers.disable')
                                  : t('organization.providers.enable')}
                              </button>
                              <button
                                type="button"
                                onClick={() => void handleDelete(provider.id)}
                                className="inline-flex items-center gap-1 rounded-md border border-red-200 px-2 py-1 text-xs text-red-700 hover:bg-red-50"
                              >
                                <Trash2 className="size-3" aria-hidden="true" />
                                {t('organization.providers.delete')}
                              </button>
                            </div>
                          </td>
                        ) : null}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <div className="grid gap-6 lg:grid-cols-2">
            <HubSettingsPanel
              title={t('organization.systemHub.title')}
              subtitle={t('organization.systemHub.subtitle')}
              providerId={systemHubProviderId}
              model={systemHubModel}
              providers={enabledProviders}
              canEdit={isSuperAdmin}
              saving={hubSaving}
              error={hubError}
              onProviderChange={setSystemHubProviderId}
              onModelChange={setSystemHubModel}
              onSave={() => void saveSystemHub()}
            />
            <HubSettingsPanel
              title={t('organization.cerebellum.title')}
              subtitle={t('organization.cerebellum.subtitle')}
              providerId={cerebellumProviderId}
              model={cerebellumModel}
              providers={enabledProviders}
              canEdit={isSuperAdmin}
              saving={cerebellumSaving}
              error={cerebellumError}
              onProviderChange={setCerebellumProviderId}
              onModelChange={setCerebellumModel}
              onSave={() => void saveCerebellumDefaults()}
            />
          </div>
        </div>
      ) : null}

      {catalogOpen && isSuperAdmin ? (
        <EnableCatalogModal
          existing={providers}
          onClose={() => setCatalogOpen(false)}
          onCreated={() => {
            setCatalogOpen(false);
            void loadAll();
          }}
        />
      ) : null}

      {customOpen && isSuperAdmin ? (
        <CustomProviderModal
          onClose={() => setCustomOpen(false)}
          onCreated={() => {
            setCustomOpen(false);
            void loadAll();
          }}
        />
      ) : null}

      {setDefaultOpen !== null && isSuperAdmin ? (
        <SetDefaultModal
          provider={providers.find((p) => p.id === setDefaultOpen) ?? null}
          baseClasses={baseClasses}
          onClose={() => setSetDefaultOpen(null)}
          onSaved={() => {
            setSetDefaultOpen(null);
            void loadAll();
          }}
        />
      ) : null}
    </section>
  );
}

function HubSettingsPanel({
  title,
  subtitle,
  providerId,
  model,
  providers,
  canEdit,
  saving,
  error,
  onProviderChange,
  onModelChange,
  onSave,
}: {
  readonly title: string;
  readonly subtitle: string;
  readonly providerId: string;
  readonly model: string;
  readonly providers: readonly OrganizationProvider[];
  readonly canEdit: boolean;
  readonly saving: boolean;
  readonly error: string | null;
  readonly onProviderChange: (value: string) => void;
  readonly onModelChange: (value: string) => void;
  readonly onSave: () => void;
}) {
  const { t } = useTranslation();
  const [models, setModels] = useState<readonly CatalogModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);

  useEffect(() => {
    if (providerId.length === 0) {
      setModels([]);
      return;
    }
    let active = true;
    setModelsLoading(true);
    fetchModelCatalog(providerId)
      .then((page) => {
        if (active) setModels(page.items);
      })
      .catch(() => {
        if (active) setModels([]);
      })
      .finally(() => {
        if (active) setModelsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [providerId]);

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-base font-semibold text-slate-900">{title}</h2>
      <p className="mt-1 text-xs text-slate-500">{subtitle}</p>
      <div className="mt-4 space-y-3">
        <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
          {t('organization.fields.provider')}
          <select
            value={providerId}
            disabled={!canEdit}
            onChange={(e) => onProviderChange(e.target.value)}
            className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm disabled:bg-slate-50"
          >
            <option value="">{t('organization.fields.none')}</option>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <div className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
          {t('organization.fields.model')}
          {models.length > 0 ? (
            <select
              aria-label={t('organization.fields.model')}
              value={model}
              disabled={!canEdit || providerId.length === 0}
              onChange={(e) => onModelChange(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm disabled:bg-slate-50"
            >
              <option value="">{t('organization.fields.selectModel')}</option>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          ) : (
            <input
              aria-label={t('organization.fields.model')}
              type="text"
              value={model}
              disabled={!canEdit}
              onChange={(e) => onModelChange(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm disabled:bg-slate-50"
            />
          )}
        </div>
        {modelsLoading ? (
          <p className="flex items-center gap-2 text-xs text-slate-500">
            <LoaderCircle className="size-3 animate-spin" aria-hidden="true" />
            {t('organization.loadingModels')}
          </p>
        ) : null}
        {error !== null ? (
          <p role="alert" className="text-xs text-red-700">
            {error}
          </p>
        ) : null}
        {canEdit ? (
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
          >
            {saving ? <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" /> : null}
            {t('organization.save')}
          </button>
        ) : null}
      </div>
    </section>
  );
}

function EnableCatalogModal({
  existing,
  onClose,
  onCreated,
}: {
  readonly existing: readonly OrganizationProvider[];
  readonly onClose: () => void;
  readonly onCreated: () => void;
}) {
  const { t } = useTranslation();
  const [entries, setEntries] = useState<readonly ProviderCatalogEntry[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [apiKeyRef, setApiKeyRef] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enabledCatalogIds = useMemo(
    () =>
      new Set(
        existing
          .filter((p) => p.origin === 'catalog' && p.catalog_provider_id)
          .map((p) => p.catalog_provider_id as string),
      ),
    [existing],
  );

  useEffect(() => {
    fetchProviderCatalog()
      .then((page) => setEntries(page.items))
      .catch((err) => setError(err instanceof ApiError ? err.message : t('errors.network')))
      .finally(() => setLoading(false));
  }, [t]);

  async function handleSubmit() {
    if (!selectedId || !apiKeyRef.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await createOrganizationProvider({
        origin: 'catalog',
        catalog_provider_id: selectedId,
        api_key_ref: apiKeyRef.trim(),
      });
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell
      title={t('organization.catalogModal.title')}
      onClose={onClose}
      testId="enable-catalog-modal"
    >
      {loading ? (
        <LoaderCircle className="size-5 animate-spin text-slate-400" aria-hidden="true" />
      ) : (
        <div className="space-y-3">
          <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
            {t('organization.catalogModal.catalogProvider')}
            <select
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">{t('organization.catalogModal.select')}</option>
              {entries.map((entry) => (
                <option key={entry.id} value={entry.id} disabled={enabledCatalogIds.has(entry.id)}>
                  {entry.name}
                  {enabledCatalogIds.has(entry.id)
                    ? ` (${t('organization.catalogModal.alreadyEnabled')})`
                    : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
            {t('organization.catalogModal.apiKeyRef')}
            <input
              type="text"
              value={apiKeyRef}
              onChange={(e) => setApiKeyRef(e.target.value)}
              placeholder="OPENAI_API_KEY"
              className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm"
            />
          </label>
          {error !== null ? (
            <p role="alert" className="text-xs text-red-700">
              {error}
            </p>
          ) : null}
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700"
            >
              {t('organization.cancel')}
            </button>
            <button
              type="button"
              disabled={submitting || !selectedId || !apiKeyRef.trim()}
              onClick={() => void handleSubmit()}
              className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-60"
            >
              {submitting ? t('organization.saving') : t('organization.catalogModal.enable')}
            </button>
          </div>
        </div>
      )}
    </ModalShell>
  );
}

function CustomProviderModal({
  onClose,
  onCreated,
}: {
  readonly onClose: () => void;
  readonly onCreated: () => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [requestFormat, setRequestFormat] = useState('completion');
  const [defaultModel, setDefaultModel] = useState('');
  const [apiKeyRef, setApiKeyRef] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      await createOrganizationProvider({
        origin: 'custom',
        name: name.trim(),
        slug: slug.trim() || undefined,
        base_url: baseUrl.trim(),
        request_format: requestFormat,
        default_model: defaultModel.trim(),
        api_key_ref: apiKeyRef.trim(),
      });
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell
      title={t('organization.customModal.title')}
      onClose={onClose}
      testId="custom-provider-modal"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t('organization.customModal.name')} value={name} onChange={setName} />
        <Field label={t('organization.customModal.slug')} value={slug} onChange={setSlug} mono />
        <Field
          label={t('organization.customModal.baseUrl')}
          value={baseUrl}
          onChange={setBaseUrl}
          className="sm:col-span-2"
        />
        <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600 sm:col-span-2">
          {t('organization.customModal.requestFormat')}
          <select
            value={requestFormat}
            onChange={(e) => setRequestFormat(e.target.value)}
            className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="completion">completion</option>
            <option value="response">response</option>
            <option value="anthropic">anthropic</option>
            <option value="gemini">gemini</option>
          </select>
        </label>
        <Field
          label={t('organization.customModal.defaultModel')}
          value={defaultModel}
          onChange={setDefaultModel}
          mono
        />
        <Field
          label={t('organization.customModal.apiKeyRef')}
          value={apiKeyRef}
          onChange={setApiKeyRef}
          mono
        />
      </div>
      {error !== null ? (
        <p role="alert" className="mt-3 text-xs text-red-700">
          {error}
        </p>
      ) : null}
      <div className="mt-4 flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700"
        >
          {t('organization.cancel')}
        </button>
        <button
          type="button"
          disabled={
            submitting ||
            !name.trim() ||
            !baseUrl.trim() ||
            !defaultModel.trim() ||
            !apiKeyRef.trim()
          }
          onClick={() => void handleSubmit()}
          className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-60"
        >
          {submitting ? t('organization.saving') : t('organization.customModal.create')}
        </button>
      </div>
    </ModalShell>
  );
}

function SetDefaultModal({
  provider,
  baseClasses,
  onClose,
  onSaved,
}: {
  readonly provider: OrganizationProvider | null;
  readonly baseClasses: readonly BaseClass[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [target, setTarget] = useState<SetDefaultTarget>('system_hub');
  const [model, setModel] = useState(provider?.default_model ?? '');
  const [selectedBaseClassIds, setSelectedBaseClassIds] = useState<ReadonlySet<string>>(new Set());
  const [models, setModels] = useState<readonly CatalogModel[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (provider === null) return;
    fetchModelCatalog(provider.id)
      .then((page) => setModels(page.items))
      .catch(() => setModels([]));
  }, [provider]);

  function toggleBaseClass(id: string) {
    setSelectedBaseClassIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleSubmit() {
    if (provider === null || !model.trim()) return;
    if (target === 'base_class' && selectedBaseClassIds.size === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      await setProviderDefault(provider.id, {
        target,
        model: model.trim(),
        base_class_ids: target === 'base_class' ? Array.from(selectedBaseClassIds) : undefined,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'));
    } finally {
      setSubmitting(false);
    }
  }

  if (provider === null) return null;

  return (
    <ModalShell
      title={t('organization.setDefaultModal.title', { name: provider.name })}
      onClose={onClose}
      testId="set-default-modal"
    >
      <fieldset className="space-y-2">
        <legend className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          {t('organization.setDefaultModal.target')}
        </legend>
        {(['base_class', 'system_hub', 'cerebellum'] as const).map((value) => (
          <label key={value} className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="set-default-target"
              value={value}
              checked={target === value}
              onChange={() => setTarget(value)}
              className="size-4 accent-blue-600"
            />
            {t(`organization.setDefaultModal.targets.${value}`)}
          </label>
        ))}
      </fieldset>

      {target === 'base_class' ? (
        <div className="mt-3 max-h-40 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2">
          {baseClasses.map((bc) => (
            <label key={bc.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={selectedBaseClassIds.has(bc.id)}
                onChange={() => toggleBaseClass(bc.id)}
                className="size-4 accent-blue-600"
              />
              {bc.display_name ?? bc.name}
            </label>
          ))}
        </div>
      ) : null}

      <div className="mt-3 block text-xs font-semibold uppercase tracking-wide text-slate-600">
        {t('organization.fields.model')}
        {models.length > 0 ? (
          <select
            aria-label={t('organization.fields.model')}
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm"
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        ) : (
          <input
            aria-label={t('organization.fields.model')}
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm"
          />
        )}
      </div>

      {error !== null ? (
        <p role="alert" className="mt-3 text-xs text-red-700">
          {error}
        </p>
      ) : null}

      <div className="mt-4 flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700"
        >
          {t('organization.cancel')}
        </button>
        <button
          type="button"
          disabled={
            submitting ||
            !model.trim() ||
            (target === 'base_class' && selectedBaseClassIds.size === 0)
          }
          onClick={() => void handleSubmit()}
          className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-60"
        >
          {submitting ? t('organization.saving') : t('organization.setDefaultModal.confirm')}
        </button>
      </div>
    </ModalShell>
  );
}

function ModalShell({
  title,
  onClose,
  testId,
  children,
}: {
  readonly title: string;
  readonly onClose: () => void;
  readonly testId: string;
  readonly children: React.ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <div
      role="dialog"
      aria-modal="true"
      data-testid={testId}
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/50 p-0 sm:items-center sm:p-4"
    >
      <div className="w-full max-w-lg rounded-t-xl border border-slate-200 bg-white p-5 shadow-2xl sm:rounded-xl">
        <div className="mb-4 flex items-start justify-between gap-3">
          <h2 className="text-base font-semibold text-slate-950">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('organization.cancel')}
            className="grid size-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  mono = false,
  className,
}: {
  readonly label: string;
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly mono?: boolean;
  readonly className?: string;
}) {
  return (
    <label
      className={cn(
        'block text-xs font-semibold uppercase tracking-wide text-slate-600',
        className,
      )}
    >
      {label}
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          'mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm',
          mono && 'font-mono',
        )}
      />
    </label>
  );
}
