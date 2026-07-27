/**
 * TopologyGlow — reusable SVG `<defs>` block with a Gaussian blur
 * filter that turns any stroked circle into a soft halo.
 *
 * The component is intentionally stateless and side-effect free: it
 * just emits a `<defs>` fragment once at the top of the topology SVG
 * so all nodes can reference it via `filter="url(#topology-glow-blur)"`.
 *
 * Visual model (matches the P9 plan, "outer ring + blur" option):
 *
 *     <circle r="40" fill="agent_color" stroke="glow_color" />          <- core
 *     <circle r="50" fill="none" stroke="glow_color"
 *             stroke-opacity={intensity} stroke-width={6}
 *             filter="url(#topology-glow-blur)" />                       <- halo
 *
 * The blur (stdDeviation=5) on a wide translucent stroke produces
 * a glowing halo whose visual size scales with stroke-width and
 * whose intensity tracks `stroke-opacity`. Five discrete intensity
 * buckets (static / weak / low / medium / strong) are mapped to
 * numeric opacity by the consumer; this component only provides
 * the filter primitive.
 *
 * No new npm dependencies. No React Flow, D3, or cytoscape — pure
 * SVG as the plan mandates.
 */
export default function TopologyGlowDefs() {
  return (
    <defs>
      <filter
        id="topology-glow-blur"
        x="-50%"
        y="-50%"
        width="200%"
        height="200%"
        filterUnits="objectBoundingBox"
      >
        <feGaussianBlur stdDeviation="5" />
      </filter>
    </defs>
  );
}

/**
 * Discrete intensity -> numeric stroke-opacity mapping.
 *
 * The P9 glow helper (cocoa-backend/app/core/glow.py) emits a
 * `GlowColor` with intensity ∈ {"static", "weak", "low", "medium",
 * "strong"}. The topology viz renders this as a halo opacity:
 *
 *   static  -> invisible (no halo)
 *   weak    -> very faint (0.20)
 *   low     -> subtle      (0.40)
 *   medium  -> readable    (0.65)
 *   strong  -> bold        (0.95)
 *
 * The mapping is intentionally monotone and never reaches 1.0 so the
 * halo always reads as a glow and not a solid ring.
 */
export const GLOW_INTENSITY_OPACITY = {
  static: 0,
  weak: 0.2,
  low: 0.4,
  medium: 0.65,
  strong: 0.95,
} as const;
