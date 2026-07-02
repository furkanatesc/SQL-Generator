// Şema graph'ı için node/edge seçim mantığı.
// İzole (ilişkisiz) tablolar çizilmez: binlerce tablolu şemalarda tarayıcıyı
// donduran şey izole node kalabalığıydı; ilişki graph'ına bilgi de katmıyorlar.
export interface GraphEdgeInput {
  source: string;
  target: string;
  source_col: string;
  target_col: string;
  type?: string;
}

export interface GraphSelection {
  /** Çizilecek tablolar, degree'ye göre azalan sırada */
  nodes: string[];
  /** İki ucu da seçilen tablolar arasında kalan ilişkiler */
  edges: GraphEdgeInput[];
  /** Hiç ilişkisi olmadığı için gizlenen tablo sayısı */
  isolatedCount: number;
  /** Limit uygulanmadan önceki bağlantılı tablo sayısı */
  totalConnected: number;
}

export function selectGraphData(
  nodes: string[],
  edges: GraphEdgeInput[],
  maxNodes: number
): GraphSelection {
  const nodeSet = new Set(nodes);
  const degrees = new Map<string, number>();

  const validEdges = edges.filter(
    (e) => nodeSet.has(e.source) && nodeSet.has(e.target)
  );
  for (const e of validEdges) {
    degrees.set(e.source, (degrees.get(e.source) || 0) + 1);
    degrees.set(e.target, (degrees.get(e.target) || 0) + 1);
  }

  const connected = nodes
    .filter((n) => (degrees.get(n) || 0) > 0)
    .sort((a, b) => (degrees.get(b) || 0) - (degrees.get(a) || 0));

  const selected = maxNodes > 0 ? connected.slice(0, maxNodes) : connected;
  const selectedSet = new Set(selected);

  return {
    nodes: selected,
    // Kopya döndür: d3.forceLink source/target alanlarını node objesine çevirir,
    // orijinal şema verisi mutasyondan korunmalı.
    edges: validEdges
      .filter((e) => selectedSet.has(e.source) && selectedSet.has(e.target))
      .map((e) => ({ ...e })),
    isolatedCount: nodes.length - connected.length,
    totalConnected: connected.length,
  };
}
