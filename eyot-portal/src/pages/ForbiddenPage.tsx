import { ArrowLeft, ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router';

export default function ForbiddenPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const missing = searchParams.get('missing') ?? '';
  const gene = searchParams.get('gene') ?? '';
  const from = searchParams.get('from') ?? '';

  return (
    <main className="grid min-h-dvh place-items-center bg-slate-950 px-4 py-10 text-slate-100">
      <section className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8 text-center shadow-2xl">
        <ShieldAlert className="mx-auto size-12 text-red-400" aria-hidden="true" />
        <h1 className="mt-6 text-2xl font-semibold tracking-tight">{t('forbidden.title')}</h1>
        <p className="mt-3 text-sm leading-6 text-slate-400">{t('forbidden.detail')}</p>

        {gene.length > 0 ? (
          <p className="mt-4 text-sm text-slate-300">
            {t('forbidden.currentGene')}: <span className="font-mono">{gene}</span>
          </p>
        ) : null}

        {missing.length > 0 ? (
          <p className="mt-2 text-sm text-slate-300">
            {t('forbidden.missing')}: <span className="font-mono">{missing}</span>
          </p>
        ) : null}

        {from.length > 0 ? (
          <p className="mt-2 truncate text-xs text-slate-500">
            {t('forbidden.from')}: {decodeURIComponent(from)}
          </p>
        ) : null}

        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-center">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 hover:bg-slate-800"
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            {t('forbidden.goBack')}
          </button>
          <Link
            to="/namespaces"
            className="inline-flex items-center justify-center rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-500"
          >
            {t('forbidden.goNamespaces')}
          </Link>
        </div>
      </section>
    </main>
  );
}
