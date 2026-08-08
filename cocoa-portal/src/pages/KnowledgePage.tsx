import { AlertCircle, BookOpen, LoaderCircle, Pencil, Plus, Tag, Trash2, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';
import {
  createKnowledgeDimension,
  createKnowledgeEntry,
  deleteKnowledgeEntry,
  fetchKnowledgeDimensions,
  fetchKnowledgeEntries,
  type KnowledgeDimension,
  type KnowledgeEntry,
  type KnowledgeEntryScope,
  updateKnowledgeEntry,
} from '@/lib/api/knowledge';
import { fetchNamespaces } from '@/lib/api/namespaces';
import { fetchOrganization } from '@/lib/api/organizations';
import { fetchWorkspaces } from '@/lib/api/workspaces';
import { resolveError } from '@/lib/apiError';
import type { Namespace, Workspace } from '@/lib/types';

type TFn = ReturnType<typeof useTranslation>['t'];

const SCOPES: readonly KnowledgeEntryScope[] = ['system', 'org', 'namespace', 'workspace'];

const SCOPE_FALLBACK_LABELS: Record<KnowledgeEntryScope, string> = {
  system: '系统',
  org: '组织',
  namespace: '命名空间',
  workspace: '工作区',
};

const SCOPE_BADGE_CLASS: Record<KnowledgeEntryScope, string> = {
  system: 'bg-purple-50 text-purple-700',
  org: 'bg-blue-50 text-blue-700',
  namespace: 'bg-teal-50 text-teal-700',
  workspace: 'bg-amber-50 text-amber-700',
};

function scopeLabel(t: TFn, scope: KnowledgeEntryScope): string {
  return t(`knowledge.scope.${scope}`, { defaultValue: SCOPE_FALLBACK_LABELS[scope] });
}

function scopeBindingMissing(
  scope: KnowledgeEntryScope,
  orgId: string,
  nsId: string,
  wsId: string,
): boolean {
  if (scope === 'system') return false;
  if (scope === 'org') return orgId === '';
  if (scope === 'namespace') return orgId === '' || nsId === '';
  return orgId === '' || nsId === '' || wsId === '';
}

function entryBindingLabel(
  entry: KnowledgeEntry,
  orgName: string | null,
  namespaceById: ReadonlyMap<string, Namespace>,
  workspaceById: ReadonlyMap<string, Workspace>,
): string | null {
  if (entry.scope === 'system') return null;
  if (entry.scope === 'org') return orgName ?? entry.organization_id;
  const ns = entry.namespace_id !== null ? namespaceById.get(entry.namespace_id) : undefined;
  if (entry.scope === 'namespace') return ns?.name ?? entry.namespace_id;
  const ws = entry.workspace_id !== null ? workspaceById.get(entry.workspace_id) : undefined;
  const nsLabel = ns?.name ?? entry.namespace_id;
  const wsLabel = ws?.name ?? entry.workspace_id;
  return `${nsLabel} / ${wsLabel}`;
}

export default function KnowledgePage() {
  const { t } = useTranslation();
  const { orgId } = useParams<{ orgId: string }>();

  const [orgName, setOrgName] = useState<string | null>(null);
  const [entries, setEntries] = useState<readonly KnowledgeEntry[]>([]);
  const [dimensions, setDimensions] = useState<readonly KnowledgeDimension[]>([]);
  const [namespaces, setNamespaces] = useState<readonly Namespace[]>([]);
  const [workspaces, setWorkspaces] = useState<readonly Workspace[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<KnowledgeEntry | null>(null);
  const [formKey, setFormKey] = useState('');
  const [formTitle, setFormTitle] = useState('');
  const [formBody, setFormBody] = useState('');
  const [formScope, setFormScope] = useState<KnowledgeEntryScope>('org');
  const [formOrgId, setFormOrgId] = useState('');
  const [formNsId, setFormNsId] = useState('');
  const [formWsId, setFormWsId] = useState('');
  const [formDimensionId, setFormDimensionId] = useState('');
  const [formBusy, setFormBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<KnowledgeEntry | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const [dimCreateOpen, setDimCreateOpen] = useState(false);
  const [dimName, setDimName] = useState('');
  const [dimSlug, setDimSlug] = useState('');
  const [dimDescription, setDimDescription] = useState('');
  const [dimBusy, setDimBusy] = useState(false);
  const [dimError, setDimError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (orgId === undefined) return;
    setIsLoading(true);
    setError(null);
    try {
      // fetchNamespaces / fetchWorkspaces rely on the X-Organization-Id header
      // injected by the API layer, so namespace/workspace bindings resolve to
      // names within the current org context.
      const [entryPage, dimensionPage, orgData, nsPage, wsPage] = await Promise.all([
        fetchKnowledgeEntries(),
        fetchKnowledgeDimensions(),
        fetchOrganization(orgId),
        fetchNamespaces(),
        fetchWorkspaces({ limit: 200 }),
      ]);
      setEntries(entryPage.items);
      setDimensions(dimensionPage.items);
      setOrgName(orgData.name);
      setNamespaces(nsPage.items);
      setWorkspaces(wsPage.items);
    } catch (loadError) {
      setError(resolveError(t, loadError));
    } finally {
      setIsLoading(false);
    }
  }, [orgId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (orgId === undefined) {
    return null;
  }

  const namespaceById = new Map(namespaces.map((ns) => [ns.id, ns]));
  const workspaceById = new Map(workspaces.map((ws) => [ws.id, ws]));
  const dimensionById = new Map(dimensions.map((dim) => [dim.id, dim]));

  const openCreate = () => {
    setEditing(null);
    setFormKey('');
    setFormTitle('');
    setFormBody('');
    setFormScope('org');
    setFormOrgId(orgId);
    setFormNsId('');
    setFormWsId('');
    setFormDimensionId('');
    setFormError(null);
    setFormOpen(true);
  };

  const openEdit = (entry: KnowledgeEntry) => {
    setEditing(entry);
    setFormKey(entry.key);
    setFormTitle(entry.title);
    setFormBody(entry.body);
    setFormScope(entry.scope);
    setFormOrgId(entry.organization_id ?? '');
    setFormNsId(entry.namespace_id ?? '');
    setFormWsId(entry.workspace_id ?? '');
    setFormDimensionId(entry.dimension_id ?? '');
    setFormError(null);
    setFormOpen(true);
  };

  const closeForm = () => {
    setFormOpen(false);
    setEditing(null);
    setFormBusy(false);
  };

  const bindingMissing = scopeBindingMissing(formScope, formOrgId, formNsId, formWsId);
  const canSubmit =
    !formBusy && !bindingMissing && formKey.trim() !== '' && formTitle.trim() !== '';

  const handleScopeChange = (scope: KnowledgeEntryScope) => {
    setFormScope(scope);
    setFormNsId('');
    setFormWsId('');
  };

  const handleSubmit = async () => {
    const key = formKey.trim().toLowerCase();
    if (key.length === 0) {
      setFormError(t('knowledge.form.keyRequired', { defaultValue: 'Key 不能为空' }));
      return;
    }
    if (formTitle.trim().length === 0) {
      setFormError(t('knowledge.form.titleRequired', { defaultValue: '标题不能为空' }));
      return;
    }
    if (bindingMissing) {
      setFormError(t('knowledge.form.bindingRequired', { defaultValue: '请补全作用域绑定字段' }));
      return;
    }
    setFormBusy(true);
    setFormError(null);
    try {
      if (editing !== null) {
        await updateKnowledgeEntry(editing.id, {
          key,
          title: formTitle.trim(),
          body: formBody,
          dimension_id: formDimensionId === '' ? null : formDimensionId,
        });
      } else {
        await createKnowledgeEntry({
          key,
          title: formTitle.trim(),
          body: formBody,
          dimension_id: formDimensionId === '' ? null : formDimensionId,
          scope: formScope,
          organization_id: formScope === 'system' ? null : formOrgId,
          namespace_id: formScope === 'system' || formScope === 'org' ? null : formNsId,
          workspace_id: formScope === 'workspace' ? formWsId : null,
        });
      }
      closeForm();
      await load();
    } catch (submitError) {
      setFormError(resolveError(t, submitError));
      setFormBusy(false);
    }
  };

  const handleDelete = async () => {
    if (deleteTarget === null) return;
    setDeleteBusy(true);
    try {
      await deleteKnowledgeEntry(deleteTarget.id);
      setDeleteTarget(null);
      await load();
    } catch (deleteError) {
      setError(resolveError(t, deleteError));
    } finally {
      setDeleteBusy(false);
    }
  };

  const handleCreateDimension = async () => {
    const name = dimName.trim();
    if (name.length === 0) {
      setDimError(t('knowledge.dimensions.nameRequired', { defaultValue: '维度名称不能为空' }));
      return;
    }
    setDimBusy(true);
    setDimError(null);
    try {
      await createKnowledgeDimension({
        name,
        slug: dimSlug.trim().toLowerCase() || null,
        description: dimDescription.trim() || null,
        scope: 'org',
        organization_id: orgId,
      });
      setDimName('');
      setDimSlug('');
      setDimDescription('');
      setDimCreateOpen(false);
      await load();
    } catch (createError) {
      setDimError(resolveError(t, createError));
    } finally {
      setDimBusy(false);
    }
  };

  return (
    <section className="mx-auto w-full max-w-6xl p-6 lg:p-8" aria-labelledby="knowledge-title">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-4">
          <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
            <BookOpen className="size-6" aria-hidden="true" />
          </span>
          <div>
            <h1
              id="knowledge-title"
              className="text-2xl font-semibold tracking-tight text-slate-950"
            >
              {t('knowledge.title', { defaultValue: '知识管理' })}
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-slate-600">
              {t('knowledge.subtitle', {
                defaultValue: '管理注入到 Agent 提示词脚手架中的知识条目与维度。',
              })}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500"
          data-testid="knowledge-create-entry"
        >
          <Plus className="size-4" aria-hidden="true" />
          {t('knowledge.createEntry', { defaultValue: '新建知识' })}
        </button>
      </header>

      {error !== null ? (
        <div
          role="alert"
          className="mb-6 flex gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p className="flex-1">{error}</p>
          <button
            type="button"
            onClick={() => void load()}
            className="rounded-md px-2 py-0.5 text-xs font-semibold text-red-700 hover:bg-red-100"
          >
            {t('common.retry')}
          </button>
        </div>
      ) : null}

      {formOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="knowledge-form-title"
          className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
          data-testid="knowledge-entry-form"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 id="knowledge-form-title" className="text-base font-semibold text-slate-950">
                {editing !== null
                  ? t('knowledge.editEntry', { defaultValue: '编辑知识' })
                  : t('knowledge.createEntry', { defaultValue: '新建知识' })}
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                {t('knowledge.form.scopeHelp', {
                  defaultValue: '作用域决定注入优先级：workspace > namespace > org > system。',
                })}
              </p>
            </div>
            <button
              type="button"
              onClick={closeForm}
              className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              aria-label={t('knowledge.form.cancel', { defaultValue: '取消' })}
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">
                {t('knowledge.form.key', { defaultValue: 'Key' })}
              </span>
              <input
                value={formKey}
                onChange={(event) => setFormKey(event.target.value.toLowerCase())}
                placeholder={t('knowledge.form.keyPlaceholder', {
                  defaultValue: '例如 cocoa.collab.passage',
                })}
                aria-label={t('knowledge.form.key', { defaultValue: 'Key' })}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              />
              <span className="mt-1 block text-xs text-slate-400">
                {t('knowledge.form.keyLowercaseHint', { defaultValue: '自动转为小写' })}
              </span>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">
                {t('knowledge.form.title', { defaultValue: '标题' })}
              </span>
              <input
                value={formTitle}
                onChange={(event) => setFormTitle(event.target.value)}
                aria-label={t('knowledge.form.title', { defaultValue: '标题' })}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              />
            </label>
          </div>

          <label className="mt-3 block text-sm">
            <span className="mb-1 block font-medium text-slate-700">
              {t('knowledge.form.body', { defaultValue: '内容' })}
            </span>
            <textarea
              value={formBody}
              onChange={(event) => setFormBody(event.target.value)}
              rows={5}
              aria-label={t('knowledge.form.body', { defaultValue: '内容' })}
              className="w-full resize-y rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
            />
          </label>

          {editing === null ? (
            <>
              <label className="mt-3 block text-sm">
                <span className="mb-1 block font-medium text-slate-700">
                  {t('knowledge.form.scope', { defaultValue: '作用域' })}
                </span>
                <select
                  value={formScope}
                  onChange={(event) => handleScopeChange(event.target.value as KnowledgeEntryScope)}
                  aria-label={t('knowledge.form.scope', { defaultValue: '作用域' })}
                  data-testid="knowledge-scope-select"
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                >
                  {SCOPES.map((scope) => (
                    <option key={scope} value={scope}>
                      {scopeLabel(t, scope)}
                    </option>
                  ))}
                </select>
              </label>

              {formScope !== 'system' ? (
                <div className="mt-3 grid gap-3 sm:grid-cols-3">
                  <label className="block text-sm">
                    <span className="mb-1 block font-medium text-slate-700">
                      {t('knowledge.form.organization', { defaultValue: '组织' })}
                    </span>
                    <select
                      value={formOrgId}
                      onChange={(event) => setFormOrgId(event.target.value)}
                      aria-label={t('knowledge.form.organization', { defaultValue: '组织' })}
                      data-testid="knowledge-org-select"
                      className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                    >
                      <option value="">—</option>
                      <option value={orgId}>{orgName ?? orgId}</option>
                    </select>
                  </label>
                  {formScope === 'namespace' || formScope === 'workspace' ? (
                    <label className="block text-sm">
                      <span className="mb-1 block font-medium text-slate-700">
                        {t('knowledge.form.namespace', { defaultValue: '命名空间' })}
                      </span>
                      <select
                        value={formNsId}
                        onChange={(event) => {
                          setFormNsId(event.target.value);
                          setFormWsId('');
                        }}
                        aria-label={t('knowledge.form.namespace', { defaultValue: '命名空间' })}
                        data-testid="knowledge-namespace-select"
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                      >
                        <option value="">—</option>
                        {namespaces.map((ns) => (
                          <option key={ns.id} value={ns.id}>
                            {ns.name}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : null}
                  {formScope === 'workspace' ? (
                    <label className="block text-sm">
                      <span className="mb-1 block font-medium text-slate-700">
                        {t('knowledge.form.workspace', { defaultValue: '工作区' })}
                      </span>
                      <select
                        value={formWsId}
                        onChange={(event) => setFormWsId(event.target.value)}
                        aria-label={t('knowledge.form.workspace', { defaultValue: '工作区' })}
                        data-testid="knowledge-workspace-select"
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                      >
                        <option value="">—</option>
                        {workspaces
                          .filter((ws) => ws.namespace_id === formNsId)
                          .map((ws) => (
                            <option key={ws.id} value={ws.id}>
                              {ws.name}
                            </option>
                          ))}
                      </select>
                    </label>
                  ) : null}
                </div>
              ) : null}
            </>
          ) : (
            <p className="mt-3 text-sm text-slate-500">
              <span
                className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${SCOPE_BADGE_CLASS[editing.scope]}`}
              >
                {scopeLabel(t, editing.scope)}
              </span>
              <span className="ml-2">{editing.organization_id ?? ''}</span>
            </p>
          )}

          <label className="mt-3 block text-sm">
            <span className="mb-1 block font-medium text-slate-700">
              {t('knowledge.form.dimension', { defaultValue: '维度（可选）' })}
            </span>
            <select
              value={formDimensionId}
              onChange={(event) => setFormDimensionId(event.target.value)}
              aria-label={t('knowledge.form.dimension', { defaultValue: '维度（可选）' })}
              data-testid="knowledge-dimension-select"
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
            >
              <option value="">
                {t('knowledge.form.noDimension', { defaultValue: '无维度' })}
              </option>
              {dimensions.map((dim) => (
                <option key={dim.id} value={dim.id}>
                  {dim.name}
                </option>
              ))}
            </select>
          </label>

          {formError !== null ? (
            <p role="alert" className="mt-3 text-sm text-red-600">
              {formError}
            </p>
          ) : null}

          <div className="mt-4 flex justify-end gap-2">
            <button
              type="button"
              onClick={closeForm}
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              {t('knowledge.form.cancel', { defaultValue: '取消' })}
            </button>
            <button
              type="button"
              disabled={!canSubmit}
              onClick={() => void handleSubmit()}
              data-testid="knowledge-form-submit"
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
            >
              {formBusy
                ? t('knowledge.form.busy', { defaultValue: '保存中…' })
                : t('knowledge.form.submit', { defaultValue: '保存' })}
            </button>
          </div>
        </div>
      ) : null}

      {isLoading ? (
        <div className="flex items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white px-6 py-16 text-sm text-slate-500">
          <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
          {t('common.loading')}
        </div>
      ) : null}

      {!isLoading && entries.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
          <BookOpen className="mx-auto size-8 text-slate-400" aria-hidden="true" />
          <h2 className="mt-4 text-base font-semibold text-slate-900">
            {t('knowledge.emptyTitle', { defaultValue: '暂无知识条目' })}
          </h2>
          <p className="mt-2 text-sm text-slate-500">
            {t('knowledge.emptyDetail', {
              defaultValue: '创建第一条知识，它将被注入到 Agent 的提示词脚手架中。',
            })}
          </p>
        </div>
      ) : null}

      {!isLoading && entries.length > 0 ? (
        <EntryTable
          entries={entries}
          dimensionById={dimensionById}
          namespaceById={namespaceById}
          workspaceById={workspaceById}
          orgName={orgName}
          deleteTarget={deleteTarget}
          deleteBusy={deleteBusy}
          onEdit={openEdit}
          onRequestDelete={setDeleteTarget}
          onConfirmDelete={() => void handleDelete()}
          onCancelDelete={() => setDeleteTarget(null)}
          t={t}
        />
      ) : null}

      <div className="mt-10">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">
              {t('knowledge.dimensions.title', { defaultValue: '维度管理' })}
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              {t('knowledge.dimensions.subtitle', {
                defaultValue: '维度用于给知识条目分组，方便按维度检索。',
              })}
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              setDimCreateOpen((open) => !open);
              setDimError(null);
            }}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <Plus className="size-4" aria-hidden="true" />
            {t('knowledge.dimensions.create', { defaultValue: '新建维度' })}
          </button>
        </div>

        {dimCreateOpen ? (
          <div className="mt-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="block text-sm">
                <span className="mb-1 block font-medium text-slate-700">
                  {t('knowledge.dimensions.name', { defaultValue: '名称' })}
                </span>
                <input
                  value={dimName}
                  onChange={(event) => setDimName(event.target.value)}
                  aria-label={t('knowledge.dimensions.name', { defaultValue: '名称' })}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block font-medium text-slate-700">
                  {t('knowledge.dimensions.slug', { defaultValue: 'Slug（可选）' })}
                </span>
                <input
                  value={dimSlug}
                  onChange={(event) => setDimSlug(event.target.value.toLowerCase())}
                  aria-label={t('knowledge.dimensions.slug', { defaultValue: 'Slug（可选）' })}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block font-medium text-slate-700">
                  {t('knowledge.dimensions.description', { defaultValue: '描述（可选）' })}
                </span>
                <input
                  value={dimDescription}
                  onChange={(event) => setDimDescription(event.target.value)}
                  aria-label={t('knowledge.dimensions.description', {
                    defaultValue: '描述（可选）',
                  })}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                />
              </label>
            </div>
            {dimError !== null ? (
              <p role="alert" className="mt-3 text-sm text-red-600">
                {dimError}
              </p>
            ) : null}
            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setDimCreateOpen(false);
                  setDimError(null);
                }}
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                {t('knowledge.form.cancel', { defaultValue: '取消' })}
              </button>
              <button
                type="button"
                disabled={dimBusy}
                onClick={() => void handleCreateDimension()}
                data-testid="knowledge-dimension-submit"
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
              >
                {dimBusy
                  ? t('knowledge.dimensions.busy', { defaultValue: '保存中…' })
                  : t('knowledge.dimensions.submit', { defaultValue: '保存' })}
              </button>
            </div>
          </div>
        ) : null}

        {dimensions.length === 0 ? (
          <p className="mt-3 rounded-xl border border-dashed border-slate-300 bg-white px-4 py-8 text-center text-sm text-slate-500">
            {t('knowledge.dimensions.empty', { defaultValue: '暂无维度' })}
          </p>
        ) : (
          <ul className="mt-3 divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200 bg-white">
            {dimensions.map((dim) => (
              <li key={dim.id} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="flex min-w-0 items-center gap-3">
                  <Tag className="size-4 shrink-0 text-slate-400" aria-hidden="true" />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-900">{dim.name}</p>
                    <p className="truncate font-mono text-xs text-slate-400">{dim.slug}</p>
                  </div>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${SCOPE_BADGE_CLASS[dim.scope]}`}
                >
                  {scopeLabel(t, dim.scope)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function EntryTable({
  entries,
  dimensionById,
  namespaceById,
  workspaceById,
  orgName,
  deleteTarget,
  deleteBusy,
  onEdit,
  onRequestDelete,
  onConfirmDelete,
  onCancelDelete,
  t,
}: {
  readonly entries: readonly KnowledgeEntry[];
  readonly dimensionById: ReadonlyMap<string, KnowledgeDimension>;
  readonly namespaceById: ReadonlyMap<string, Namespace>;
  readonly workspaceById: ReadonlyMap<string, Workspace>;
  readonly orgName: string | null;
  readonly deleteTarget: KnowledgeEntry | null;
  readonly deleteBusy: boolean;
  readonly onEdit: (entry: KnowledgeEntry) => void;
  readonly onRequestDelete: (entry: KnowledgeEntry) => void;
  readonly onConfirmDelete: () => void;
  readonly onCancelDelete: () => void;
  readonly t: TFn;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <table className="min-w-full text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3">{t('knowledge.columns.key', { defaultValue: 'Key' })}</th>
            <th className="px-4 py-3">{t('knowledge.columns.title', { defaultValue: '标题' })}</th>
            <th className="px-4 py-3">
              {t('knowledge.columns.scope', { defaultValue: '作用域' })}
            </th>
            <th className="px-4 py-3">
              {t('knowledge.columns.binding', { defaultValue: '绑定' })}
            </th>
            <th className="px-4 py-3">
              {t('knowledge.columns.dimension', { defaultValue: '维度' })}
            </th>
            <th className="px-4 py-3">
              {t('knowledge.columns.createdAt', { defaultValue: '创建时间' })}
            </th>
            <th className="px-4 py-3">
              {t('knowledge.columns.actions', { defaultValue: '操作' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => {
            const binding = entryBindingLabel(entry, orgName, namespaceById, workspaceById);
            const dimension = dimensionById.get(entry.dimension_id ?? '');
            const isDeleting = deleteTarget?.id === entry.id;
            return (
              <tr key={entry.id} className="border-b border-slate-100 last:border-0">
                <td className="px-4 py-3 font-mono text-xs font-medium text-slate-900">
                  {entry.key}
                </td>
                <td className="max-w-[12rem] px-4 py-3">
                  <p className="truncate font-medium text-slate-900">{entry.title}</p>
                  <p className="line-clamp-2 text-xs text-slate-500">{entry.body}</p>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${SCOPE_BADGE_CLASS[entry.scope]}`}
                  >
                    {scopeLabel(t, entry.scope)}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-600">{binding ?? '—'}</td>
                <td className="px-4 py-3 text-slate-600">{dimension?.name ?? '—'}</td>
                <td className="px-4 py-3 text-slate-500">
                  {new Date(entry.created_at).toLocaleString()}
                </td>
                <td className="px-4 py-3">
                  {entry.scope === 'system' ? (
                    <span className="text-xs text-slate-400">
                      {t('knowledge.actions.readonly', { defaultValue: '只读' })}
                    </span>
                  ) : isDeleting ? (
                    <span className="flex items-center gap-2">
                      <span className="text-xs text-slate-600">
                        {t('knowledge.delete.confirmText', {
                          key: entry.key,
                          defaultValue: '确认删除 {{key}}？',
                        })}
                      </span>
                      <button
                        type="button"
                        disabled={deleteBusy}
                        onClick={onConfirmDelete}
                        data-testid={`knowledge-delete-confirm-${entry.id}`}
                        className="rounded-md bg-red-600 px-2 py-1 text-xs font-semibold text-white hover:bg-red-500 disabled:opacity-60"
                      >
                        {t('knowledge.delete.confirm', { defaultValue: '删除' })}
                      </button>
                      <button
                        type="button"
                        onClick={onCancelDelete}
                        className="rounded-md border border-slate-200 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                      >
                        {t('knowledge.delete.cancel', { defaultValue: '取消' })}
                      </button>
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => onEdit(entry)}
                        data-testid={`knowledge-edit-${entry.id}`}
                        className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700"
                      >
                        <Pencil className="size-3.5" aria-hidden="true" />
                        {t('knowledge.actions.edit', { defaultValue: '编辑' })}
                      </button>
                      <button
                        type="button"
                        onClick={() => onRequestDelete(entry)}
                        data-testid={`knowledge-delete-${entry.id}`}
                        className="inline-flex items-center gap-1 text-red-600 hover:text-red-700"
                      >
                        <Trash2 className="size-3.5" aria-hidden="true" />
                        {t('knowledge.actions.delete', { defaultValue: '删除' })}
                      </button>
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
