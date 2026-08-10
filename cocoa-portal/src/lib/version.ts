/**
 * Product version shown in the AppShell sidebar footer (`vMAJOR.MINOR.PATCH`).
 *
 * - MAJOR — product generation (current 5; v5 = naming → definition → UIUX →
 *   visual waves per v5-roadmap)
 * - MINOR — bumps once per completed v5 slice (v5.0 → .0, v5.1 → .1, …)
 * - PATCH — bumps on each small change / hotfix within the current slice
 *
 * Keep in sync with `cocoa-portal/package.json` and `cocoa-backend/pyproject.toml`.
 */
export const APP_VERSION = '5.2.1';
