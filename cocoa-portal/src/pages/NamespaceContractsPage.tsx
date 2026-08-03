import { AlertCircle, Fingerprint, LoaderCircle, Plus, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';
import { ApiError } from '@/lib/api';
import {
  listNamespaceContractDetails,
  type NamespaceContractDetail,
  updateNamespaceContractAtoms,
} from '@/lib/api/contracts';
import { cn } from '@/lib/utils';
import { WORLD_ATOM_CATALOG } from '@/pages/WorldMembersPage';

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString();
}

export default function NamespaceContractsPage() {
  const { t } = useTranslation();
  const { nsId } = useParams<{ nsId: string }>();

  const [contracts, setContracts] = useState<readonly NamespaceContractDetail[] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingContractId, setPendingContractId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (nsId === undefined) return;
    setIsLoading(true);
    setLoadError(null);
    try {
      const page = await listNamespaceContractDetails(nsId, { includeInherited: true });
      setContracts(page.items);
    } catch (error) {
      setLoadError(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setIsLoading(false);
    }
  }, [nsId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function patchAtoms(
    contract: NamespaceContractDetail,
    nextSlugs: readonly string[],
  ): Promise<void> {
    if (nsId === undefined) return;
    setPendingContractId(contract.contract_id);
    setActionError(null);
    try {
      // H6: only namespace_atoms are writable — inherited_org_atoms are never
      // sent to the PATCH (they come from the world contract).
      await updateNamespaceContractAtoms(nsId, contract.contract_id, nextSlugs);
      await load();
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setPendingContractId(null);
    }
  }

  async function handleRemoveNamespaceAtom(
    contract: NamespaceContractDetail,
    slug: string,
  ): Promise<void> {
    const current = contract.namespace_atoms.map((atom) => atom.slug);
    await patchAtoms(
      contract,
      current.filter((s) => s !== slug),
    );
  }

  async function handleAddNamespaceAtom(
    contract: NamespaceContractDetail,
    slug: string,
  ): Promise<void> {
    const current = contract.namespace_atoms.map((atom) => atom.slug);
    if (current.includes(slug)) return;
    await patchAtoms(contract, [...current, slug]);
  }

  return (
    <section
      className="mx-auto w-full max-w-4xl p-6 lg:p-8"
      aria-labelledby="namespace-contracts-title"
    >
      <header className="mb-6 flex items-center gap-4">
        <span className="grid size-11 place-items-center rounded-xl bg-blue-600 text-white">
          <Fingerprint className="size-6" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h1
            id="namespace-contracts-title"
            className="truncate text-2xl font-semibold text-slate-950"
          >
            {t('namespaceContracts.title')}
          </h1>
          {contracts !== null ? (
            <p className="mt-1 text-sm text-slate-500">
              {t('namespaceContracts.contractCount', { count: contracts.length })}
            </p>
          ) : null}
        </div>
      </header>

      {loadError !== null ? (
        <div
          role="alert"
          className="mb-6 flex gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p className="flex-1">{loadError}</p>
          <button
            type="button"
            onClick={() => void load()}
            className="rounded-md px-2 py-0.5 text-xs font-semibold text-red-700 hover:bg-red-100"
          >
            {t('common.retry')}
          </button>
        </div>
      ) : null}

      {actionError !== null ? (
        <div
          role="alert"
          className="mb-6 flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p className="flex-1">{actionError}</p>
          <button
            type="button"
            onClick={() => setActionError(null)}
            className="rounded-md px-2 py-0.5 text-xs font-semibold text-red-700 hover:bg-red-100"
          >
            {t('common.dismiss')}
          </button>
        </div>
      ) : null}

      {isLoading && contracts === null ? (
        <div className="flex items-center justify-center gap-3 py-16 text-sm text-slate-500">
          <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
          {t('namespaceContracts.loading')}
        </div>
      ) : contracts !== null && contracts.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center">
          <Fingerprint className="mx-auto size-8 text-slate-400" aria-hidden="true" />
          <h2 className="mt-3 text-sm font-semibold text-slate-900">
            {t('namespaceContracts.empty')}
          </h2>
        </div>
      ) : contracts !== null ? (
        <ul className="space-y-3">
          {contracts.map((contract) => {
            const pending = pendingContractId === contract.contract_id;
            const namespaceSlugs = contract.namespace_atoms.map((atom) => atom.slug);
            const addableAtoms = WORLD_ATOM_CATALOG.filter(
              (atom) => !namespaceSlugs.includes(atom.slug),
            );
            return (
              <li
                key={contract.contract_id}
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-900">
                      {contract.user.nickname?.trim() || contract.user.username}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-slate-500">
                      {contract.user.username} · {contract.user.email}
                    </p>
                  </div>
                  <p className="shrink-0 text-xs text-slate-400">
                    {formatDate(contract.created_at)}
                  </p>
                </div>

                <div className="mt-3">
                  <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">
                    {t('namespaceContracts.namespaceLabel')}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {contract.namespace_atoms.map((atom) => (
                      <button
                        key={atom.slug}
                        type="button"
                        disabled={pending}
                        onClick={() => void handleRemoveNamespaceAtom(contract, atom.slug)}
                        title={`${t('namespaceContracts.removeAtom')}: ${atom.slug}`}
                        className={cn(
                          'inline-flex items-center gap-1 rounded-lg border border-blue-500 bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-800 transition-colors hover:bg-blue-100',
                          pending && 'cursor-wait opacity-60',
                        )}
                      >
                        {atom.slug}
                        <X className="size-3" aria-hidden="true" />
                      </button>
                    ))}
                    {addableAtoms.map((atom) => (
                      <button
                        key={atom.slug}
                        type="button"
                        disabled={pending}
                        onClick={() => void handleAddNamespaceAtom(contract, atom.slug)}
                        title={`${t('namespaceContracts.addAtom')}: ${atom.slug}`}
                        className={cn(
                          'inline-flex items-center gap-1 rounded-lg border border-dashed border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-500 transition-colors hover:border-blue-400 hover:text-blue-600',
                          pending && 'cursor-wait opacity-60',
                        )}
                      >
                        <Plus className="size-3" aria-hidden="true" />
                        {atom.slug}
                      </button>
                    ))}
                    {contract.namespace_atoms.length === 0 && addableAtoms.length === 0 ? (
                      <span className="text-xs text-slate-400">{t('common.none')}</span>
                    ) : null}
                  </div>
                </div>

                {contract.inherited_org_atoms !== undefined &&
                contract.inherited_org_atoms.length > 0 ? (
                  <div className="mt-3" data-testid="inherited-atoms">
                    <p
                      className="mb-1.5 flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-slate-400"
                      title={t('namespaceContracts.inheritedTooltip')}
                    >
                      {t('namespaceContracts.inheritedLabel')}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {contract.inherited_org_atoms.map((atom) => (
                        <span
                          key={atom.slug}
                          title={t('namespaceContracts.inheritedTooltip')}
                          className="inline-flex cursor-default items-center gap-1 rounded-lg border border-slate-200 bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-400"
                        >
                          {atom.slug}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
