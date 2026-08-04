/**
 * Product version shown in the AppShell sidebar footer (`vMAJOR.MINOR.PATCH`).
 *
 * - MAJOR — product generation (current 4; v4 = implementation waves per
 *   v4-roadmap, after the v3.5.x design-correction docs track)
 * - MINOR — bumps once per completed v4 slice (v4.0 → .0, v4.1 → .1, …)
 * - PATCH — bumps on each small change / hotfix within the current slice
 *
 * Keep in sync with `cocoa-portal/package.json` and `cocoa-backend/pyproject.toml`.
 */
export const APP_VERSION = '4.6.0';
