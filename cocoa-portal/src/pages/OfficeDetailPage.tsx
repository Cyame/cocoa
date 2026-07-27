import {
  AlertCircle,
  Building2,
  Cpu,
  LoaderCircle,
  Notebook,
  UserRound,
  Users,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { useParams } from 'react-router';
import { ApiError, api } from '@/lib/api';
import type { Instance, Membership, Office } from '@/lib/types';
import { useSelectedStore } from '@/stores/selected';

type TabId = 'employees' | 'instances' | 'blackboard';

type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly total: number;
};

type Blackboard = {
  readonly id: string;
  readonly office_id: string;
  readonly content: string | null;
  readonly manual_notes: string | null;
  readonly created_at: string;
};

const TABS = [
  { id: 'employees', label: 'Employees', Icon: Users },
  { id: 'instances', label: 'Instances', Icon: Cpu },
  { id: 'blackboard', label: 'Blackboard', Icon: Notebook },
] as const;

export default function OfficeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const setOfficeId = useSelectedStore((state) => state.setOfficeId);
  const [office, setOffice] = useState<Office | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>('employees');
  const [memberships, setMemberships] = useState<readonly Membership[]>([]);
  const [instances, setInstances] = useState<readonly Instance[]>([]);
  const [blackboard, setBlackboard] = useState<Blackboard | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (id === undefined) return;
    setOfficeId(id);
    return () => setOfficeId(null);
  }, [id, setOfficeId]);

  useEffect(() => {
    if (id === undefined) return;
    const officeId = id;
    let isActive = true;

    async function loadTab() {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        if (activeTab === 'employees') {
          const [officeResponse, membershipPage] = await Promise.all([
            office === null ? api<Office>(`/offices/${officeId}`) : Promise.resolve(office),
            api<OffsetPage<Membership>>(
              `/messaging/memberships?office_id=${encodeURIComponent(officeId)}`,
            ),
          ]);
          if (isActive) {
            setOffice(officeResponse);
            setMemberships(membershipPage.items);
          }
        } else if (activeTab === 'instances') {
          const [officeResponse, instancePage] = await Promise.all([
            office === null ? api<Office>(`/offices/${officeId}`) : Promise.resolve(office),
            api<OffsetPage<Instance>>(`/instances?office_id=${encodeURIComponent(officeId)}`),
          ]);
          if (isActive) {
            setOffice(officeResponse);
            setInstances(instancePage.items);
          }
        } else {
          const [officeResponse, blackboardResponse] = await Promise.all([
            office === null ? api<Office>(`/offices/${officeId}`) : Promise.resolve(office),
            api<Blackboard>(`/blackboards?office_id=${encodeURIComponent(officeId)}`),
          ]);
          if (isActive) {
            setOffice(officeResponse);
            setBlackboard(blackboardResponse);
          }
        }
      } catch (error) {
        if (error instanceof ApiError) {
          if (isActive) setErrorMessage(error.message);
          return;
        }
        throw error;
      } finally {
        if (isActive) setIsLoading(false);
      }
    }

    void loadTab();
    return () => {
      isActive = false;
    };
  }, [activeTab, id, office]);

  if (id === undefined) {
    return <p className="p-6 text-sm text-red-700">Office identifier is missing.</p>;
  }

  return (
    <section className="mx-auto w-full max-w-6xl p-6 lg:p-8" aria-labelledby="office-title">
      <header className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="flex items-start gap-4">
          <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-600 text-white">
            <Building2 className="size-6" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="font-mono text-xs text-slate-500">{office?.slug ?? 'Loading office'}</p>
            <h1
              id="office-title"
              className="mt-1 truncate text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl"
            >
              {office?.name ?? 'Office detail'}
            </h1>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Read-only operational view of membership, runtime, and shared state.
            </p>
          </div>
        </div>
      </header>

      <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto border-b border-slate-200">
          <div
            role="tablist"
            aria-label="Office detail sections"
            className="flex min-w-max gap-1 px-3 pt-3"
          >
            {TABS.map(({ id: tabId, label, Icon }) => (
              <button
                key={tabId}
                type="button"
                role="tab"
                id={`tab-${tabId}`}
                aria-selected={activeTab === tabId}
                aria-controls={`panel-${tabId}`}
                onClick={() => setActiveTab(tabId)}
                className={`inline-flex items-center gap-2 rounded-t-lg border-b-2 px-4 py-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                  activeTab === tabId
                    ? 'border-blue-600 bg-blue-50 text-blue-700'
                    : 'border-transparent text-slate-500 hover:bg-slate-50 hover:text-slate-900'
                }`}
              >
                <Icon className="size-4" aria-hidden="true" />
                {label}
              </button>
            ))}
          </div>
        </div>

        <div
          id={`panel-${activeTab}`}
          role="tabpanel"
          aria-labelledby={`tab-${activeTab}`}
          className="min-h-64 p-4 sm:p-6"
        >
          {errorMessage !== null ? (
            <div
              role="alert"
              className="flex gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
            >
              <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <p>{errorMessage}</p>
            </div>
          ) : null}

          {isLoading ? (
            <div className="flex min-h-52 items-center justify-center gap-3 text-sm text-slate-500">
              <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
              Loading {activeTab}
            </div>
          ) : null}

          {!isLoading && errorMessage === null && activeTab === 'employees' ? (
            memberships.length > 0 ? (
              <ul className="grid gap-3 sm:grid-cols-2">
                {memberships.map((membership) => (
                  <li
                    key={membership.id}
                    className="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4"
                  >
                    <span className="grid size-9 shrink-0 place-items-center rounded-full bg-white text-slate-600 shadow-sm">
                      <UserRound className="size-4" aria-hidden="true" />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-slate-900">
                        {membership.user_id ?? membership.instance_id}
                      </p>
                      <p className="mt-1 text-xs capitalize text-slate-500">{membership.role}</p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                Icon={Users}
                title="No employees"
                detail="This office has no active memberships."
              />
            )
          ) : null}

          {!isLoading && errorMessage === null && activeTab === 'instances' ? (
            instances.length > 0 ? (
              <ul className="space-y-3">
                {instances.map((instance) => (
                  <li
                    key={instance.id}
                    className="grid gap-3 rounded-lg border border-slate-200 p-4 sm:grid-cols-[1fr_auto] sm:items-center"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-slate-900">
                        {instance.employee_id}
                      </p>
                      <p className="mt-1 truncate font-mono text-xs text-slate-500">
                        {instance.workspace_path ?? instance.id}
                      </p>
                    </div>
                    <span className="w-fit rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                      {instance.status}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                Icon={Cpu}
                title="No instances"
                detail="No active runtime is assigned to this office."
              />
            )
          ) : null}

          {!isLoading && errorMessage === null && activeTab === 'blackboard' ? (
            blackboard === null ? (
              <EmptyState
                Icon={Notebook}
                title="No blackboard"
                detail="Shared office context has not been initialized."
              />
            ) : (
              <div className="grid gap-4 lg:grid-cols-2">
                <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <h2 className="text-sm font-semibold text-slate-900">Shared context</h2>
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-600">
                    {blackboard.content ?? 'No shared context recorded.'}
                  </p>
                </article>
                <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <h2 className="text-sm font-semibold text-slate-900">Manual notes</h2>
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-600">
                    {blackboard.manual_notes ?? 'No manual notes recorded.'}
                  </p>
                </article>
              </div>
            )
          ) : null}
        </div>
      </div>
    </section>
  );
}

type EmptyStateProps = {
  readonly Icon: typeof Users;
  readonly title: string;
  readonly detail: string;
};

function EmptyState({ Icon, title, detail }: EmptyStateProps) {
  return (
    <div className="grid min-h-52 place-items-center text-center">
      <div>
        <Icon className="mx-auto size-8 text-slate-400" aria-hidden="true" />
        <h2 className="mt-4 text-sm font-semibold text-slate-900">{title}</h2>
        <p className="mt-2 text-sm text-slate-500">{detail}</p>
      </div>
    </div>
  );
}
