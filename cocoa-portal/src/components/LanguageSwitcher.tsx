import { Check, ChevronUp, Languages } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

const LOCALES = [
  { id: 'zh-CN', labelKey: 'language.zh' },
  { id: 'en', labelKey: 'language.en' },
] as const;

type LocaleId = (typeof LOCALES)[number]['id'];

type LanguageSwitcherProps = {
  /** Match left navigator (dark) or light surfaces (login header / IDE chrome). */
  readonly variant?: 'sidebar' | 'surface';
  /** Footer sits at the bottom of the nav — open upward by default. */
  readonly placement?: 'up' | 'down';
};

function resolveLocale(language: string): LocaleId {
  return language.startsWith('zh') ? 'zh-CN' : 'en';
}

export default function LanguageSwitcher({
  variant = 'sidebar',
  placement = 'up',
}: LanguageSwitcherProps) {
  const { i18n, t } = useTranslation();
  const current = resolveLocale(i18n.language);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  useEffect(() => {
    if (!open) return;
    function onDocPointer(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDocPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  function selectLocale(next: LocaleId) {
    if (next !== current) {
      void i18n.changeLanguage(next);
    }
    setOpen(false);
  }

  const currentLabel = t(LOCALES.find((l) => l.id === current)?.labelKey ?? 'language.zh');

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-label={t('language.label')}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        title={t('language.label')}
        data-testid="language-switcher"
        data-current={current}
        className={cn(
          'inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500',
          variant === 'sidebar'
            ? 'text-slate-300 hover:bg-slate-800 hover:text-white'
            : 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-100 hover:text-slate-900',
        )}
      >
        <Languages className="size-4 shrink-0" aria-hidden="true" />
        <span>{currentLabel}</span>
        <ChevronUp
          className={cn(
            'size-3.5 shrink-0 opacity-70 transition-transform',
            placement === 'up' ? (open ? 'rotate-180' : '') : open ? '' : 'rotate-180',
          )}
          aria-hidden="true"
        />
      </button>

      {open ? (
        <ul
          id={listId}
          aria-label={t('language.label')}
          data-testid="language-switcher-menu"
          className={cn(
            'absolute left-0 z-50 min-w-[9rem] overflow-hidden rounded-lg border py-1 shadow-lg',
            placement === 'up' ? 'bottom-full mb-1.5' : 'top-full mt-1.5',
            variant === 'sidebar'
              ? 'border-slate-700 bg-slate-900 text-slate-100'
              : 'border-slate-200 bg-white text-slate-900',
          )}
        >
          {LOCALES.map((locale) => {
            const selected = locale.id === current;
            return (
              <li key={locale.id}>
                <button
                  type="button"
                  data-testid={`language-option-${locale.id}`}
                  aria-current={selected ? 'true' : undefined}
                  onClick={() => selectLocale(locale.id)}
                  className={cn(
                    'flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition-colors',
                    variant === 'sidebar'
                      ? selected
                        ? 'bg-blue-600 text-white'
                        : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                      : selected
                        ? 'bg-blue-50 text-blue-800'
                        : 'text-slate-700 hover:bg-slate-50',
                  )}
                >
                  <span>{t(locale.labelKey)}</span>
                  {selected ? <Check className="size-3.5 shrink-0" aria-hidden="true" /> : null}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
