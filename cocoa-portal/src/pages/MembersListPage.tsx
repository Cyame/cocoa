import { AlertCircle, Cpu, LoaderCircle, MapPin, UserRound, Users } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';
import { ApiError, api } from '@/lib/api';
import type { Membership } from '@/lib/types';

type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly offset: number;
  readonly limit: number;
  readonly total: number;
};

const ROLE_BADGE_CLASS: Readonly<Record<string, string>> = {
  owner: 'bg-amber-100 text-amber-800',
  editor: 'bg-blue-100 text-blue-800',
  viewer: 'bg-slate-100 text-slate-700',
};

export default function MembersListPage() {
  const { t } = useTranslation();
  const { id: officeId } = useParams<{ id: string }>();
  const [members, setMembers] = useState<readonly Membership[] | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (officeId === undefined) {
      setErrorMessage(t('members.officeIdMissing'));
      return;
    }
    let isActive = true;

    async function loadMembers() {
      try {
        const page = await api<OffsetPage<Membership>>(
          `/messaging/memberships?office_id=${encodeURIComponent(officeId as string)}&limit=200`,
        );
        if (isActive) setMembers(page.items);
      } catch (error) {
        if (error instanceof ApiError) {
          if (isActive) setErrorMessage(error.message);
          return;
        }
        throw error;
      }
    }

    void loadMembers();
    return () => {
      isActive = false;
    };
  }, [officeId, t]);

  return (
    <section className="mx-auto w-full max-w-6xl p-6 lg:p-8" aria-labelledby="members-list-title">
      <header className="mb-8 flex items-start gap-4">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
          <Users className="size-6" aria-hidden="true" />
        </span>
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-blue-700">
            {t('members.eyebrow')}
          </p>
          <h1
            id="members-list-title"
            className="mt-1 text-3xl font-semibold tracking-tight text-slate-950"
          >
            {t('members.title')}
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            {t('members.subtitle', { count: members?.length ?? 0 })}
          </p>
        </div>
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

      {members === null ? (
        <div className="flex items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white px-6 py-16 text-sm text-slate-500">
          <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
          {t('members.loading')}
        </div>
      ) : null}

      {members !== null && members.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
          <Users className="mx-auto size-8 text-slate-400" aria-hidden="true" />
          <h2 className="mt-4 text-base font-semibold text-slate-900">{t('members.emptyTitle')}</h2>
          <p className="mt-2 text-sm text-slate-500">{t('members.emptyDetail')}</p>
        </div>
      ) : null}

      {members !== null && members.length > 0 ? (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {members.map((member) => {
            const kind = member.user_id !== null ? 'user' : 'instance';
            const KindIcon = kind === 'user' ? UserRound : Cpu;
            const badgeClass = ROLE_BADGE_CLASS[member.role] ?? 'bg-slate-100 text-slate-700';
            return (
              <li
                key={member.id}
                className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-[border-color,box-shadow] hover:border-blue-300 hover:shadow-md"
              >
                <div className="flex items-start gap-3">
                  <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-indigo-50 text-indigo-700">
                    <KindIcon className="size-5" aria-hidden="true" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-xs text-slate-500">{member.id}</p>
                    <p className="mt-0.5 text-sm font-medium text-slate-900">
                      {kind === 'user' ? (
                        <span>{t('members.userKind')}</span>
                      ) : (
                        <span>{t('members.instanceKind')}</span>
                      )}
                    </p>
                  </div>
                  <span
                    className={`inline-flex shrink-0 items-center rounded-full px-2.5 py-1 text-xs font-semibold ${badgeClass}`}
                  >
                    {t(`members.role.${member.role}`)}
                  </span>
                </div>
                <div className="mt-4 flex items-center gap-2 text-xs text-slate-500">
                  <MapPin className="size-3.5" aria-hidden="true" />
                  <span>
                    {t('members.positionLabel')}: ({member.posx}, {member.posy})
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
