import { AlertCircle, LoaderCircle, Sparkles } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';
import { ApiError } from '@/lib/api';
import { fetchBaseClass } from '@/lib/api/entities';
import type { BaseClass } from '@/lib/types';
import { useOnboardingModalStore } from '@/stores/onboardingModalStore';

export default function BaseClassDetailPage() {
  const { t } = useTranslation();
  const { slug } = useParams<{ slug: string }>();
  const [baseClass, setBaseClass] = useState<BaseClass | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const openOnboarding = useOnboardingModalStore((state) => state.open);

  useEffect(() => {
    if (slug === undefined) return;
    let isActive = true;
    async function load() {
      try {
        const data = await fetchBaseClass(slug as string);
        if (isActive) setBaseClass(data);
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
                  {baseClass.display_name ?? baseClass.name}
                </h1>
                <p className="mt-1 font-mono text-sm text-slate-500">{baseClass.slug}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={openOnboarding}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500"
            >
              {t('namespaces.summonFromBaseClass')}
            </button>
          </header>
          <p className="text-sm leading-6 text-slate-600">{baseClass.description}</p>
        </>
      ) : null}
    </section>
  );
}
