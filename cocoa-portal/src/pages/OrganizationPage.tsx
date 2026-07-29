import { AlertCircle, LoaderCircle, Settings } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError, api } from '@/lib/api';

type Organization = {
  readonly id: string;
  readonly slug: string;
  readonly name: string;
  readonly created_at: string;
  readonly updated_at: string;
};

export default function OrganizationPage() {
  const { t } = useTranslation();
  const [org, setOrg] = useState<Organization | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;
    async function load() {
      try {
        const data = await api<Organization>('/organizations/default');
        if (isActive) setOrg(data);
      } catch (error) {
        if (!isActive) return;
        if (error instanceof ApiError && error.status === 404) {
          setErrorMessage(t('organization.notAvailable'));
          return;
        }
        setErrorMessage(error instanceof ApiError ? error.message : t('errors.network'));
      } finally {
        if (isActive) setIsLoading(false);
      }
    }
    void load();
    return () => {
      isActive = false;
    };
  }, [t]);

  return (
    <section className="mx-auto w-full max-w-3xl p-6 lg:p-8">
      <header className="mb-6 flex items-center gap-3">
        <Settings className="size-6 text-slate-700" aria-hidden="true" />
        <h1 className="text-2xl font-semibold text-slate-900">{t('organization.title')}</h1>
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
          className="flex gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
        >
          <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
          <p>{errorMessage}</p>
        </div>
      ) : null}

      {org !== null ? (
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <dl className="grid gap-4 text-sm">
            <div>
              <dt className="text-slate-500">{t('organization.name')}</dt>
              <dd className="mt-1 font-medium text-slate-900">{org.name}</dd>
            </div>
            <div>
              <dt className="text-slate-500">{t('organization.slug')}</dt>
              <dd className="mt-1 font-mono text-slate-700">{org.slug}</dd>
            </div>
          </dl>
          <p className="mt-6 text-sm text-slate-500">{t('organization.providerHint')}</p>
        </div>
      ) : null}
    </section>
  );
}
