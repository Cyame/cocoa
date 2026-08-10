import {
  AlertCircle,
  Building2,
  Copy,
  Layers,
  LoaderCircle,
  Pencil,
  Plus,
  Sparkles,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useParams } from 'react-router';
import CloneDialog from '@/components/CloneDialog';
import SubagentChips, { extractSubagentCapabilities } from '@/components/SubagentChips';
import { ApiError } from '@/lib/api';
import { fetchMe } from '@/lib/api/auth';
import { fetchBaseClassesPage } from '@/lib/api/baseClasses';
import { type ClonePayload, cloneBaseClass } from '@/lib/api/clone';
import { resolveError } from '@/lib/apiError';
import { translateBaseClassTag } from '@/lib/baseClassTags';
import type { BaseClass, OrgIdentity } from '@/lib/types';
import { useOnboardingModalStore } from '@/stores/onboardingModalStore';
import { useSessionStore } from '@/stores/session';

export default function BaseClassesPage() {
  const { t } = useTranslation();
  const { orgId } = useParams<{ orgId: string }>();
  const user = useSessionStore((state) => state.user);
  const isSuperAdmin = user?.is_super_admin ?? false;
  const [orgIdentity, setOrgIdentity] = useState<OrgIdentity | null>(null);
  const canCloneBaseClass =
    isSuperAdmin || (orgIdentity?.atoms.includes('can_clone_base_class') ?? false);

  const [baseClasses, setBaseClasses] = useState<readonly BaseClass[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUnauthorized, setIsUnauthorized] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [cloningId, setCloningId] = useState<string | null>(null);
  const [cloneTarget, setCloneTarget] = useState<BaseClass | null>(null);

  const openOnboarding = useOnboardingModalStore((state) => state.open);

  useEffect(() => {
    if (orgId === undefined) {
      setOrgIdentity(null);
      return;
    }
    let cancelled = false;
    fetchMe()
      .then((me) => {
        if (!cancelled) setOrgIdentity(me.org_identity ?? null);
      })
      .catch(() => {
        if (!cancelled) setOrgIdentity(null);
      });
    return () => {
      cancelled = true;
    };
  }, [orgId]);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const page = await fetchBaseClassesPage({ limit: 50, offset: 0 });
      setBaseClasses(
        page.items.filter(
          (bc) =>
            bc.slug !== 'cerebellum-baseclass' &&
            !(bc.tags ?? []).some((tag) => tag === 'internal' || tag === 'system'),
        ),
      );
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 401) {
          setIsUnauthorized(true);
          return;
        }
      }
      setErrorMessage(resolveError(t, error));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleClone = useCallback(
    async (baseClass: BaseClass, payload: ClonePayload) => {
      setCloningId(baseClass.id);
      setErrorMessage(null);
      try {
        await cloneBaseClass(baseClass.id, payload);
        await refresh();
      } catch (error) {
        setErrorMessage(resolveError(t, error, 'clone.error'));
      } finally {
        setCloningId(null);
        setCloneTarget(null);
      }
    },
    [refresh, t],
  );

  if (isUnauthorized) {
    return <Navigate to="/login" replace />;
  }

  return (
    <section className="mx-auto w-full max-w-6xl p-6 lg:p-8" aria-labelledby="base-classes-title">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-4">
          <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
            <Building2 className="size-6" aria-hidden="true" />
          </span>
          <div>
            <h1 id="base-classes-title" className="text-2xl font-semibold text-slate-950">
              {t('nav.divinity')}
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-slate-600">{t('namespaces.subtitle')}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => openOnboarding()}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500"
        >
          <Sparkles className="size-4" aria-hidden="true" />
          {t('namespaces.summonEntity')}
        </button>
      </header>

      {errorMessage !== null ? (
        <div
          role="alert"
          className="mb-6 flex gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p>{errorMessage}</p>
        </div>
      ) : null}

      {isLoading ? (
        <div className="flex items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white px-6 py-16 text-sm text-slate-500">
          <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
          {t('common.loading')}
        </div>
      ) : null}

      {!isLoading ? (
        <BaseClassGrid
          orgId={orgId ?? ''}
          baseClasses={baseClasses}
          canClone={canCloneBaseClass}
          cloningId={cloningId}
          onClone={(bc) => setCloneTarget(bc)}
          onSummon={(slug) => openOnboarding({ baseClassSlug: slug })}
          t={t}
        />
      ) : null}

      <CloneDialog
        open={cloneTarget !== null}
        title={t('clone.baseClass')}
        confirmMessage={t('clone.dialog.confirmBaseClass', {
          name: cloneTarget?.display_name ?? cloneTarget?.name ?? '',
        })}
        confirmLabel={t('clone.baseClass')}
        busy={cloneTarget !== null && cloningId === cloneTarget.id}
        onConfirm={(payload) => {
          if (cloneTarget !== null) void handleClone(cloneTarget, payload);
        }}
        onCancel={() => setCloneTarget(null)}
      />
    </section>
  );
}

