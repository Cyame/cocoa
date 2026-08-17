import { Hammer } from 'lucide-react';
import { useTranslation } from 'react-i18next';

type PagePlaceholderProps = {
  /**
   * i18n key of the route's page name (nav.* or equivalent). The visual is a
   * temporary skeleton — PB-B replaces these mounted placeholder routes with
   * real page content.
   */
  readonly titleKey: string;
};

/**
 * Skeleton mount for canonical routes whose page CONTENT is migrated by a
 * sibling wave (PB-B). Keeps the route table stable and tsc green.
 */
export default function PagePlaceholder({ titleKey }: PagePlaceholderProps) {
  const { t } = useTranslation();
  const title = t(titleKey);

  return (
    <section
      className="flex min-h-full flex-col items-center justify-center gap-3 p-10 text-center"
      aria-label={title}
    >
      <span className="grid size-11 place-items-center rounded-xl bg-slate-100 text-slate-400">
        <Hammer className="size-5" aria-hidden="true" />
      </span>
      <div>
        <p className="text-sm font-semibold text-slate-500">{title}</p>
        <p className="mt-1 text-xs text-slate-400">{t('nav.pending')}</p>
      </div>
    </section>
  );
}
