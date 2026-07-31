import { AlertCircle, LoaderCircle, Plus, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '@/lib/api';
import {
  type AdminUser,
  type CatalogUserGene,
  createUser,
  deleteUser,
  type IdentityKey,
  listUserGenes,
  listUsers,
  setUserExtraGenes,
  setUserIdentity,
  updateUser,
} from '@/lib/api/users';

const IDENTITIES: IdentityKey[] = ['system', 'org', 'namespace', 'workspace', 'member'];

type Props = {
  readonly canWrite: boolean;
};

export default function OrganizationUsersPanel({ canWrite }: Props) {
  const { t } = useTranslation();
  const [users, setUsers] = useState<readonly AdminUser[]>([]);
  const [genes, setGenes] = useState<readonly CatalogUserGene[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [editingExtrasFor, setEditingExtrasFor] = useState<string | null>(null);
  const [username, setUsername] = useState('');
  const [nickname, setNickname] = useState('');
  const [email, setEmail] = useState('');
  const [identity, setIdentity] = useState<IdentityKey>('member');
  const [busy, setBusy] = useState(false);
  const [tempPassword, setTempPassword] = useState<string | null>(null);

  const extraGeneOptions = useMemo(
    () => genes.filter((g) => !g.slug.startsWith('identity-')),
    [genes],
  );

  const load = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const [userPage, genePage] = await Promise.all([listUsers(), listUserGenes()]);
      setUsers(userPage.items);
      setGenes(genePage.items);
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleCreate() {
    if (!canWrite) return;
    setBusy(true);
    setErrorMessage(null);
    setTempPassword(null);
    try {
      const created = await createUser({
        username,
        nickname: nickname.trim() || null,
        email,
        identity,
      });
      setTempPassword(created.temporary_password);
      setUsername('');
      setNickname('');
      setEmail('');
      setIdentity('member');
      setCreateOpen(false);
      await load();
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setBusy(false);
    }
  }

  async function toggleExtraGene(user: AdminUser, geneId: string, checked: boolean) {
    const current = new Set(user.extra_genes.map((g) => g.id));
    if (checked) current.add(geneId);
    else current.delete(geneId);
    try {
      await setUserExtraGenes(user.id, Array.from(current));
      await load();
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : t('errors.network'));
    }
  }

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
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-slate-900">{t('organization.users.title')}</h2>
        {canWrite ? (
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500"
          >
            <Plus className="size-4" aria-hidden="true" />
            {t('organization.users.create')}
          </button>
        ) : null}
      </div>

      {errorMessage ? (
        <div
          role="alert"
          className="flex gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p>{errorMessage}</p>
        </div>
      ) : null}

      {tempPassword ? (
        <p
          role="status"
          className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
        >
          {t('organization.users.tempPassword')}:{' '}
          <span className="font-mono font-semibold">{tempPassword}</span>
        </p>
      ) : null}

      {createOpen ? (
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">
                {t('organization.users.username')}
              </span>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder={t('organization.users.usernameHint')}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">
                {t('organization.users.nickname')}
              </span>
              <input
                value={nickname}
                onChange={(e) => setNickname(e.target.value)}
                placeholder={t('organization.users.nicknameHint')}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">
                {t('organization.users.email')}
              </span>
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">
                {t('organization.users.identity')}
              </span>
              <select
                value={identity}
                onChange={(e) => setIdentity(e.target.value as IdentityKey)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                {IDENTITIES.map((key) => (
                  <option key={key} value={key}>
                    {t(`identity.${key}`)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="mt-3 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setCreateOpen(false)}
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              {t('common.cancel')}
            </button>
            <button
              type="button"
              disabled={busy || !username.trim() || !email.trim()}
              onClick={() => void handleCreate()}
              className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60"
            >
              {t('organization.users.create')}
            </button>
          </div>
        </div>
      ) : null}

      {users.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center text-sm text-slate-500">
          {t('organization.users.empty')}
        </p>
      ) : (
        <div className="space-y-3">
          {users.map((user) => {
            const editing = editingExtrasFor === user.id;
            return (
              <div
                key={user.id}
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-slate-900">
                      {user.nickname?.trim() || user.username}
                    </p>
                    <p className="font-mono text-xs text-slate-500">{user.username}</p>
                    <p className="text-sm text-slate-500">{user.email}</p>
                  </div>
                  {canWrite ? (
                    <button
                      type="button"
                      onClick={() => {
                        void deleteUser(user.id).then(load);
                      }}
                      className="inline-flex items-center gap-1 text-sm text-red-600 hover:text-red-700"
                    >
                      <Trash2 className="size-3.5" aria-hidden="true" />
                      {t('organization.users.delete')}
                    </button>
                  ) : null}
                </div>

                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <label className="block text-sm">
                    <span className="mb-1 block font-medium text-slate-700">
                      {t('organization.users.nickname')}
                    </span>
                    {canWrite ? (
                      <input
                        defaultValue={user.nickname ?? ''}
                        key={`${user.id}:${user.nickname ?? ''}`}
                        onBlur={(e) => {
                          const next = e.target.value.trim() || null;
                          if (next === (user.nickname ?? null)) return;
                          void updateUser(user.id, { nickname: next }).then(load);
                        }}
                        placeholder={t('organization.users.nicknameHint')}
                        className="w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm"
                      />
                    ) : (
                      <p className="text-sm text-slate-700">{user.nickname?.trim() || '—'}</p>
                    )}
                  </label>
                  <label className="block text-sm">
                    <span className="mb-1 block font-medium text-slate-700">
                      {t('organization.users.identity')}
                    </span>
                    {canWrite ? (
                      <select
                        value={user.identity ?? 'member'}
                        onChange={(e) => {
                          void setUserIdentity(user.id, e.target.value as IdentityKey).then(load);
                        }}
                        className="w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm"
                      >
                        {IDENTITIES.map((key) => (
                          <option key={key} value={key}>
                            {t(`identity.${key}`)}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <p className="text-sm text-slate-700">
                        {t(`identity.${user.identity ?? 'member'}`)}
                      </p>
                    )}
                  </label>
                  <div className="text-sm">
                    <span className="mb-1 block font-medium text-slate-700">
                      {t('account.lockedGenes')}
                    </span>
                    <p className="font-mono text-xs text-slate-500">
                      {user.locked_genes.map((g) => g.slug).join(', ') || '—'}
                    </p>
                  </div>
                </div>

                <div className="mt-3">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-slate-700">
                      {t('account.extraGenes')}
                    </span>
                    {canWrite ? (
                      <button
                        type="button"
                        onClick={() =>
                          setEditingExtrasFor((prev) => (prev === user.id ? null : user.id))
                        }
                        className="rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                      >
                        {editing
                          ? t('common.done')
                          : t('organization.users.editExtraGenes')}
                      </button>
                    ) : null}
                  </div>
                  {!editing ? (
                    <p className="font-mono text-xs text-slate-600">
                      {user.extra_genes.map((g) => g.slug).join(', ') || '—'}
                    </p>
                  ) : extraGeneOptions.length === 0 ? (
                    <p className="text-xs text-slate-500">{t('organization.users.noExtraGenes')}</p>
                  ) : (
                    <div className="grid max-h-48 gap-1 overflow-y-auto rounded-lg border border-slate-200 p-2 sm:grid-cols-2">
                      {extraGeneOptions.map((g) => {
                        const checked = user.extra_genes.some((x) => x.id === g.id);
                        return (
                          <label
                            key={g.id}
                            className="flex items-start gap-2 rounded-md px-2 py-1 text-xs hover:bg-slate-50"
                          >
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(e) => {
                                void toggleExtraGene(user, g.id, e.target.checked);
                              }}
                              className="mt-0.5 size-3.5 accent-blue-600"
                            />
                            <span>
                              <span className="font-mono text-slate-800">{g.slug}</span>
                              {g.description ? (
                                <span className="mt-0.5 block text-slate-500">{g.description}</span>
                              ) : null}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
