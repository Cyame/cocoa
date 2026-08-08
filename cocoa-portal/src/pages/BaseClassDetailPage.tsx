import { AlertCircle, LoaderCircle, Sparkles } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';
import { ModelInputCombobox } from '@/components/ModelInputCombobox';
import { ApiError } from '@/lib/api';
import { fetchBaseClass } from '@/lib/api/entities';
import {
  fetchBaseClassProviderDefault,
  fetchModelCatalog,
  listOrganizationProviders,
  type OrganizationProvider,
  updateBaseClassProviderDefault,
} from '@/lib/api/providers';
import type { BaseClass } from '@/lib/types';
import { useOnboardingModalStore } from '@/stores/onboardingModalStore';
import { useSessionStore } from '@/stores/session';

export default function BaseClassDetailPage() {
  const { t } = useTranslation();
  const { slug } = useParams<{ slug: string }>();
  const isSuperAdmin = useSessionStore((s) => s.user?.is_super_admin === true);
  const [baseClass, setBaseClass] = useState<BaseClass | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [providers, setProviders] = useState<readonly OrganizationProvider[]>([]);
  const [providerId, setProviderId] = useState('');
  const [model, setModel] = useState('');
  const [models, setModels] = useState<readonly string[]>([]);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const openOnboarding = useOnboardingModalStore((state) => state.open);

  useEffect(() => {
    if (slug === undefined) return;
    let isActive = true;
    async function load() {
      try {
        const data = await fetchBaseClass(slug as string);
        if (!isActive) return;
        setBaseClass(data);
        const [enabledProviders, binding] = await Promise.all([
          listOrganizationProviders(true),
          fetchBaseClassProviderDefault(data.id),
        ]);
        if (!isActive) return;
        setProviders(enabledProviders);
        if (binding) {
          setProviderId(binding.provider_id);
          setModel(binding.model);
        }
      } catch (error) {
        if (!isActive) return;
        setErrorMessage(error instanceof ApiError ? error.message : t('errors.network'));
      } finally {
        if (isActive) setIsLoading(false);
      }
    }
    void load();
    return () => {
      isActive = false;
    };
  }, [slug, t]);

  useEffect(() => {
    if (!providerId) {
      setModels([]);
      return;
    }
    let cancelled = false;
    void fetchModelCatalog(providerId)
      .then((page) => {
        if (!cancelled) setModels(page.items.map((m) => m.id));
      })
      .catch(() => {
        if (!cancelled) setModels([]);
      });
    return () => {
      cancelled = true;
    };
  }, [providerId]);

  async function handleSaveDefault() {
    if (!baseClass || !providerId || !model) return;
    setIsSaving(true);
    setSaveMsg(null);
    try {
      await updateBaseClassProviderDefault(baseClass.id, {
        provider_id: providerId,
        model,
      });
      setSaveMsg(t('baseClass.providerDefaultSaved'));
    } catch (error) {
      setSaveMsg(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setIsSaving(false);
    }
  }

  if (slug === undefined) {
    return <p className="p-6 text-sm text-red-700">{t('baseClass.slugMissing')}</p>;
  }

  return (
    <section className="mx-auto w-full max-w-4xl p-6 lg:p-8">
      {isLoading ? (
        <div className="flex items-center gap-3 text-sm text-slate-500">
          <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
          {t('common.loading')}
        </div>
      ) : null}

      {errorMessage !== null ? (
        <div
          role="alert"
          className="flex gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
          <p>{errorMessage}</p>
        </div>
      ) : null}

      {baseClass !== null ? (
        <>
          <header className="mb-6 flex items-start justify-between gap-4">
            <div className="flex items-start gap-4">
              <span className="grid size-11 place-items-center rounded-xl bg-blue-600 text-white">
                <Sparkles className="size-6" aria-hidden="true" />
              </span>
              <div>
                <h1 className="text-2xl font-semibold text-slate-950">
                  {t(baseClass.display_name ?? baseClass.name, { defaultValue: baseClass.name })}
                </h1>
                <p className="mt-1 font-mono text-sm text-slate-500">{baseClass.slug}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => openOnboarding({ baseClassSlug: baseClass.slug })}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500"
            >
              {t('namespaces.summonFromBaseClass')}
            </button>
          </header>
          <p className="text-sm leading-6 text-slate-600">{baseClass.description}</p>

          <section className="mt-8 rounded-xl border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-900">
              {t('baseClass.providerDefaultTitle')}
            </h2>
            <p className="mt-1 text-xs text-slate-500">{t('baseClass.providerDefaultHint')}</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <label className="block text-xs font-medium text-slate-600">
                {t('organization.fields.provider')}
                <select
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  value={providerId}
                  disabled={!isSuperAdmin}
                  onChange={(e) => {
                    setProviderId(e.target.value);
                    setModel('');
                  }}
                >
                  <option value="">{t('organization.catalogModal.select')}</option>
                  {providers.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
              <label
                htmlFor="base-class-model"
                className="block text-xs font-medium text-slate-600"
              >
                {t('organization.fields.model')}
                <ModelInputCombobox
                  id="base-class-model"
                  aria-label={t('organization.fields.model')}
                  value={model}
                  onChange={setModel}
                  options={models.map((id) => ({ id, name: id }))}
                  disabled={!isSuperAdmin || !providerId}
                  placeholder={t('organization.fields.modelPlaceholder')}
                  className="mt-1"
                />
              </label>
            </div>
            {isSuperAdmin ? (
              <button
                type="button"
                disabled={isSaving || !providerId || !model}
                onClick={() => void handleSaveDefault()}
                className="mt-4 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
              >
                {isSaving ? t('organization.saving') : t('baseClass.saveProviderDefault')}
              </button>
            ) : null}
            {saveMsg ? <p className="mt-2 text-xs text-slate-600">{saveMsg}</p> : null}
          </section>
        </>
      ) : null}
    </section>
  );
}
