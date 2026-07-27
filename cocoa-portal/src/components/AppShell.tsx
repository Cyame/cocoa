import { Bug, Building2, LogOut, Network, Pencil, User } from 'lucide-react';
import { Navigate, NavLink, Outlet, useParams } from 'react-router';
import { cn } from '@/lib/utils';
import { useSelectedStore } from '@/stores/selected';
import { useSessionStore } from '@/stores/session';

const DESKTOP_LINK_CLASS =
  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500';
const MOBILE_LINK_CLASS =
  'flex min-w-0 flex-col items-center gap-1 px-2 py-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500';

export default function AppShell() {
  const token = useSessionStore((state) => state.token);
  const user = useSessionStore((state) => state.user);
  const clearToken = useSessionStore((state) => state.clearToken);
  const selectedOfficeId = useSelectedStore((state) => state.officeId);
  const { id: routeOfficeId } = useParams<{ id: string }>();
  const officeId = routeOfficeId ?? selectedOfficeId;

  if (token === null) {
    return <Navigate to="/login" replace />;
  }

  const navigationItems = [
    {
      label: 'Office list',
      href: '/offices',
      Icon: Building2,
      end: true,
      isDisabled: false,
    },
    {
      label: 'Debug',
      href: '/debug',
      Icon: Bug,
      end: true,
      isDisabled: false,
    },
    {
      label: 'Topology',
      href: officeId === null ? '/offices' : `/offices/${officeId}/topology`,
      Icon: Network,
      end: true,
      isDisabled: officeId === null,
    },
    {
      label: 'Composer',
      href: officeId === null ? '/offices' : `/offices/${officeId}/composer`,
      Icon: Pencil,
      end: true,
      isDisabled: officeId === null,
    },
  ] as const;

  return (
    <div className="flex min-h-dvh bg-slate-100 text-slate-950 md:h-dvh md:overflow-hidden">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-800 bg-slate-950 text-slate-100 md:flex">
        <div className="flex h-16 items-center gap-3 border-b border-slate-800 px-5">
          <span className="grid size-9 place-items-center rounded-lg bg-blue-600 text-white">
            <Building2 className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold tracking-tight">Cocoa</p>
            <p className="truncate text-xs text-slate-400">Control studio</p>
          </div>
        </div>

        <nav className="flex flex-1 flex-col gap-1 p-3" aria-label="Primary navigation">
          {navigationItems.map(({ label, href, Icon, end, isDisabled }) => (
            <NavLink
              key={label}
              to={href}
              end={end}
              aria-disabled={isDisabled}
              tabIndex={isDisabled ? -1 : undefined}
              onClick={(event) => {
                if (isDisabled) event.preventDefault();
              }}
              className={({ isActive }) =>
                cn(
                  DESKTOP_LINK_CLASS,
                  isActive && !isDisabled
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white',
                  isDisabled && 'cursor-not-allowed opacity-40 hover:bg-transparent',
                )
              }
            >
              <Icon className="size-4 shrink-0" aria-hidden="true" />
              <span className="truncate">{label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col md:min-h-0">
        <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-slate-200 bg-white px-4 sm:px-6">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-900">Operator console</p>
            <p className="truncate text-xs text-slate-500">Cocoa portal</p>
          </div>

          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            <div className="flex min-w-0 items-center gap-2">
              <span className="grid size-8 shrink-0 place-items-center rounded-full bg-slate-100 text-slate-600">
                <User className="size-4" aria-hidden="true" />
              </span>
              <div className="hidden min-w-0 sm:block">
                <p className="max-w-48 truncate text-sm font-medium text-slate-800">
                  {user?.user_id ?? 'Authenticated user'}
                </p>
                <p className="text-xs text-slate-500">
                  {user?.is_super_admin === true ? 'Super admin' : 'Operator'}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={clearToken}
              className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 active:bg-slate-200"
              aria-label="Log out"
              title="Log out"
            >
              <LogOut className="size-4" aria-hidden="true" />
            </button>
          </div>
        </header>

        <nav
          className="grid shrink-0 grid-cols-4 border-b border-slate-200 bg-white md:hidden"
          aria-label="Primary navigation"
        >
          {navigationItems.map(({ label, href, Icon, end, isDisabled }) => (
            <NavLink
              key={label}
              to={href}
              end={end}
              aria-disabled={isDisabled}
              tabIndex={isDisabled ? -1 : undefined}
              onClick={(event) => {
                if (isDisabled) event.preventDefault();
              }}
              className={({ isActive }) =>
                cn(
                  MOBILE_LINK_CLASS,
                  isActive && !isDisabled
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900',
                  isDisabled && 'cursor-not-allowed opacity-40 hover:bg-transparent',
                )
              }
            >
              <Icon className="size-4" aria-hidden="true" />
              <span className="w-full truncate text-center">{label}</span>
            </NavLink>
          ))}
        </nav>

        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
