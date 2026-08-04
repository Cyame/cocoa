import {
  AlertCircle,
  Bot,
  Brain,
  Cpu,
  Link,
  LoaderCircle,
  Network,
  Trash,
  User,
  X,
} from 'lucide-react';
import {
  type ReactElement,
  type MouseEvent as ReactMouseEvent,
  type WheelEvent as ReactWheelEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';
import { ModeToolbar } from '@/components/ModeToolbar';
import { NodeModal } from '@/components/NodeModal';
import { NodeTooltip } from '@/components/NodeTooltip';
import TopologyGlowDefs, {
  GLOW_INTENSITY_OPACITY,
  OutdatedOverlay,
} from '@/components/TopologyGlow';
import { ApiError, api } from '@/lib/api';
import { deleteInstanceById, deleteMembership, deletePassage } from '@/lib/api/instances';
import { fetchTopologyLiveStatus } from '@/lib/api/topology';
import { fitNodes } from '@/lib/topologyFit';
import type {
  Event,
  GlowIntensity,
  LiveStatusItem,
  Membership,
  Passage,
  TopologyNode,
} from '@/lib/types';
import { useComposerDraftStore } from '@/stores/composerDraftStore';
import { useSelectedStore } from '@/stores/selected';
import { useSessionStore } from '@/stores/session';
import { useTabStore } from '@/stores/tabStore';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type PassageEdge = Passage;

type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly total: number;
};

type CursorPage<T> = {
  readonly items: readonly T[];
  readonly next_cursor: string | null;
  readonly total: number | null;
};

type ResolvedEndpoint = {
  readonly id: string;
  readonly x: number;
  readonly y: number;
};

type ResolvedPassage = {
  readonly passage: PassageEdge;
  readonly from: ResolvedEndpoint;
  readonly to: ResolvedEndpoint;
};

type NodeSummary = TopologyNode;

type PendingConnection = {
  readonly id: string;
};

type DragState = {
  readonly id: string;
  readonly originX: number;
  readonly originY: number;
  readonly currentX: number;
  readonly currentY: number;
};

type NodeDragPatchBody = {
  readonly posx: number;
  readonly posy: number;
};

type PassageCreateBody = {
  readonly workspace_id: string;
  readonly from_membership_id: string;
  readonly to_membership_id: string;
};

