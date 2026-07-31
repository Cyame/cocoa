/**
 * Product version shown in the AppShell sidebar footer (`vMAJOR.MINOR.PATCH`).
 *
 * - MAJOR — product generation (currently 3)
 * - MINOR — bumps once per completed PRD (PRD-v1 → .1, PRD-v2 → .2, PRD-v3 → .3)
 * - PATCH — bumps on each small change / hotfix within the current PRD
 *
 * Keep in sync with `cocoa-portal/package.json` and `cocoa-backend/pyproject.toml`.
 */
export const APP_VERSION = '3.5.4';