type TFn = ReturnType<typeof useTranslation>['t'];

function BaseClassGrid({
  orgId,
  baseClasses,
  canClone,
  cloningId,
  onClone,
  onSummon,
  t,
}: {
  readonly orgId: string;
  readonly baseClasses: readonly BaseClass[];
  readonly canClone: boolean;
  readonly cloningId: string | null;
  readonly onClone: (baseClass: BaseClass) => void;
  readonly onSummon: (slug: string) => void;
  readonly t: TFn;
}) {
  if (baseClasses.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
        <p className="text-sm text-slate-500">{t('namespaces.noEntities')}</p>
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {baseClasses.map((bc) => (
        <article key={bc.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <Link to={`/orgs/${orgId}/base-classes/${bc.slug}`} className="block">
            <div className="flex items-start justify-between gap-2">
              <h2 className="text-lg font-semibold text-slate-950">
                {t(bc.display_name ?? bc.name, { defaultValue: bc.name })}
              </h2>
              {bc.scope === 'system' ? (
                <span className="inline-flex shrink-0 items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                  <Layers className="size-3" aria-hidden="true" />
                  {t('namespaces.preset')}
                </span>
              ) : (
                <span className="inline-flex shrink-0 items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                  <Pencil className="size-3" aria-hidden="true" />
                  {t('namespaces.custom')}
                </span>
              )}
            </div>
            <p className="mt-1 font-mono text-xs text-slate-500">{bc.slug}</p>
            <p className="mt-3 line-clamp-3 text-sm text-slate-600">{bc.description}</p>
          </Link>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {(bc.tags ?? []).map((tag) => (
              <span
                key={tag}
                className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600"
              >
                {translateBaseClassTag(tag, t)}
              </span>
            ))}
          </div>
          <div className="mt-3">
            <SubagentChips capabilities={extractSubagentCapabilities(bc.manifest)} />
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => onSummon(bc.slug)}
              className="inline-flex items-center gap-1 text-sm font-medium text-blue-600 hover:text-blue-700"
            >
              <Plus className="size-3.5" aria-hidden="true" />
              {t('namespaces.summonFromBaseClass')}
            </button>
            {canClone ? (
              <button
                type="button"
                disabled={cloningId !== null}
                onClick={() => onClone(bc)}
                data-testid={`base-class-clone-${bc.id}`}
                title={t('clone.instancesNotCopied')}
                className="inline-flex items-center gap-1 text-sm font-medium text-slate-600 hover:text-slate-900 disabled:opacity-50"
              >
                <Copy className="size-3.5" aria-hidden="true" />
                {cloningId === bc.id ? t('clone.cloning') : t('clone.baseClass')}
              </button>
            ) : null}
          </div>
        </article>
      ))}
    </div>
  );
}