type TopologyPageProps = {
  readonly embedded?: boolean;
  readonly workspaceId?: string;
  /** Bump to force-reload memberships / passages (e.g. after introduce). */
  readonly refreshKey?: number;
  /** Open the workspace 主脑 tab (hub node click). */
  readonly onOpenBrain?: () => void;
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const VIEW_BOX = '-1000 -1000 2000 2000';
const NODE_RADIUS = 40;
const HALO_RADIUS = 52;
const HALO_STROKE_WIDTH = 8;
const CORE_STROKE_WIDTH = 2;
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 4;
const PARTICLE_DURATION_MS = 1000;
const ACTIVE_STROKE = '#10b981';
const ACTIVE_STROKE_WIDTH = 3;
const DEFAULT_STROKE = '#94a3b8';
const DEFAULT_STROKE_WIDTH = 2;
const LIVE_STATUS_INTERVAL_MS = 5000;
const EVENT_POLL_INTERVAL_MS = 5000;
const EVENT_LOOKBACK_MS = 5000;
const PARTICLE_TICK_MS = 200;
const HUB_NODE_ID = '__central_hub__';
const HUB_FILL = '#0f766e';
const HUB_GLOW = '#14b8a6';
const HUB_SPOKE_STROKE = '#0d9488';

const DEFAULT_USER_FILL = '#e2e8f0';
const DEFAULT_INSTANCE_FILL = '#3b82f6';
const SELECTED_STROKE = '#2563eb';
const SELECTED_STROKE_WIDTH = 3;

function intensityOpacity(intensity: GlowIntensity): number {
  return GLOW_INTENSITY_OPACITY[intensity];
}

function intensityStrokeOpacity(intensity: GlowIntensity): number {
  // Slightly stronger so the inner ring remains visible against the halo
  if (intensity === 'static') return 0.4;
  return Math.min(1, GLOW_INTENSITY_OPACITY[intensity] + 0.2);
}

type TranslateFn = (key: string, options?: { readonly defaultValue?: string }) => string;

function resolveErrorMessage(error: unknown, translate: TranslateFn, fallbackKey: string): string {
  if (error instanceof ApiError) {
    const payload = error.payload;
    if (
      typeof payload === 'object' &&
      payload !== null &&
      'message_key' in payload &&
      typeof (payload as { message_key: unknown }).message_key === 'string'
    ) {
      const key = (payload as { message_key: string }).message_key;
      const translated = translate(key, { defaultValue: '' });
      if (translated.length > 0) return translated;
    }
    return error.message;
  }
  return translate(fallbackKey);
}

function userFillColor(): string {
  return DEFAULT_USER_FILL;
}

function instanceFillColor(): string {
  return DEFAULT_INSTANCE_FILL;
}

// ---------------------------------------------------------------------------
// Data fetch hooks (kept inline to avoid premature module split)
// ---------------------------------------------------------------------------

type TopologyStaticData = {
  readonly memberships: readonly Membership[];
  readonly passages: readonly PassageEdge[];
};

async function fetchStaticData(workspaceId: string): Promise<TopologyStaticData> {
  const [membershipPage, passagePage] = await Promise.all([
    api<OffsetPage<Membership>>(
      `/messaging/memberships?workspace_id=${encodeURIComponent(workspaceId)}`,
    ),
    api<OffsetPage<PassageEdge>>(
      `/messaging/passages?workspace_id=${encodeURIComponent(workspaceId)}`,
    ),
  ]);
  return {
    memberships: membershipPage.items,
    passages: passagePage.items,
  };
}

// ---------------------------------------------------------------------------
// TopologyPage
// ---------------------------------------------------------------------------

export default function TopologyPage({
  embedded = false,
  workspaceId: workspaceIdProp,
  refreshKey = 0,
  onOpenBrain,
}: TopologyPageProps = {}) {
  const { id: routeWorkspaceId } = useParams<{ id: string }>();
  const setWorkspaceId = useSelectedStore((state) => state.setWorkspaceId);
  const interactionMode = useSelectedStore((state) => state.interactionMode);
  const addTab = useTabStore((state) => state.addTab);
  const setComposerDraft = useComposerDraftStore((state) => state.setDraft);
  const currentUserId = useSessionStore((state) => state.user?.user_id ?? null);
  const [staticData, setStaticData] = useState<TopologyStaticData | null>(null);
  const [liveStatus, setLiveStatus] = useState<readonly LiveStatusItem[]>([]);
  const [activePassages, setActivePassages] = useState<ReadonlyMap<string, number>>(
    () => new Map(),
  );
  const [isStaticLoading, setIsStaticLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Hook order matters — useTranslation must be called at component scope,
  // before any async callbacks or conditional branches.
  const { t } = useTranslation();

  // ---- Interaction state (Todo 9) ----
  const [selectedNode, setSelectedNode] = useState<NodeSummary | null>(null);
  const [selectedPassage, setSelectedPassage] = useState<PassageEdge | null>(null);
  const [pendingConnection, setPendingConnection] = useState<PendingConnection | null>(null);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // ---- Viewport state (pan / zoom) ----
  const [panX, setPanX] = useState(0);
  const [panY, setPanY] = useState(0);
  const [zoom, setZoom] = useState(1);

  // Refs used during drag to avoid React re-render storm on each mousemove.
  const isDraggingRef = useRef(false);
  const lastPointerRef = useRef<{ x: number; y: number } | null>(null);
  const panXRef = useRef(0);
  const panYRef = useRef(0);
  const svgRef = useRef<SVGSVGElement | null>(null);

  // Latest delete handler for the global keydown listener (Delete / Backspace),
  // mirrored so the listener never re-subscribes when the selection changes.
  const deleteSelectionRef = useRef<() => void>(() => {});

  // Mirror panX/panY into refs so the pointer handlers always read the
  // latest committed value without depending on the React state version.
  useEffect(() => {
    panXRef.current = panX;
  }, [panX]);
  useEffect(() => {
    panYRef.current = panY;
  }, [panY]);

  // Mirror zoom similarly so wheel handler clamps correctly.
  const zoomRef = useRef(1);
  useEffect(() => {
    zoomRef.current = zoom;
  }, [zoom]);

  const workspaceId = workspaceIdProp ?? routeWorkspaceId ?? null;

  useEffect(() => {
    if (workspaceId === null) return;
    setWorkspaceId(workspaceId);
    return () => setWorkspaceId(null);
  }, [workspaceId, setWorkspaceId]);

  // ---- Initial topology load ----
  useEffect(() => {
    if (workspaceId === null) return;
    const workspaceIdValue = workspaceId;
    let isActive = true;
    setIsStaticLoading(true);
    setErrorMessage(null);

    async function load() {
      try {
        const data = await fetchStaticData(workspaceIdValue);
        if (isActive) {
          setStaticData(data);
        }
      } catch (error) {
        if (isActive) {
          const message = error instanceof Error ? error.message : t('topology.failedLoad');
          setErrorMessage(message);
        }
      } finally {
        if (isActive) setIsStaticLoading(false);
      }
    }

    void load();
    return () => {
      isActive = false;
    };
  }, [workspaceId, refreshKey, t]);

  // ---- Live status polling (every 2s) ----
  useEffect(() => {
    if (workspaceId === null) return;
    const workspaceIdValue = workspaceId;
    let cancelled = false;
    let timerId: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      if (cancelled) return;
      try {
        const items = await fetchTopologyLiveStatus(workspaceIdValue);
        if (!cancelled) setLiveStatus(items);
      } catch {
        // Live status is best-effort; do not propagate polling errors
      } finally {
        if (!cancelled) {
          timerId = setTimeout(poll, LIVE_STATUS_INTERVAL_MS);
        }
      }
    }

    timerId = setTimeout(poll, 0);
    return () => {
      cancelled = true;
      if (timerId !== null) clearTimeout(timerId);
    };
  }, [workspaceId]);

  // ---- Messaging event polling + active passage animation ----
  useEffect(() => {
    if (workspaceId === null) return;
    let cancelled = false;
    let timerId: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      if (cancelled) return;
      try {
        const sinceIso = new Date(Date.now() - EVENT_LOOKBACK_MS).toISOString();
        const url = `/events?type_prefix=messaging.&since=${encodeURIComponent(sinceIso)}&limit=20`;
        const page = await api<CursorPage<Event>>(url);
        if (cancelled) return;

        const now = Date.now();
        let mutated = false;
        setActivePassages((prev) => {
          const next = new Map(prev);
          for (const event of page.items) {
            if (event.type !== 'messaging.message_sent') continue;
            const passageId = event.payload.passage_id ?? event.payload.corridor_id;
            if (typeof passageId !== 'string') continue;
            next.set(passageId, now + PARTICLE_DURATION_MS);
            mutated = true;
          }
          return mutated ? next : prev;
        });
      } catch {
        // best-effort
      } finally {
        if (!cancelled) {
          timerId = setTimeout(poll, EVENT_POLL_INTERVAL_MS);
        }
      }
    }

    timerId = setTimeout(poll, 0);
    return () => {
      cancelled = true;
      if (timerId !== null) clearTimeout(timerId);
    };
  }, [workspaceId]);

  // ---- Expire activePassages entries ----
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      setActivePassages((prev) => {
        if (prev.size === 0) return prev;
        let changed = false;
        const next = new Map<string, number>();
        for (const [id, expiresAt] of prev) {
          if (expiresAt > now) {
            next.set(id, expiresAt);
          } else {
            changed = true;
          }
        }
        return changed ? next : prev;
      });
    }, PARTICLE_TICK_MS);
    return () => clearInterval(interval);
  }, []);

  // ---- Derived node + passage summaries ----
  const nodes = useMemo<readonly NodeSummary[]>(() => {
    if (staticData === null) return [];
    const statusByMembership = new Map<string, LiveStatusItem>();
    for (const item of liveStatus) statusByMembership.set(item.membership_id, item);

    const membershipNodes: NodeSummary[] = staticData.memberships.map((m) => {
      const status = statusByMembership.get(m.id);
      const isUser = m.user_id !== null;
      const fallbackStatus: LiveStatusItem = {
        membership_id: m.id,
        posx: m.posx,
        posy: m.posy,
        node_type: isUser ? 'user' : 'instance',
        glow: { color: '#94a3b8', intensity: 'static' },
        outdated: false,
        active_hash: null,
        instance_status: null,
        mentionable: false,
        display_status: null,
      };
      const effective = status ?? fallbackStatus;
      const isCurrentUser = isUser && currentUserId !== null && m.user_id === currentUserId;
      const username = m.username?.trim() || null;
      const displayName = m.nickname?.trim() || username;
      const label = isUser
        ? isCurrentUser
          ? t('topology.meLabel', { name: displayName ?? t('topology.userLabel') })
          : (displayName ?? t('topology.userLabel'))
        : (m.entity_name ?? m.entity_slug ?? m.instance_id ?? t('topology.instanceLabel'));
      return {
        kind: 'membership' as const,
        id: m.id,
        instanceId: m.instance_id,
        x: m.posx,
        y: m.posy,
        label,
        slug: isUser ? (username ?? m.user_id ?? '') : (m.entity_slug ?? ''),
        status: effective.display_status ?? effective.instance_status ?? effective.glow.intensity,
        fillColor: isUser ? userFillColor() : instanceFillColor(),
        glowColor: effective.glow.color,
        glowIntensity: effective.glow.intensity,
        outdated: effective.outdated,
        activeHash: effective.active_hash,
        instanceStatus: effective.instance_status ?? null,
        mentionable: effective.mentionable === true,
        displayStatus: effective.display_status ?? null,
        isCurrentUser,
      };
    });

    // Visual 主脑 hub: spokes to every membership; not an editable passage endpoint.
    let hubX = 0;
    let hubY = 0;
    if (membershipNodes.length > 0) {
      hubX = membershipNodes.reduce((sum, n) => sum + n.x, 0) / membershipNodes.length;
      hubY = membershipNodes.reduce((sum, n) => sum + n.y, 0) / membershipNodes.length;
    }
    const hubNode: NodeSummary = {
      kind: 'hub',
      id: HUB_NODE_ID,
      instanceId: null,
      x: hubX,
      y: hubY,
      label: t('topology.hubLabel'),
      slug: 'hub',
      status: 'static',
      fillColor: HUB_FILL,
      glowColor: HUB_GLOW,
      glowIntensity: 'medium',
      outdated: false,
      activeHash: null,
      instanceStatus: null,
      mentionable: false,
      displayStatus: null,
      isCurrentUser: false,
    };

    return [hubNode, ...membershipNodes];
  }, [staticData, liveStatus, t, currentUserId]);

  const applyFit = useCallback(() => {
    const vp = fitNodes(nodes, {
      viewSize: 2000,
      padding: 0.15,
      minZoom: MIN_ZOOM,
      maxZoom: MAX_ZOOM,
    });
    setPanX(vp.panX);
    setPanY(vp.panY);
    setZoom(vp.zoom);
    panXRef.current = vp.panX;
    panYRef.current = vp.panY;
    zoomRef.current = vp.zoom;
  }, [nodes]);

  const didFitRef = useRef(false);
  useEffect(() => {
    if (nodes.length === 0 || didFitRef.current) return;
    didFitRef.current = true;
    applyFit();
  }, [nodes, applyFit]);

  useEffect(() => {
    didFitRef.current = false;
  }, [workspaceId]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement ||
        event.target instanceof HTMLSelectElement ||
        event.metaKey ||
        event.ctrlKey ||
        event.altKey
      ) {
        return;
      }
      if (event.key === 'f' || event.key === 'F' || event.key === '0') {
        event.preventDefault();
        applyFit();
      }
      if (event.key === 'Delete' || event.key === 'Backspace') {
        event.preventDefault();
        deleteSelectionRef.current();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [applyFit]);

  const handleChatInComposer = useCallback(
    (node: NodeSummary) => {
      if (!node.slug || node.instanceId === null || !node.mentionable) return;
      setComposerDraft(`@${node.slug} `);
    },
    [setComposerDraft],
  );

  const handleRestartInstance = useCallback(
    async (node: NodeSummary) => {
      if (node.instanceId === null || workspaceId === null) return;
      try {
        const record = await api<{ id: string; instance_id: string }>(
          `/instances/${encodeURIComponent(node.instanceId)}/deploy`,
          { method: 'POST' },
        );
        const { useDeployProgressStore } = await import('@/stores/deployProgressStore');
        useDeployProgressStore.getState().start({
          recordId: record.id,
          instanceId: record.instance_id,
          workspaceId,
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : t('topology.failedCreate');
        setActionError(message);
      }
    },
    [workspaceId, t],
  );

  const resolvedPassages = useMemo<readonly ResolvedPassage[]>(() => {
    if (staticData === null) return [];
    const membershipById = new Map(staticData.memberships.map((m) => [m.id, m]));

    const result: ResolvedPassage[] = [];
    for (const passage of staticData.passages) {
      const fromMembership = membershipById.get(passage.from_membership_id);
      const toMembership = membershipById.get(passage.to_membership_id);
      if (fromMembership === undefined || toMembership === undefined) continue;
      result.push({
        passage,
        from: { id: fromMembership.id, x: fromMembership.posx, y: fromMembership.posy },
        to: { id: toMembership.id, x: toMembership.posx, y: toMembership.posy },
      });
    }
    return result;
  }, [staticData]);

  const membershipLabelById = useMemo(() => {
    const byId = new Map<string, string>();
    for (const node of nodes) {
      if (node.kind === 'membership') byId.set(node.id, node.label);
    }
    return byId;
  }, [nodes]);

  // ---- Pointer handlers (pan via drag) ----
  const handleMouseDown = useCallback(
    (event: ReactMouseEvent<SVGSVGElement>) => {
      if (event.button !== 0) return;
      const target = event.target as Element | null;
      // Only start panning when the click lands on the background, not a node
      if (target !== null && target.closest('[data-topology-node="true"]') !== null) {
        return;
      }
      // Clicking empty canvas in connect mode cancels the pending connection.
      if (interactionMode === 'connect' && pendingConnection !== null) {
        setPendingConnection(null);
        return;
      }
      isDraggingRef.current = true;
      lastPointerRef.current = { x: event.clientX, y: event.clientY };
    },
    [interactionMode, pendingConnection],
  );

  useEffect(() => {
    function handleMouseMove(event: globalThis.MouseEvent) {
      if (!isDraggingRef.current) return;
      const last = lastPointerRef.current;
      if (last === null) return;
      const dx = event.clientX - last.x;
      const dy = event.clientY - last.y;
      lastPointerRef.current = { x: event.clientX, y: event.clientY };

      const svg = svgRef.current;
      if (svg === null) {
        panXRef.current += dx;
        panYRef.current += dy;
        return;
      }
      const rect = svg.getBoundingClientRect();
      // viewBox is 2000 user units wide -> pixels-to-user scale. Fall back to
      // a 1:1 ratio when the SVG has no measurable layout (e.g. jsdom tests).
      const userPerPixel = rect.width > 0 ? 2000 / rect.width : 1;
      panXRef.current += dx * userPerPixel;
      panYRef.current += dy * userPerPixel;
    }

    function handleMouseUp() {
      if (!isDraggingRef.current) return;
      isDraggingRef.current = false;
      lastPointerRef.current = null;
      // Commit ref values to React state on drag end so the transform re-renders.
      setPanX(panXRef.current);
      setPanY(panYRef.current);
    }

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  const handleWheel = useCallback((event: ReactWheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    const factor = event.deltaY < 0 ? 1.1 : 1 / 1.1;
    const next = clamp(zoomRef.current * factor, MIN_ZOOM, MAX_ZOOM);
    setZoom(next);
  }, []);

  // ---- Node interaction handlers (Todo 9: mode-aware) ----

  // Drag state mirrored into a ref so the global mousemove/mouseup listeners
  // can read the latest drag coordinates without re-subscribing on every move.
  const dragStateRef = useRef<DragState | null>(null);
  useEffect(() => {
    dragStateRef.current = dragState;
  }, [dragState]);

  // rAF token so we coalesce mousemove updates to one React state write per frame.
  const rafIdRef = useRef<number | null>(null);
  const lastDragPointerRef = useRef<{ x: number; y: number } | null>(null);

  const handleNodeClick = useCallback(
    (node: NodeSummary) => {
      if (node.kind === 'hub') {
        onOpenBrain?.();
        setSelectedNode(null);
        setPendingConnection(null);
        return;
      }
      if (interactionMode === 'select') {
        setSelectedNode(node);
        setPendingConnection(null);
        return;
      }
      if (interactionMode === 'connect') {
        // Hub is visual-only — never participate in solid Passage edges.
        if (pendingConnection === null) {
          setPendingConnection({ id: node.id });
          setActionError(null);
          return;
        }
        if (pendingConnection.id === node.id) {
          setPendingConnection(null);
          return;
        }
        if (pendingConnection.id === HUB_NODE_ID) {
          setPendingConnection(null);
          setActionError(t('topology.hubNoConnect'));
          return;
        }
        setPendingConnectionCompletion({
          source: pendingConnection,
          target: { id: node.id },
        });
        setPendingConnection(null);
        return;
      }
    },
    [interactionMode, pendingConnection, onOpenBrain, t],
  );

  const [pendingConnectionCompletion, setPendingConnectionCompletion] = useState<{
    readonly source: PendingConnection;
    readonly target: PendingConnection;
  } | null>(null);

  // Effect: when a connect-mode pair is completed, POST /messaging/passages.
  useEffect(() => {
    if (pendingConnectionCompletion === null) return;
    if (workspaceId === null) return;
    const completion = pendingConnectionCompletion;
    let cancelled = false;

    async function createPassage() {
      const body: PassageCreateBody = {
        workspace_id: workspaceId as string,
        from_membership_id: completion.source.id,
        to_membership_id: completion.target.id,
      };
      try {
        await api<PassageEdge>('/messaging/passages', {
          method: 'POST',
          body: JSON.stringify(body),
        });
        if (cancelled) return;
        const fresh = await fetchStaticData(workspaceId as string);
        if (cancelled) return;
        setStaticData(fresh);
        setActionError(null);
      } catch (error) {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : t('topology.failedCreate');
        setActionError(message);
      }
    }

    void createPassage();
    return () => {
      cancelled = true;
    };
  }, [pendingConnectionCompletion, workspaceId, t]);

  const handlePassageSelect = useCallback(
    (passage: PassageEdge) => {
      if (interactionMode !== 'select') return;
      setSelectedNode(null);
      setPendingConnection(null);
      setSelectedPassage(passage);
    },
    [interactionMode],
  );

  const handleRemoveNode = useCallback(
    async (node: NodeSummary) => {
      if (workspaceId === null || node.kind === 'hub') return;
      try {
        if (node.instanceId !== null) {
          await deleteInstanceById(node.instanceId);
        } else {
          await deleteMembership(node.id);
        }
        const fresh = await fetchStaticData(workspaceId);
        setStaticData(fresh);
        setSelectedNode(null);
        setActionError(null);
      } catch (error) {
        const message = resolveErrorMessage(
          error,
          (key, options) => t(key, options),
          'topology.failedDelete',
        );
        setActionError(message);
        throw error;
      }
    },
    [workspaceId, t],
  );

  const handleDeletePassage = useCallback(async () => {
    if (selectedPassage === null || workspaceId === null) return;
    const from =
      membershipLabelById.get(selectedPassage.from_membership_id) ??
      selectedPassage.from_membership_id;
    const to =
      membershipLabelById.get(selectedPassage.to_membership_id) ?? selectedPassage.to_membership_id;
    const ok = window.confirm(t('topology.removePassageConfirm', { from, to }));
    if (!ok) return;
    try {
      await deletePassage(selectedPassage.id);
      const fresh = await fetchStaticData(workspaceId);
      setStaticData(fresh);
      setSelectedPassage(null);
      setActionError(null);
    } catch (error) {
      const message = resolveErrorMessage(
        error,
        (key, options) => t(key, options),
        'topology.failedDeletePassage',
      );
      setActionError(message);
    }
  }, [selectedPassage, workspaceId, membershipLabelById, t]);

  const handleDeleteSelection = useCallback(async () => {
    if (workspaceId === null) return;
    if (selectedNode !== null && selectedNode.kind !== 'hub') {
      const confirmKey =
        selectedNode.instanceId !== null
          ? 'topology.removeLostOneConfirm'
          : 'topology.removeAwakenedConfirm';
      const ok = window.confirm(t(confirmKey, { name: selectedNode.label }));
      if (!ok) return;
      try {
        await handleRemoveNode(selectedNode);
      } catch {
        // Error already surfaced via setActionError inside handleRemoveNode
      }
      return;
    }
    if (selectedPassage !== null) {
      await handleDeletePassage();
    }
  }, [workspaceId, selectedNode, selectedPassage, handleRemoveNode, handleDeletePassage, t]);

  useEffect(() => {
    deleteSelectionRef.current = () => {
      void handleDeleteSelection();
    };
  }, [handleDeleteSelection]);

  // ---- Move mode: drag handlers ----

  const handleNodeMouseDown = useCallback(
    (node: NodeSummary, event: ReactMouseEvent<SVGGElement>) => {
      if (node.kind === 'hub') return;
      if (interactionMode !== 'move') return;
      if (event.button !== 0) return;
      event.stopPropagation();
      const initial: DragState = {
        id: node.id,
        originX: node.x,
        originY: node.y,
        currentX: node.x,
        currentY: node.y,
      };
      dragStateRef.current = initial;
      setDragState(initial);
      lastDragPointerRef.current = { x: event.clientX, y: event.clientY };
    },
    [interactionMode],
  );

  // Global mousemove/mouseup for node drag (separate from pan listeners so
  // we can apply rAF throttling and resolve SVG coordinates correctly).
  useEffect(() => {
    if (dragState === null) return;

    function handleMove(event: globalThis.MouseEvent) {
      const drag = dragStateRef.current;
      const lastPointer = lastDragPointerRef.current;
      if (drag === null || lastPointer === null) return;
      const svg = svgRef.current;
      if (svg === null) return;

      const rect = svg.getBoundingClientRect();
      const userPerPixel = rect.width > 0 ? 2000 / rect.width : 1;
      const dx = (event.clientX - lastPointer.x) * userPerPixel;
      const dy = (event.clientY - lastPointer.y) * userPerPixel;
      lastDragPointerRef.current = { x: event.clientX, y: event.clientY };

      const next: DragState = {
        ...drag,
        currentX: drag.currentX + dx,
        currentY: drag.currentY + dy,
      };
      dragStateRef.current = next;

      if (rafIdRef.current !== null) return;
      rafIdRef.current = requestAnimationFrame(() => {
        rafIdRef.current = null;
        setDragState(dragStateRef.current);
      });
    }

    async function handleUp() {
      const drag = dragStateRef.current;
      if (drag === null) return;
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
      lastDragPointerRef.current = null;
      dragStateRef.current = null;
      setDragState(null);

      const moved =
        Math.round(drag.currentX) !== Math.round(drag.originX) ||
        Math.round(drag.currentY) !== Math.round(drag.originY);
      if (!moved) return;

      const patchBody: NodeDragPatchBody = {
        posx: Math.round(drag.currentX),
        posy: Math.round(drag.currentY),
      };
      const endpoint = `/messaging/memberships/${encodeURIComponent(drag.id)}`;

      try {
        await api(endpoint, {
          method: 'PATCH',
          body: JSON.stringify(patchBody),
        });
        if (workspaceId !== null) {
          const fresh = await fetchStaticData(workspaceId);
          setStaticData(fresh);
        }
        setActionError(null);
      } catch (error) {
        // Revert is implicit: dragState was cleared above and the optimistic
        // position was never persisted into staticData, so the next render
        // falls back to the original (originX, originY) from the server.
        const message =
          error instanceof ApiError && error.status === 409
            ? `Position (${patchBody.posx}, ${patchBody.posy}) is already used in this workspace`
            : error instanceof Error
              ? error.message
              : t('topology.failedMove');
        setActionError(message);
      }
    }

    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };
  }, [dragState, workspaceId, t]);

  useEffect(() => {
    if (interactionMode !== 'connect') setPendingConnection(null);
    if (interactionMode !== 'select') setSelectedNode(null);
    if (interactionMode !== 'select') setSelectedPassage(null);
  }, [interactionMode]);

  // ---- Render ----
  if (workspaceId === null) {
    return (
      <section className="mx-auto w-full max-w-6xl p-6 lg:p-8">
        <p className="rounded-lg border border-dashed border-red-300 bg-red-50 px-6 py-12 text-center text-sm text-red-700">
          {t('workspace.idMissing')}
        </p>
      </section>
    );
  }

  const transform = `translate(${panX} ${panY}) scale(${zoom})`;
  const now = Date.now();

  return (
    <section
      className={`flex h-full w-full max-w-full flex-col ${embedded ? 'p-0' : 'p-0'}`}
      aria-labelledby="topology-title"
    >
      {!embedded ? (
        <header className="flex shrink-0 items-center justify-between gap-4 border-b border-slate-200 bg-white px-4 py-3 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-blue-600 text-white">
              <Network className="size-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="font-mono text-xs text-slate-500">{workspaceId}</p>
              <h1
                id="topology-title"
                className="truncate text-lg font-semibold tracking-tight text-slate-950"
              >
                {t('topology.title')}
              </h1>
            </div>
          </div>
          <p className="hidden text-xs text-slate-500 sm:block">{t('topology.tagline')}</p>
        </header>
      ) : null}

      {pendingConnection !== null ? (
        <div
          role="status"
          className="flex shrink-0 items-center gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800 sm:px-6"
          data-testid="topology-connect-hint"
        >
          <span className="grid size-4 place-items-center rounded-full bg-amber-500 text-white">
            <Link className="size-2.5" aria-hidden="true" />
          </span>
          <span>{t('topology.clickTargetHint')}</span>
        </div>
      ) : null}

      {actionError !== null ? (
        <div
          role="alert"
          className="flex shrink-0 items-center gap-3 border-b border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 sm:px-6"
          data-testid="topology-action-error"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p className="min-w-0 flex-1">{actionError}</p>
          <button
            type="button"
            onClick={() => setActionError(null)}
            className="inline-flex size-6 shrink-0 items-center justify-center rounded text-red-600 hover:bg-red-100"
            aria-label={t('topology.dismissError')}
          >
            <X className="size-3.5" aria-hidden="true" />
          </button>
        </div>
      ) : null}

      {errorMessage !== null ? (
        <div
          role="alert"
          className="flex shrink-0 gap-3 border-b border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 sm:px-6"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p>{errorMessage}</p>
        </div>
      ) : null}

      <div className="relative flex min-h-0 flex-1">
        <div
          className="relative flex min-w-0 flex-1 items-center justify-center overflow-hidden bg-slate-50"
          data-testid="topology-canvas-container"
        >
          <ModeToolbar
            onFit={applyFit}
            onDeleteSelected={() => {
              void handleDeleteSelection();
            }}
            canDelete={selectedNode !== null || selectedPassage !== null}
          />
          {isStaticLoading ? (
            <div className="flex items-center justify-center gap-3 text-sm text-slate-500">
              <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
              {t('topology.loading')}
            </div>
          ) : null}

          {!isStaticLoading && errorMessage === null ? (
            <svg
              ref={svgRef}
              role="img"
              aria-label={t('topology.canvasAria', { workspaceId: workspaceId ?? '' })}
              data-testid="topology-canvas"
              viewBox={VIEW_BOX}
              preserveAspectRatio="xMidYMid meet"
              className={`h-full w-full select-none transition-[filter,opacity] duration-200 ${selectedNode !== null ? 'blur-[8px] opacity-30' : ''} ${interactionMode === 'connect' ? 'cursor-crosshair' : interactionMode === 'move' ? 'cursor-move' : 'cursor-pointer'}`}
              onMouseDown={handleMouseDown}
              onWheel={handleWheel}
            >
              <TopologyGlowDefs />

              {/* subtle grid backdrop - purely cosmetic, no role in tests */}
              <g opacity="0.25">
                {[-800, -400, 0, 400, 800].map((tick) => (
                  <line
                    key={`v-${tick}`}
                    x1={tick}
                    y1={-1000}
                    x2={tick}
                    y2={1000}
                    stroke="#cbd5e1"
                    strokeWidth={1}
                  />
                ))}
                {[-800, -400, 0, 400, 800].map((tick) => (
                  <line
                    key={`h-${tick}`}
                    x1={-1000}
                    y1={tick}
                    x2={1000}
                    y2={tick}
                    stroke="#cbd5e1"
                    strokeWidth={1}
                  />
                ))}
              </g>

              <g data-testid="topology-canvas-content" transform={transform}>
                {(() => {
                  const hub = nodes.find((n) => n.kind === 'hub');
                  if (hub === undefined) return null;
                  return nodes
                    .filter((n) => n.kind === 'membership')
                    .map((n) => (
                      <line
                        key={`hub-spoke-${n.id}`}
                        x1={hub.x}
                        y1={hub.y}
                        x2={n.x}
                        y2={n.y}
                        stroke={HUB_SPOKE_STROKE}
                        strokeWidth={1.5}
                        strokeDasharray="6 4"
                        strokeOpacity={0.55}
                        pointerEvents="none"
                        data-testid={`topology-hub-spoke-${n.id}`}
                      />
                    ));
                })()}

                {resolvedPassages.map((entry) => (
                  <PassageView
                    key={entry.passage.id}
                    entry={entry}
                    isActive={activePassages.has(entry.passage.id)}
                    isSelected={selectedPassage !== null && selectedPassage.id === entry.passage.id}
                    isSelectMode={interactionMode === 'select'}
                    onSelect={handlePassageSelect}
                    now={now}
                  />
                ))}

                {nodes.map((node) => {
                  const isPendingSource =
                    pendingConnection !== null && pendingConnection.id === node.id;
                  const isSelected = selectedNode !== null && selectedNode.id === node.id;
                  const dragOverride =
                    dragState !== null && dragState.id === node.id
                      ? { x: dragState.currentX, y: dragState.currentY }
                      : null;
                  return (
                    <NodeView
                      key={node.id}
                      node={node}
                      onClick={handleNodeClick}
                      onDoubleClick={(clickedNode) => {
                        if (clickedNode.kind === 'hub') {
                          onOpenBrain?.();
                          return;
                        }
                        if (clickedNode.instanceId === null) return;
                        addTab({
                          id: `instance-${clickedNode.instanceId}`,
                          label: clickedNode.label,
                          instanceId: clickedNode.instanceId,
                        });
                        setSelectedNode(null);
                      }}
                      onMouseDown={handleNodeMouseDown}
                      onChat={handleChatInComposer}
                      onRestart={(n) => {
                        void handleRestartInstance(n);
                      }}
                      isHighlighted={isPendingSource || isSelected}
                      highlightKind={isPendingSource ? 'pending' : isSelected ? 'selected' : null}
                      dragOverride={dragOverride}
                      isMoveCursor={interactionMode === 'move' && node.kind !== 'hub'}
                    />
                  );
                })}
              </g>
            </svg>
          ) : null}
        </div>

        {selectedNode !== null ? (
          <NodeModal
            node={selectedNode}
            onClose={() => setSelectedNode(null)}
            onRemove={handleRemoveNode}
          />
        ) : null}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Sub-views
// ---------------------------------------------------------------------------

type NodeViewProps = {
  readonly node: NodeSummary;
  readonly onClick: (node: NodeSummary) => void;
  readonly onDoubleClick: (node: NodeSummary) => void;
  readonly onMouseDown: (node: NodeSummary, event: ReactMouseEvent<SVGGElement>) => void;
  readonly onChat: (node: NodeSummary) => void;
  readonly onRestart: (node: NodeSummary) => void;
  readonly isHighlighted: boolean;
  readonly highlightKind: 'pending' | 'selected' | null;
  readonly dragOverride: { readonly x: number; readonly y: number } | null;
  readonly isMoveCursor: boolean;
};

function NodeView({
  node,
  onClick,
  onDoubleClick,
  onMouseDown,
  onChat,
  onRestart,
  isHighlighted,
  highlightKind,
  dragOverride,
  isMoveCursor,
}: NodeViewProps): ReactElement {
  const { t } = useTranslation();
  const haloOpacity = intensityOpacity(node.glowIntensity);
  const coreStrokeOpacity = intensityStrokeOpacity(node.glowIntensity);
  const isUser = node.fillColor === DEFAULT_USER_FILL;
  const tooltip = `${node.label} | ${node.status}`;
  const Icon = node.kind === 'hub' ? Brain : isUser ? User : node.instanceId !== null ? Cpu : Bot;
  const renderX = dragOverride !== null ? dragOverride.x : node.x;
  const renderY = dragOverride !== null ? dragOverride.y : node.y;
  const highlightStroke =
    highlightKind === 'pending' ? '#f59e0b' : highlightKind === 'selected' ? '#2563eb' : null;
  const [isTooltipVisible, setIsTooltipVisible] = useState(false);
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showTooltip = () => {
    if (hideTimerRef.current !== null) clearTimeout(hideTimerRef.current);
    if (hoverTimerRef.current !== null) clearTimeout(hoverTimerRef.current);
    hoverTimerRef.current = setTimeout(() => setIsTooltipVisible(true), 350);
  };

  const scheduleHideTooltip = () => {
    if (hoverTimerRef.current !== null) clearTimeout(hoverTimerRef.current);
    if (hideTimerRef.current !== null) clearTimeout(hideTimerRef.current);
    // Longer grace + invisible bridge rect below closes the SVG hit-test gap.
    hideTimerRef.current = setTimeout(() => setIsTooltipVisible(false), 450);
  };

  const cancelHideTooltip = () => {
    if (hideTimerRef.current !== null) clearTimeout(hideTimerRef.current);
  };
  const clickTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (hoverTimerRef.current !== null) clearTimeout(hoverTimerRef.current);
      if (hideTimerRef.current !== null) clearTimeout(hideTimerRef.current);
      if (clickTimerRef.current !== null) clearTimeout(clickTimerRef.current);
    },
    [],
  );

  return (
    /* biome-ignore lint/a11y/noStaticElementInteractions: SVG <g> has no semantic <button> */
    <g
      data-testid={`topology-node-${node.id}`}
      data-topology-node="true"
      data-node-kind={node.kind}
      data-highlight={highlightKind ?? undefined}
      transform={`translate(${renderX} ${renderY})`}
      className={isMoveCursor ? 'cursor-move' : 'cursor-pointer'}
      onClick={(event) => {
        event.stopPropagation();
        if (clickTimerRef.current !== null) clearTimeout(clickTimerRef.current);
        clickTimerRef.current = setTimeout(() => onClick(node), 300);
      }}
      onDoubleClick={(event) => {
        event.stopPropagation();
        if (clickTimerRef.current !== null) clearTimeout(clickTimerRef.current);
        clickTimerRef.current = null;
        onDoubleClick(node);
      }}
      onMouseEnter={showTooltip}
      onMouseLeave={scheduleHideTooltip}
      onMouseDown={(event) => {
        onMouseDown(node, event);
      }}
    >
      {isHighlighted && highlightStroke !== null ? (
        <circle
          r={HALO_RADIUS + 6}
          fill="none"
          stroke={highlightStroke}
          strokeWidth={2}
          strokeDasharray="6 3"
          data-testid={`topology-node-highlight-${node.id}`}
        />
      ) : null}
      {haloOpacity > 0 ? (
        <circle
          r={HALO_RADIUS}
          fill="none"
          stroke={node.glowColor}
          strokeOpacity={haloOpacity}
          strokeWidth={HALO_STROKE_WIDTH}
          filter="url(#topology-glow-blur)"
          data-testid={`topology-node-halo-${node.id}`}
        />
      ) : null}
      <circle
        r={NODE_RADIUS}
        fill={node.fillColor}
        stroke={node.isCurrentUser ? '#2563eb' : node.glowColor}
        strokeOpacity={node.isCurrentUser ? 1 : coreStrokeOpacity}
        strokeWidth={node.isCurrentUser ? CORE_STROKE_WIDTH + 1.5 : CORE_STROKE_WIDTH}
        data-testid={`topology-node-core-${node.id}`}
      />
      {node.outdated ? <OutdatedOverlay nodeId={node.id} /> : null}
      <foreignObject x={-12} y={-12} width={24} height={24}>
        <div
          className="flex h-full w-full items-center justify-center text-slate-800"
          aria-hidden="true"
        >
          <Icon size={20} strokeWidth={2} />
        </div>
      </foreignObject>
      {node.kind !== 'hub' ? (
        <text
          y={NODE_RADIUS + 16}
          textAnchor="middle"
          className="fill-slate-700"
          style={{ fontSize: 11, fontWeight: node.isCurrentUser ? 700 : 500 }}
          data-testid={`topology-node-label-${node.id}`}
        >
          {node.label.length > 14 ? `${node.label.slice(0, 13)}…` : node.label}
        </text>
      ) : null}
      {node.isCurrentUser ? (
        <text
          y={NODE_RADIUS + 30}
          textAnchor="middle"
          className="fill-blue-600"
          style={{ fontSize: 10, fontWeight: 700 }}
          data-testid={`topology-node-me-${node.id}`}
        >
          {t('topology.meBadge')}
        </text>
      ) : null}
      {isTooltipVisible ? (
        <g
          data-testid={`topology-tooltip-group-${node.id}`}
          onMouseEnter={cancelHideTooltip}
          onMouseLeave={scheduleHideTooltip}
        >
          {/* Invisible hit bridge: fills the gap between node core and tooltip panel */}
          <rect x={-40} y={-220} width={80} height={220} fill="transparent" pointerEvents="all" />
          <NodeTooltip
            node={node}
            onOpen={() => onClick(node)}
            onChat={() => onChat(node)}
            onRestart={() => onRestart(node)}
            onPointerEnter={cancelHideTooltip}
            onPointerLeave={scheduleHideTooltip}
          />
        </g>
      ) : null}
      <title>{tooltip}</title>
    </g>
  );
}

type NodeDrawerProps = {
  readonly node: NodeSummary;
  readonly isEditor: boolean;
  readonly onClose: () => void;
  readonly onDelete: (node: NodeSummary) => Promise<void>;
};

export function NodeDrawer({ node, isEditor, onClose, onDelete }: NodeDrawerProps): ReactElement {
  const { t } = useTranslation();
  return (
    <aside
      className="flex w-72 shrink-0 flex-col gap-3 border-l border-slate-200 bg-white p-4"
      aria-label="Selected node details"
      data-testid="topology-node-drawer"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            {t('topology.membershipNode')}
          </p>
          <h2 className="truncate text-base font-semibold text-slate-950">{node.label}</h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex size-7 shrink-0 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-800"
          aria-label="Close details"
        >
          <X className="size-4" aria-hidden="true" />
        </button>
      </div>

      <dl className="flex flex-col gap-2 text-sm">
        <div className="flex justify-between gap-3">
          <dt className="text-slate-500">ID</dt>
          <dd className="truncate font-mono text-xs text-slate-800">{node.id}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-slate-500">Status</dt>
          <dd className="text-slate-800">{node.status}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-slate-500">Glow</dt>
          <dd className="flex items-center gap-2 text-slate-800">
            <span
              className="inline-block size-3 rounded-full"
              style={{ backgroundColor: node.glowColor }}
              aria-hidden="true"
            />
            <span>{node.glowIntensity}</span>
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-slate-500">Position</dt>
          <dd className="font-mono text-xs text-slate-800">
            ({node.x}, {node.y})
          </dd>
        </div>
      </dl>

      {isEditor ? (
        <div className="mt-auto flex flex-col gap-2 border-t border-slate-200 pt-3">
          <button
            type="button"
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-medium text-red-700 transition-colors hover:bg-red-50"
            onClick={() => {
              void onDelete(node);
            }}
            data-testid={`topology-node-delete-${node.id}`}
          >
            <Trash className="size-4" aria-hidden="true" />
            <span>{t('topology.removeNode')}</span>
          </button>
        </div>
      ) : null}
    </aside>
  );
}

type PassageViewProps = {
  readonly entry: ResolvedPassage;
  readonly isActive: boolean;
  readonly isSelected: boolean;
  readonly isSelectMode: boolean;
  readonly onSelect: (passage: PassageEdge) => void;
  readonly now: number;
};

function PassageView({
  entry,
  isActive,
  isSelected,
  isSelectMode,
  onSelect,
  now,
}: PassageViewProps): ReactElement {
  const { passage, from, to } = entry;
  const stroke = isActive ? ACTIVE_STROKE : isSelected ? SELECTED_STROKE : DEFAULT_STROKE;
  const strokeWidth = isActive
    ? ACTIVE_STROKE_WIDTH
    : isSelected
      ? SELECTED_STROKE_WIDTH
      : DEFAULT_STROKE_WIDTH;

  return (
    <g data-testid={`topology-passage-${passage.id}`} data-passage-id={passage.id}>
      <line
        x1={from.x}
        y1={from.y}
        x2={to.x}
        y2={to.y}
        stroke={stroke}
        strokeWidth={strokeWidth}
        data-testid={`topology-passage-line-${passage.id}`}
        data-active={isActive ? 'true' : 'false'}
        data-selected={isSelected ? 'true' : 'false'}
      />
      {/* Invisible wide hit target so thin edges are selectable in Select mode. */}
      {/* biome-ignore lint/a11y/noStaticElementInteractions: SVG <line> has no semantic <button> */}
      <line
        x1={from.x}
        y1={from.y}
        x2={to.x}
        y2={to.y}
        stroke="transparent"
        strokeWidth={16}
        fill="none"
        pointerEvents="stroke"
        className={isSelectMode ? 'cursor-pointer' : undefined}
        data-testid={`topology-passage-hit-${passage.id}`}
        onMouseDown={(event) => {
          // In Select mode, grabbing an edge selects it instead of panning.
          if (isSelectMode) event.stopPropagation();
        }}
        onClick={(event) => {
          event.stopPropagation();
          if (isSelectMode) onSelect(passage);
        }}
      />
      {isActive ? (
        <ParticleView passageId={passage.id} from={from} to={to} startedAt={now} />
      ) : null}
    </g>
  );
}

type ParticleViewProps = {
  readonly passageId: string;
  readonly from: ResolvedEndpoint;
  readonly to: ResolvedEndpoint;
  readonly startedAt: number;
};

function ParticleView({ passageId, from, to, startedAt }: ParticleViewProps): ReactElement {
  const path = `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
  return (
    <circle
      r={5}
      fill={ACTIVE_STROKE}
      data-testid={`topology-passage-particle-${passageId}`}
      data-started-at={startedAt}
    >
      <animateMotion
        path={path}
        dur={`${PARTICLE_DURATION_MS}ms`}
        fill="freeze"
        begin="0s"
        repeatCount="1"
      />
    </circle>
  );
}

function clamp(value: number, min: number, max: number): number {
  if (value < min) return min;
  if (value > max) return max;
  return value;
}
