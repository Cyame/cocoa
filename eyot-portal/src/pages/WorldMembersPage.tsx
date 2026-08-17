import { AlertCircle, Check, LoaderCircle, Plus, Search, UserRound, X } from 'lucide-react';
import { type FormEvent, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';
import { ApiError } from '@/lib/api';
import {
  addOrganizationMember,
  fetchOrganizationMembers,
  removeOrganizationMember,
  searchUsers,
  updateOrganizationMember,
} from '@/lib/api/organizations';
import { resolveError as sharedResolveError } from '@/lib/apiError';
import type { OrgMember, UserBrief } from '@/lib/types';
import { cn } from '@/lib/utils';

/**
 * Full 16-atom world-management catalog shown as toggles/checkboxes.
 * Mirrors the backend single source eyot-backend/app/core/gene_atoms.py
 * (ATOM_CATALOG); display names come from worldMembers.atoms.<slug> i18n keys.
 */
export const WORLD_ATOM_CATALOG = [
  { slug: 'can_manage_organization', name: 'can_manage_organization' },
  { slug: 'can_manage_org_members', name: 'can_manage_org_members' },
  { slug: 'can_manage_namespace', name: 'can_manage_namespace' },
  { slug: 'can_manage_workspace', name: 'can_manage_workspace' },
  { slug: 'can_edit_workspace', name: 'can_edit_workspace' },
  { slug: 'can_view_workspace', name: 'can_view_workspace' },
  { slug: 'can_operate_workspace', name: 'can_operate_workspace' },
  { slug: 'can_manage_genes', name: 'can_manage_genes' },
  { slug: 'can_manage_capabilities', name: 'can_manage_capabilities' },
  { slug: 'can_manage_ai_genes', name: 'can_manage_ai_genes' },
  { slug: 'can_clone_base_class', name: 'can_clone_base_class' },
  { slug: 'can_clone_entity', name: 'can_clone_entity' },
  { slug: 'can_clone_organization', name: 'can_clone_organization' },
  { slug: 'can_clone_workspace', name: 'can_clone_workspace' },
  { slug: 'can_manage_knowledge', name: 'can_manage_knowledge' },
  { slug: 'can_manage_meetings', name: 'can_manage_meetings' },
] as const satisfies readonly { readonly slug: string; readonly name: string }[];

const SEARCH_DEBOUNCE_MS = 300;

const SELF_LOCK_MESSAGE_KEY = 'organization.cannot_lock_self';
const SELF_LOCK_ERROR_CODE = 'errors.org.cannot_lock_self';

/** H5 防自锁: backend 400 with the locked error_code / message_key pair. */
function isSelfLockError(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  const payload = error.payload;
  if (typeof payload !== 'object' || payload === null) return false;
  const record = payload as Record<string, unknown>;
  return record.message_key === SELF_LOCK_MESSAGE_KEY || record.error_code === SELF_LOCK_ERROR_CODE;
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString();
}

type TFn = ReturnType<typeof useTranslation>['t'];

function atomDisplayName(t: TFn, slug: string): string {
  return t(`worldMembers.atoms.${slug}`, { defaultValue: slug });
}

export default function WorldMembersPage() {
  const { t } = useTranslation();
  const { orgId } = useParams<{ orgId: string }>();

  const [members, setMembers] = useState<readonly OrgMember[] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingContractId, setPendingContractId] = useState<string | null>(null);

  const [showAdd, setShowAdd] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [selectedUser, setSelectedUser] = useState<UserBrief | null>(null);
  const [searchResults, setSearchResults] = useState<readonly UserBrief[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [selectedAtomSlugs, setSelectedAtomSlugs] = useState<readonly string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  // biome-ignore lint/correctness/useExhaustiveDependencies: resolveError captures t via closure
  const load = useCallback(async () => {
    if (orgId === undefined) return;
    setIsLoading(true);
    setLoadError(null);
    try {
      const page = await fetchOrganizationMembers(orgId);
      setMembers(page.items);
    } catch (error) {
      setLoadError(resolveError(error, 'errors.network'));
    } finally {
      setIsLoading(false);
    }
  }, [orgId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  // Debounced user search while the add form is open.
  useEffect(() => {
    const q = searchText.trim();
    if (q.length === 0) {
      setSearchResults(null);
      setIsSearching(false);
      return;
    }
    setIsSearching(true);
    const timer = window.setTimeout(() => {
      searchUsers(q)
        .then((page) => setSearchResults(page.items))
        .catch(() => setSearchResults([]))
        .finally(() => setIsSearching(false));
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [searchText]);

  function resolveError(error: unknown, fallbackKey: string): string {
    if (isSelfLockError(error)) {
      return t('worldMembers.selfLockError');
    }
    return sharedResolveError(t, error, fallbackKey);
  }

  async function handleToggleAtom(member: OrgMember, slug: string): Promise<void> {
    if (orgId === undefined) return;
    const has = member.atoms.some((atom) => atom.slug === slug);
    const nextSlugs = has
      ? member.atoms.filter((atom) => atom.slug !== slug).map((atom) => atom.slug)
      : [...member.atoms.map((atom) => atom.slug), slug];
    setPendingContractId(member.id);
    setActionError(null);
    try {
      await updateOrganizationMember(orgId, member.id, { atom_slugs: nextSlugs });
      await load();
    } catch (error) {
      setActionError(resolveError(error, 'errors.unknown'));
    } finally {
      setPendingContractId(null);
    }
  }

  async function handleRemoveMember(member: OrgMember): Promise<void> {
    if (orgId === undefined) return;
    const name = member.user.nickname?.trim() || member.user.username;
    const ok = window.confirm(t('worldMembers.removeConfirm', { name }));
    if (!ok) return;
    setActionError(null);
    try {
      await removeOrganizationMember(orgId, member.id);
      await load();
    } catch (error) {
      setActionError(resolveError(error, 'errors.unknown'));
    }
  }

  async function handleAddMember(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (orgId === undefined) return;
    const q = searchText.trim();
    if (selectedUser === null && q.length === 0) return;
    setSubmitting(true);
    setActionError(null);
    try {
      if (selectedUser !== null) {
        await addOrganizationMember(orgId, {
          user_id: selectedUser.id,
          atom_slugs: selectedAtomSlugs,
        });
      } else {
        await addOrganizationMember(orgId, { q, atom_slugs: selectedAtomSlugs });
      }
      setSelectedUser(null);
      setSearchText('');
      setSelectedAtomSlugs([]);
      setShowAdd(false);
      await load();
    } catch (error) {
      setActionError(resolveError(error, 'errors.unknown'));
    } finally {
      setSubmitting(false);
    }
  }

  function toggleCatalogAtom(slug: string): void {
    setSelectedAtomSlugs((prev) =>
      prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug],
    );
  }

  const canSubmitAdd = selectedUser !== null || searchText.trim().length > 0;

  return (
    <section className="mx-auto w-full max-w-4xl p-6 lg:p-8" aria-labelledby="world-members-title">
      <header className="mb-6 flex items-center justify-between gap-4">
        <div className="flex items-start gap-4">
          <span className="grid size-11 place-items-center rounded-xl bg-blue-600 text-white">
            <UserRound className="size-6" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h1 id="world-members-title" className="truncate text-2xl font-semibold text-slate-950">
              {t('worldMembers.title')}
            </h1>
            {members !== null ? (
              <p className="mt-1 text-sm text-slate-500">
                {t('worldMembers.memberCount', { count: members.length })}
              </p>
            ) : null}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setShowAdd((prev) => !prev)}
          data-testid="world-members-add-toggle"
          className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-500"
        >
          <Plus className="size-4" aria-hidden="true" />
          {t('worldMembers.addMember')}
        </button>
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

      {showAdd ? (
        <form
          onSubmit={(event) => void handleAddMember(event)}
          className="mb-8 space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
        >
          <h2 className="text-sm font-semibold text-slate-900">
            {t('worldMembers.addMemberTitle')}
          </h2>

          <div>
            <label
              htmlFor="world-members-search"
              className="mb-1.5 block text-sm font-medium text-slate-700"
            >
              {t('worldMembers.searchPlaceholder')}
            </label>
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400"
                aria-hidden="true"
              />
              <input
                id="world-members-search"
                type="text"
                value={searchText}
                onChange={(event) => {
                  setSearchText(event.currentTarget.value);
                  setSelectedUser(null);
                }}
                placeholder={t('worldMembers.searchPlaceholder')}
                autoComplete="off"
                className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm outline-none transition-colors placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30"
              />
            </div>
            {selectedUser !== null ? (
              <div className="mt-2 flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm">
                <span className="font-medium text-blue-900">{selectedUser.username}</span>
                <span className="text-blue-600">{selectedUser.email}</span>
                <button
                  type="button"
                  onClick={() => setSelectedUser(null)}
                  aria-label={t('common.dismiss')}
                  className="ml-auto rounded p-0.5 text-blue-500 hover:text-blue-700"
                >
                  <X className="size-4" aria-hidden="true" />
                </button>
              </div>
            ) : isSearching ? (
              <p className="mt-2 flex items-center gap-2 text-sm text-slate-400">
                <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                {t('common.loading')}
              </p>
            ) : searchText.trim().length === 0 ? (
              <p className="mt-2 text-sm text-slate-400">{t('worldMembers.searchEmpty')}</p>
            ) : searchResults !== null && searchResults.length === 0 ? (
              <p className="mt-2 text-sm text-slate-400">{t('worldMembers.noResults')}</p>
            ) : searchResults !== null ? (
              <ul className="mt-2 max-h-48 divide-y divide-slate-100 overflow-y-auto rounded-lg border border-slate-200">
                {searchResults.map((user) => (
                  <li key={user.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedUser(user);
                        setSearchText('');
                        setSearchResults(null);
                      }}
                      className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm transition-colors hover:bg-blue-50"
                    >
                      <span className="font-medium text-slate-800">{user.username}</span>
                      <span className="text-xs text-slate-500">{user.email}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>

          <div>
            <span className="mb-1.5 block text-sm font-medium text-slate-700">
              {t('worldMembers.atomSelect')}
            </span>
            <div className="flex flex-wrap gap-2">
              {WORLD_ATOM_CATALOG.map((atom) => {
                const checked = selectedAtomSlugs.includes(atom.slug);
                const displayName = atomDisplayName(t, atom.slug);
                return (
                  <label
                    key={atom.slug}
                    title={atom.slug}
                    className={cn(
                      'flex cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-sm transition-colors',
                      checked
                        ? 'border-blue-500 bg-blue-50 text-blue-800'
                        : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50',
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleCatalogAtom(atom.slug)}
                      className="size-4 accent-blue-600"
                    />
                    {displayName}
                  </label>
                );
              })}
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setShowAdd(false)}
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              data-testid="world-members-submit"
              disabled={!canSubmitAdd || submitting}
              aria-busy={submitting}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? (
                <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <Plus className="size-4" aria-hidden="true" />
              )}
              {t('worldMembers.addMember')}
            </button>
          </div>
        </form>
      ) : null}

      {isLoading && members === null ? (
        <div className="flex items-center justify-center gap-3 py-16 text-sm text-slate-500">
          <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
          {t('worldMembers.loading')}
        </div>
      ) : members !== null && members.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center">
          <UserRound className="mx-auto size-8 text-slate-400" aria-hidden="true" />
          <h2 className="mt-3 text-sm font-semibold text-slate-900">{t('worldMembers.empty')}</h2>
          <button
            type="button"
            onClick={() => setShowAdd(true)}
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-500"
          >
            <Plus className="size-4" aria-hidden="true" />
            {t('worldMembers.addMember')}
          </button>
        </div>
      ) : members !== null ? (
        <ul className="space-y-3">
          {members.map((member) => {
            const pending = pendingContractId === member.id;
            return (
              <li
                key={member.id}
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-900">
                      {member.user.nickname?.trim() || member.user.username}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-slate-500">
                      {member.user.username} · {member.user.email}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-xs text-slate-400">{formatDate(member.created_at)}</p>
                    <button
                      type="button"
                      onClick={() => void handleRemoveMember(member)}
                      className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-red-600 hover:text-red-700"
                    >
                      <X className="size-3" aria-hidden="true" />
                      {t('worldMembers.removeMember')}
                    </button>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {WORLD_ATOM_CATALOG.map((atom) => {
                    const has = member.atoms.some((a) => a.slug === atom.slug);
                    const displayName = atomDisplayName(t, atom.slug);
                    return (
                      <button
                        key={atom.slug}
                        type="button"
                        disabled={pending}
                        onClick={() => void handleToggleAtom(member, atom.slug)}
                        aria-pressed={has}
                        aria-label={`${displayName}: ${has ? 'on' : 'off'}`}
                        title={atom.slug}
                        className={cn(
                          'inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors',
                          has
                            ? 'border-blue-500 bg-blue-600 text-white hover:bg-blue-500'
                            : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50',
                          pending && 'cursor-wait opacity-60',
                        )}
                      >
                        {has ? <Check className="size-3" aria-hidden="true" /> : null}
                        {displayName}
                      </button>
                    );
                  })}
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
