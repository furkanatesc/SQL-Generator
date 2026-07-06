// Sinaptik arka plan ağının veri kaynağı: gerçek şema graph'ı varsa
// selectGraphData ile (yalnız bağlantılı tablolar, hub-öncelikli, üst sınırlı),
// yoksa seed'li prosedürel küçük-dünya ağı. Arka plan asla boş kalmaz.
import { selectGraphData, type GraphEdgeInput } from './graphSelection.ts';
import { mulberry32 } from './seededRandom.ts';

export interface SynapseGraphEdge { source: string; target: string }

export interface SynapseGraph {
  nodes: string[];
  edges: SynapseGraphEdge[];
  isFallback: boolean;
}

export const SYNAPSE_MAX_NODES = 150;
export const FALLBACK_NODE_COUNT = 60;
export const FALLBACK_CHORD_COUNT = 30;
const FALLBACK_SEED = 0x53514c67;

export function buildFallbackGraph(): SynapseGraph {
  const rand = mulberry32(FALLBACK_SEED);
  const nodes = Array.from({ length: FALLBACK_NODE_COUNT }, (_, i) => `synapse_${i}`);
  const edges: SynapseGraphEdge[] = [];
  for (let i = 0; i < FALLBACK_NODE_COUNT; i++) {
    edges.push({ source: nodes[i], target: nodes[(i + 1) % FALLBACK_NODE_COUNT] });
  }
  const seen = new Set<string>();
  while (seen.size < FALLBACK_CHORD_COUNT) {
    const a = Math.floor(rand() * FALLBACK_NODE_COUNT);
    const b = Math.floor(rand() * FALLBACK_NODE_COUNT);
    const gap = Math.abs(a - b);
    if (a === b || gap === 1 || gap === FALLBACK_NODE_COUNT - 1) continue;
    const key = a < b ? `${a}-${b}` : `${b}-${a}`;
    if (seen.has(key)) continue;
    seen.add(key);
    edges.push({ source: nodes[Math.min(a, b)], target: nodes[Math.max(a, b)] });
  }
  return { nodes, edges, isFallback: true };
}

export function buildSynapseGraph(
  schemaGraph: { nodes?: string[]; edges?: GraphEdgeInput[] } | null | undefined,
  maxNodes: number = SYNAPSE_MAX_NODES
): SynapseGraph {
  const nodes = schemaGraph?.nodes ?? [];
  const edges = schemaGraph?.edges ?? [];
  if (nodes.length >= 2 && edges.length >= 1) {
    const selection = selectGraphData(nodes, edges, maxNodes);
    if (selection.nodes.length >= 2 && selection.edges.length >= 1) {
      return {
        nodes: selection.nodes,
        edges: selection.edges.map((e) => ({ source: e.source, target: e.target })),
        isFallback: false,
      };
    }
  }
  return buildFallbackGraph();
}
