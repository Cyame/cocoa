import { AlertCircle, Bot, LoaderCircle, Network, User } from 'lucide-react';
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
import { useParams } from 'react-router';
import TopologyGlowDefs, { GLOW_INTENSITY_OPACITY } from '@/components/TopologyGlow';
import { api } from '@/lib/api';
import type {
  CorridorNode as CorridorNodeModel,
  Event,
  GlowIntensity,
  LiveStatusItem,
  Membership,
} from '@/lib/types';
import { useSelectedStore } from '@/stores/selected';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Corridor = {
  readonly id: string;
  readonly office_id: string;
  readonly from_membership_id: string | null;
  readonly to_membership_id: string | null;
  readonly from_corridor_node_id: string | null;
  readonly to_corridor_node_id: string | null;
  readonly is_active: boolean;
};

type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly total: number;
};

type CursorPage<T> = {
  readonly items: readonly T[];
  readonly next_cursor: string | null;
  readonly total: number | null;
};

type NodeKind = 'membership' | 'corridor_node';

type ResolvedEndpoint =
  | {
      readonly kind: 'membership';
      readonly id: string;
      readonly x: number;
      readonly y: number;
    }
  | {
      readonly kind: 'corridor_node';
      readonly id: string;
      readonly x: number;
      readonly y: number;
      readonly label: string;
    };

type ResolvedCorridor = {
  readonly corridor: Corridor;
  readonly from: ResolvedEndpoint;
  readonly to: ResolvedEndpoint;
};

