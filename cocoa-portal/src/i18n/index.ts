import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './locales/en.json';
import zhCN from './locales/zh-CN.json';

const STORAGE_KEY = 'cocoa.locale';

function detectInitialLanguage(): string {
  if (typeof window === 'undefined') return 'en';
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === 'zh-CN' || stored === 'en') return stored;
  const nav = window.navigator.language.toLowerCase();
  if (nav.startsWith('zh')) return 'zh-CN';
  return 'en';
}

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    'zh-CN': { translation: zhCN },
  },
  lng: detectInitialLanguage(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
  returnNull: false,
});

if (typeof window !== 'undefined') {
  i18n.on('languageChanged', (lng) => {
    window.localStorage.setItem(STORAGE_KEY, lng);
    document.documentElement.lang = lng;
  });
  document.documentElement.lang = i18n.language;
}

export default i18n;
