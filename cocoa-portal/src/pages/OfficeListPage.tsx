import { AlertCircle, Building2, Cpu, LoaderCircle, Users } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, Navigate } from 'react-router';
import { ApiError, api } from '@/lib/api';
import type { Office } from '@/lib/types';

type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly offset: number;
  readonly limit: number;
  readonly total: number;
};

type OfficeSummary = {
  readonly office: Office;
  readonly memberCount: number;
  readonly instanceCount: number;
};

type CountPage = {
  readonly items: readonly { readonly id: string }[];
  readonly total: number;
};

export default function OfficeListPage() {
  const [offices, setOffices] = useState<readonly OfficeSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUnauthorized, setIsUnauthorized] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;

    async function loadOffices() {
      try {
        const officePage = await api<OffsetPage<Office>>('/offices');
        const summaries = await Promise.all(
          officePage.items.map(async (office) => {
            const [memberships, instances] = await Promise.all([
              api<CountPage>(`/messaging/memberships?office_id=${encodeURIComponent(office.id)}`),
              api<CountPage>(`/instances?office_id=${encodeURIComponent(office.id)}`),
            ]);
            return {
              office,
              memberCount: memberships.total,
              instanceCount: instances.total,
            } satisfies OfficeSummary;
          }),
        );
        if (isActive) setOffices(summaries);
      } catch (error) {
        if (error instanceof ApiError) {
          if (error.status === 401) {
            if (isActive) setIsUnauthorized(true);
            return;
          }
          if (isActive) setErrorMessage(error.message);
          return;
        }
        throw error;
      } finally {
        if (isActive) setIsLoading(false);
      }
    }

    void loadOffices();
    return () => {
      isActive = false;
    };
  }, []);

  if (isUnauthorized) {
    return <Navigate to="/login" replace />;
  }

  return (
    <section className="mx-auto w-full max-w-6xl p-6 lg:p-8" aria-labelledby="office-list-title">
      <header className="mb-8 flex items-start gap-4">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
          <Building2 className="size-6" aria-hidden="true" />
        </span>
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-blue-700">
            Workspace index
          </p>
          <h1
            id="office-list-title"
            className="mt-1 text-3xl font-semibold tracking-tight text-slate-950"
          >
            Offices
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Select an office to inspect its employees, running instances, and shared blackboard.
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

      {isLoading ? (
        <div className="flex items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white px-6 py-16 text-sm text-slate-500">
          <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
          Loading offices
        </div>
      ) : null}

      {!isLoading && errorMessage === null && offices.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
          <Building2 className="mx-auto size-8 text-slate-400" aria-hidden="true" />
          <h2 className="mt-4 text-base font-semibold text-slate-900">No offices available</h2>
          <p className="mt-2 text-sm text-slate-500">
            Your account does not have an active office yet.
          </p>
        </div>
      ) : null}

      {!isLoading && offices.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {offices.map(({ office, memberCount, instanceCount }) => (
            <Link
              key={office.id}
              to={`/offices/${office.id}`}
              aria-label={`Open ${office.name}`}
              className="group rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-[border-color,box-shadow,transform] hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              <div className="flex items-start justify-between gap-4">
                <span className="grid size-10 place-items-center rounded-lg bg-blue-50 text-blue-700 transition-colors group-hover:bg-blue-100">
                  <Building2 className="size-5" aria-hidden="true" />
                </span>
                <span className="rounded-full bg-slate-100 px-2.5 py-1 font-mono text-xs text-slate-600">
                  {office.slug}
                </span>
              </div>
              <h2 className="mt-5 text-lg font-semibold tracking-tight text-slate-950">
                {office.name}
              </h2>
              <div className="mt-5 grid grid-cols-2 gap-3 border-t border-slate-100 pt-4 text-sm text-slate-600">
                <span className="flex items-center gap-2">
                  <Users className="size-4 text-slate-400" aria-hidden="true" />
                  {memberCount} {memberCount === 1 ? 'member' : 'members'}
                </span>
                <span className="flex items-center gap-2">
                  <Cpu className="size-4 text-slate-400" aria-hidden="true" />
                  {instanceCount} {instanceCount === 1 ? 'instance' : 'instances'}
                </span>
              </div>
            </Link>
          ))}
        </div>
      ) : null}
    </section>
  );
}