type NodeSummary = {
  readonly kind: NodeKind;
  readonly id: string;
  readonly x: number;
  readonly y: number;
  readonly label: string;
  readonly role: string;
  readonly status: string;
  readonly fillColor: string;
  readonly glowColor: string;
  readonly glowIntensity: GlowIntensity;
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
const LIVE_STATUS_INTERVAL_MS = 2000;
const EVENT_POLL_INTERVAL_MS = 2000;
const EVENT_LOOKBACK_MS = 5000;
const PARTICLE_TICK_MS = 200;

const DEFAULT_USER_FILL = '#e2e8f0';
const DEFAULT_INSTANCE_FILL = '#3b82f6';

function intensityOpacity(intensity: GlowIntensity): number {
  return GLOW_INTENSITY_OPACITY[intensity];
}

function intensityStrokeOpacity(intensity: GlowIntensity): number {
  // Slightly stronger so the inner ring remains visible against the halo
  if (intensity === 'static') return 0.4;
  return Math.min(1, GLOW_INTENSITY_OPACITY[intensity] + 0.2);
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
  readonly corridors: readonly Corridor[];
  readonly corridorNodes: readonly CorridorNodeModel[];
};

async function fetchStaticData(officeId: string): Promise<TopologyStaticData> {
  const [membershipPage, corridorPage, corridorNodePage] = await Promise.all([
    api<OffsetPage<Membership>>(`/messaging/memberships?office_id=${encodeURIComponent(officeId)}`),
    api<OffsetPage<Corridor>>(`/messaging/corridors?office_id=${encodeURIComponent(officeId)}`),
    api<CursorPage<CorridorNodeModel>>(
      `/learning/corridor-nodes?office_id=${encodeURIComponent(officeId)}`,
    ),
  ]);
  return {
    memberships: membershipPage.items,
    corridors: corridorPage.items,
    corridorNodes: corridorNodePage.items,
  };
}

// ---------------------------------------------------------------------------
// TopologyPage
// ---------------------------------------------------------------------------

export default function TopologyPage() {
  const { id: routeOfficeId } = useParams<{ id: string }>();
  const setOfficeId = useSelectedStore((state) => state.setOfficeId);
  const [staticData, setStaticData] = useState<TopologyStaticData | null>(null);
  const [liveStatus, setLiveStatus] = useState<readonly LiveStatusItem[]>([]);
  const [activeCorridors, setActiveCorridors] = useState<ReadonlyMap<string, number>>(
    () => new Map(),
  );
  const [isStaticLoading, setIsStaticLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

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

  const officeId = routeOfficeId ?? null;

  // Sync store with URL office id (matches OfficeDetailPage pattern)
  useEffect(() => {
    if (officeId === null) return;
    setOfficeId(officeId);
    return () => setOfficeId(null);
  }, [officeId, setOfficeId]);

  // ---- Initial topology load ----
  useEffect(() => {
    if (officeId === null) return;
    const officeIdValue = officeId;
    let isActive = true;
    setIsStaticLoading(true);
    setErrorMessage(null);

    async function load() {
      try {
        const data = await fetchStaticData(officeIdValue);
        if (isActive) {
          setStaticData(data);
        }
      } catch (error) {
        if (isActive) {
          const message = error instanceof Error ? error.message : 'Failed to load topology';
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
  }, [officeId]);

  // ---- Live status polling (every 2s) ----
  useEffect(() => {
    if (officeId === null) return;
    const officeIdValue = officeId;
    let cancelled = false;
    let timerId: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      if (cancelled) return;
      try {
        const items = await api<readonly LiveStatusItem[]>(
          `/offices/${encodeURIComponent(officeIdValue)}/live-status`,
        );
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
  }, [officeId]);

  // ---- Messaging event polling + active corridor animation ----
  useEffect(() => {
    if (officeId === null) return;
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
        setActiveCorridors((prev) => {
          const next = new Map(prev);
          for (const event of page.items) {
            if (event.type !== 'messaging.message_sent') continue;
            const corridorId = event.payload.corridor_id;
            if (typeof corridorId !== 'string') continue;
            next.set(corridorId, now + PARTICLE_DURATION_MS);
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
  }, [officeId]);

  // ---- Expire activeCorridors entries ----
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      setActiveCorridors((prev) => {
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

  // ---- Derived node + corridor summaries ----
  const nodes = useMemo<readonly NodeSummary[]>(() => {
    if (staticData === null) return [];
    const statusByMembership = new Map<string, LiveStatusItem>();
    for (const item of liveStatus) statusByMembership.set(item.membership_id, item);

    const membershipNodes: NodeSummary[] = staticData.memberships.map((m) => {
      const status = statusByMembership.get(m.id);
      const isUser = m.user_id !== null;
      const role = m.role;
      const fallbackStatus: LiveStatusItem = {
        membership_id: m.id,
        posx: m.posx,
        posy: m.posy,
        node_type: isUser ? 'user' : 'instance',
        glow: { color: '#94a3b8', intensity: 'static' },
      };
      const effective = status ?? fallbackStatus;
      const label = isUser ? (m.user_id ?? 'user') : (m.instance_id ?? 'instance');
      return {
        kind: 'membership',
        id: m.id,
        x: m.posx,
        y: m.posy,
        label,
        role,
        status: effective.glow.intensity,
        fillColor: isUser ? userFillColor() : instanceFillColor(),
        glowColor: effective.glow.color,
        glowIntensity: effective.glow.intensity,
      };
    });

    const corridorNodeNodes: NodeSummary[] = staticData.corridorNodes.map((cn) => ({
      kind: 'corridor_node',
      id: cn.id,
      x: cn.posx,
      y: cn.posy,
      label: cn.display_name,
      role: cn.status,
      status: cn.status,
      fillColor: '#f8fafc',
      glowColor: cn.glow_color ?? '#475569',
      glowIntensity: 'low',
    }));

    return [...membershipNodes, ...corridorNodeNodes];
  }, [staticData, liveStatus]);

  const resolvedCorridors = useMemo<readonly ResolvedCorridor[]>(() => {
    if (staticData === null) return [];
    const membershipById = new Map(staticData.memberships.map((m) => [m.id, m]));
    const corridorNodeById = new Map(staticData.corridorNodes.map((cn) => [cn.id, cn]));

    const result: ResolvedCorridor[] = [];
    for (const corridor of staticData.corridors) {
      const from = resolveEndpoint(
        corridor.from_membership_id,
        corridor.from_corridor_node_id,
        membershipById,
        corridorNodeById,
      );
      const to = resolveEndpoint(
        corridor.to_membership_id,
        corridor.to_corridor_node_id,
        membershipById,
        corridorNodeById,
      );
      if (from === null || to === null) continue;
      result.push({ corridor, from, to });
    }
    return result;
  }, [staticData]);

  // ---- Pointer handlers (pan via drag) ----
  const handleMouseDown = useCallback((event: ReactMouseEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    const target = event.target as Element | null;
    // Only start panning when the click lands on the background, not a node
    if (target !== null && target.closest('[data-topology-node="true"]') !== null) {
      return;
    }
    isDraggingRef.current = true;
    lastPointerRef.current = { x: event.clientX, y: event.clientY };
  }, []);

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

  // ---- Node click handler (Todo 9 will route by interaction mode) ----
  const handleNodeClick = useCallback((node: NodeSummary) => {
    // eslint-disable-next-line no-console -- explicitly logged for Todo 9 to pick up
    console.info('[topology] node click', {
      kind: node.kind,
      id: node.id,
      label: node.label,
      role: node.role,
      status: node.status,
    });
  }, []);

  // ---- Render ----
  if (officeId === null) {
    return (
      <section className="mx-auto w-full max-w-6xl p-6 lg:p-8">
        <p className="rounded-lg border border-dashed border-red-300 bg-red-50 px-6 py-12 text-center text-sm text-red-700">
          Office identifier is missing.
        </p>
      </section>
    );
  }

  const transform = `translate(${panX} ${panY}) scale(${zoom})`;
  const now = Date.now();

  return (
    <section
      className="mx-auto flex h-full w-full max-w-full flex-col p-0"
      aria-labelledby="topology-title"
    >
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-slate-200 bg-white px-4 py-3 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-blue-600 text-white">
            <Network className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="font-mono text-xs text-slate-500">{officeId}</p>
            <h1
              id="topology-title"
              className="truncate text-lg font-semibold tracking-tight text-slate-950"
            >
              Topology
            </h1>
          </div>
        </div>
        <p className="hidden text-xs text-slate-500 sm:block">
          Drag to pan. Wheel to zoom. Events refresh every 2 seconds.
        </p>
      </header>

      {errorMessage !== null ? (
        <div
          role="alert"
          className="flex shrink-0 gap-3 border-b border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 sm:px-6"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p>{errorMessage}</p>
        </div>
      ) : null}

      <div
        className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-slate-50"
        data-testid="topology-canvas-container"
      >
        {isStaticLoading ? (
          <div className="flex items-center justify-center gap-3 text-sm text-slate-500">
            <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
            Loading topology
          </div>
        ) : null}

        {!isStaticLoading && errorMessage === null ? (
          <svg
            ref={svgRef}
            role="img"
            aria-label={`Topology canvas for office ${officeId}`}
            data-testid="topology-canvas"
            viewBox={VIEW_BOX}
            preserveAspectRatio="xMidYMid meet"
            className="h-full w-full select-none"
            onMouseDown={handleMouseDown}
            onWheel={handleWheel}
          >
            <TopologyGlowDefs />

            {/* subtle grid backdrop — purely cosmetic, no role in tests */}
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
              {resolvedCorridors.map((entry) => (
                <CorridorView
                  key={entry.corridor.id}
                  entry={entry}
                  isActive={activeCorridors.has(entry.corridor.id)}
                  now={now}
                />
              ))}

              {nodes.map((node) => (
                <NodeView key={`${node.kind}:${node.id}`} node={node} onClick={handleNodeClick} />
              ))}
            </g>
          </svg>
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
};

function NodeView({ node, onClick }: NodeViewProps): ReactElement {
  const haloOpacity = intensityOpacity(node.glowIntensity);
  const coreStrokeOpacity = intensityStrokeOpacity(node.glowIntensity);
  const isUser = node.kind === 'membership' && node.fillColor === DEFAULT_USER_FILL;
  const tooltip = `${node.label} | ${node.role} | ${node.status}`;
  const Icon = isUser ? User : Bot;

  return (
    /* biome-ignore lint/a11y/noStaticElementInteractions: SVG <g> has no semantic <button> */
    <g
      data-testid={`topology-node-${node.id}`}
      data-topology-node="true"
      data-node-kind={node.kind}
      transform={`translate(${node.x} ${node.y})`}
      className="cursor-pointer"
      onClick={(event) => {
        event.stopPropagation();
        onClick(node);
      }}
    >
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
        stroke={node.glowColor}
        strokeOpacity={coreStrokeOpacity}
        strokeWidth={CORE_STROKE_WIDTH}
        data-testid={`topology-node-core-${node.id}`}
      />
      <foreignObject x={-12} y={-12} width={24} height={24}>
        <div
          className="flex h-full w-full items-center justify-center text-slate-800"
          aria-hidden="true"
        >
          <Icon size={20} strokeWidth={2} />
        </div>
      </foreignObject>
      <title>{tooltip}</title>
    </g>
  );
}

type CorridorViewProps = {
  readonly entry: ResolvedCorridor;
  readonly isActive: boolean;
  readonly now: number;
};

function CorridorView({ entry, isActive, now }: CorridorViewProps): ReactElement {
  const { corridor, from, to } = entry;
  const stroke = isActive ? ACTIVE_STROKE : DEFAULT_STROKE;
  const strokeWidth = isActive ? ACTIVE_STROKE_WIDTH : DEFAULT_STROKE_WIDTH;

  return (
    <g data-testid={`topology-corridor-${corridor.id}`} data-corridor-id={corridor.id}>
      <line
        x1={from.x}
        y1={from.y}
        x2={to.x}
        y2={to.y}
        stroke={stroke}
        strokeWidth={strokeWidth}
        data-testid={`topology-corridor-line-${corridor.id}`}
        data-active={isActive ? 'true' : 'false'}
      />
      {isActive ? (
        <ParticleView corridorId={corridor.id} from={from} to={to} startedAt={now} />
      ) : null}
    </g>
  );
}

type ParticleViewProps = {
  readonly corridorId: string;
  readonly from: ResolvedEndpoint;
  readonly to: ResolvedEndpoint;
  readonly startedAt: number;
};

function ParticleView({ corridorId, from, to, startedAt }: ParticleViewProps): ReactElement {
  const path = `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
  return (
    <circle
      r={5}
      fill={ACTIVE_STROKE}
      data-testid={`topology-corridor-particle-${corridorId}`}
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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resolveEndpoint(
  membershipId: string | null,
  corridorNodeId: string | null,
  membershipById: ReadonlyMap<string, Membership>,
  corridorNodeById: ReadonlyMap<string, CorridorNodeModel>,
): ResolvedEndpoint | null {
  if (membershipId !== null) {
    const m = membershipById.get(membershipId);
    if (m === undefined) return null;
    return { kind: 'membership', id: m.id, x: m.posx, y: m.posy };
  }
  if (corridorNodeId !== null) {
    const cn = corridorNodeById.get(corridorNodeId);
    if (cn === undefined) return null;
    return { kind: 'corridor_node', id: cn.id, x: cn.posx, y: cn.posy, label: cn.display_name };
  }
  return null;
}

function clamp(value: number, min: number, max: number): number {
  if (value < min) return min;
  if (value > max) return max;
  return value;
}
