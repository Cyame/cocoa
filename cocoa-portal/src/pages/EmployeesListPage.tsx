import { AlertCircle, BookOpen, LoaderCircle, UserRound } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';
import { ApiError, api } from '@/lib/api';
import type { Employee } from '@/lib/types';

type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly offset: number;
  readonly limit: number;
  readonly total: number;
};

export default function EmployeesListPage() {
  const { t } = useTranslation();
  const { id: officeId } = useParams<{ id: string }>();
  const [employees, setEmployees] = useState<readonly Employee[] | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;

    async function loadEmployees() {
      try {
        const page = await api<OffsetPage<Employee>>('/employees?limit=200');
        if (isActive) setEmployees(page.items);
      } catch (error) {
        if (error instanceof ApiError) {
          if (isActive) setErrorMessage(error.message);
          return;
        }
        throw error;
      }
    }

    void loadEmployees();
    return () => {
      isActive = false;
    };
  }, []);

  return (
    <section className="mx-auto w-full max-w-6xl p-6 lg:p-8" aria-labelledby="employees-list-title">
      <header className="mb-8 flex items-start gap-4">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
          <UserRound className="size-6" aria-hidden="true" />
        </span>
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-blue-700">
            {t('employees.eyebrow')}
          </p>
          <h1
            id="employees-list-title"
            className="mt-1 text-3xl font-semibold tracking-tight text-slate-950"
          >
            {t('employees.title')}
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            {t('employees.subtitle', {
              count: employees?.length ?? 0,
              office: officeId ?? '—',
            })}
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

      {employees === null ? (
        <div className="flex items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white px-6 py-16 text-sm text-slate-500">
          <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
          {t('employees.loading')}
        </div>
      ) : null}

      {employees !== null && employees.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
          <UserRound className="mx-auto size-8 text-slate-400" aria-hidden="true" />
          <h2 className="mt-4 text-base font-semibold text-slate-900">
            {t('employees.emptyTitle')}
          </h2>
          <p className="mt-2 text-sm text-slate-500">{t('employees.emptyDetail')}</p>
        </div>
      ) : null}

      {employees !== null && employees.length > 0 ? (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {employees.map((emp) => (
            <li
              key={emp.id}
              className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-[border-color,box-shadow] hover:border-blue-300 hover:shadow-md"
            >
              <div className="flex items-start gap-3">
                <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-emerald-50 text-emerald-700">
                  <UserRound className="size-5" aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-base font-semibold tracking-tight text-slate-950">
                    {emp.name}
                  </p>
                  <p className="mt-0.5 font-mono text-xs text-slate-500">@{emp.slug}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {t('employees.rankLabel', { rank: t(`employees.rank.${emp.rank}`) })}
                  </p>
                </div>
              </div>
              <Link
                to={`/employees/${encodeURIComponent(emp.id)}/learning`}
                className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-blue-600 transition-colors hover:text-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                <BookOpen className="size-4" aria-hidden="true" />
                {t('employees.viewLearning')}
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
