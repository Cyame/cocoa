/**
 * Compute pan/zoom so all nodes fit in the topology viewBox (centered at 0,0).
 */

export type FitPoint = {
  readonly x: number;
  readonly y: number;
};

export type FitViewport = {
  readonly panX: number;
  readonly panY: number;
  readonly zoom: number;
};

export function fitNodes(
  nodes: readonly FitPoint[],
  options?: {
    readonly viewSize?: number;
    readonly padding?: number;
    readonly nodePad?: number;
    readonly minZoom?: number;
    readonly maxZoom?: number;
  },
): FitViewport {
  const viewSize = options?.viewSize ?? 2000;
  const padding = options?.padding ?? 0.15;
  const nodePad = options?.nodePad ?? 80;
  const minZoom = options?.minZoom ?? 0.2;
  const maxZoom = options?.maxZoom ?? 4;

  if (nodes.length === 0) {
    return { panX: 0, panY: 0, zoom: 1 };
  }

  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const n of nodes) {
    minX = Math.min(minX, n.x);
    maxX = Math.max(maxX, n.x);
    minY = Math.min(minY, n.y);
    maxY = Math.max(maxY, n.y);
  }

  minX -= nodePad;
  maxX += nodePad;
  minY -= nodePad;
  maxY += nodePad;

  const w = Math.max(maxX - minX, 1);
  const h = Math.max(maxY - minY, 1);
  let zoom = Math.min(viewSize / w, viewSize / h) * (1 - padding);
  zoom = Math.min(maxZoom, Math.max(minZoom, zoom));

  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  return {
    panX: -cx * zoom,
    panY: -cy * zoom,
    zoom,
  };
}
