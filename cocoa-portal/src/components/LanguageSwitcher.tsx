import { Languages } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

export default function LanguageSwitcher() {
  const { i18n, t } = useTranslation();
  const isZh = i18n.language.startsWith('zh');

  function toggleLanguage() {
    void i18n.changeLanguage(isZh ? 'en' : 'zh-CN');
  }

  return (
    <button
      type="button"
      onClick={toggleLanguage}
      aria-label={t('language.label')}
      title={t('language.label')}
      data-testid="language-switcher"
      data-current={isZh ? 'zh-CN' : 'en'}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 transition-colors',
        'hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 active:bg-slate-200',
      )}
    >
      <Languages className="size-3.5" aria-hidden="true" />
      <span>{isZh ? t('language.switchTo') : t('language.current')}</span>
    </button>
  );
}
