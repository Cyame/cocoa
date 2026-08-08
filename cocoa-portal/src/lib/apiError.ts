import type { TFunction } from 'i18next';
import { ApiError } from '@/lib/api';

/**
 * Resolve a backend error into a user-visible i18n string.
 * Backend returns {error_code, message_key, message}; message_key drives the
 * i18n lookup, and the raw English `message` is the fallback when the key is
 * missing (e.g. untranslated error).
 *
 * @param fallbackKey - i18n key used when error is not an ApiError (default: errors.network)
 */
export function resolveError(
  t: TFunction,
  error: unknown,
  fallbackKey: string = 'errors.network',
): string {
  if (error instanceof ApiError) {
    if (error.messageKey) {
      const translated = t(error.messageKey);
      // i18next returns the key itself when untranslated — fall back to raw message.
      if (translated !== error.messageKey) return translated;
    }
    return error.message;
  }
  if (error instanceof Error && error.message.length > 0) {
    return error.message;
  }
  return t(fallbackKey);
}
