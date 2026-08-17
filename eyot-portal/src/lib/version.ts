/**
 * Product version shown in the AppShell sidebar footer (`vMAJOR.MINOR.PATCH`).
 *
 * - MAJOR — product generation (current 0; 0.x = pre-1.0, features not yet
 *   complete; the project reset from 5.x to 0.5.x as part of the Eyot rename)
 * - MINOR — bumps once per completed slice
 * - PATCH — bumps on each small change / hotfix within the current slice
 *
 * Keep in sync with `eyot-portal/package.json` and `eyot-backend/pyproject.toml`.
 */
export const APP_VERSION = '0.5.2.dev2';
