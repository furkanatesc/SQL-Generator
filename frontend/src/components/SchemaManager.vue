<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick, onUnmounted } from 'vue';
import { apiService } from '../services/api';
import * as d3 from 'd3';
import PlanetDbSelector from './PlanetDbSelector.vue';

interface NodeItem extends d3.SimulationNodeDatum {
  id: string;
}

interface LinkItem extends d3.SimulationLinkDatum<NodeItem> {
  source: string | NodeItem;
  target: string | NodeItem;
  source_col: string;
  target_col: string;
  type?: string;
}

const schema = ref<any>(null);
const loading = ref(false);
const expandedTable = ref<string | null>(null);
const targetDbType = ref('sqlite');
const targetDbName = ref('');
const showIncoming = ref(false);
const isHidingElements = ref(false);
const isGraphExpanded = ref(false);
const isPhysicsActive = ref(true);
const maxNodesLimit = ref(5); // GECICI COZUM: Tarayıcı performansını korumak için geçici olarak sadece 5 tablo render ediliyor (0 = Limitsiz)
const visibleTablesLimit = ref(50); // Sol paneldeki tabloların lazy-loading limiti
const visibleRelationsLimit = ref(50); // Sağ paneldeki ilişkilerin lazy-loading limiti

const isTransitioning = ref(false);

const toggleGraphExpand = () => {
  isTransitioning.value = true;
  if (!isGraphExpanded.value) {
    const mainEl = document.getElementById('main-scroll-container');
    if (mainEl) mainEl.scrollTo({ top: 0, behavior: 'smooth' });
    
    isHidingElements.value = true;
    
    setTimeout(() => {
      isGraphExpanded.value = true;
      setTimeout(() => {
        handleResize();
        setTimeout(() => {
          isTransitioning.value = false;
        }, 100);
      }, 750);
    }, 450);
  } else {
    isGraphExpanded.value = false;
    
    setTimeout(() => {
      isHidingElements.value = false;
      setTimeout(() => {
        handleResize();
        setTimeout(() => {
          isTransitioning.value = false;
        }, 100);
      }, 750);
    }, 600);
  }
};

// SVG ve D3 referansları
const svgRef = ref<SVGSVGElement | null>(null);
let simulation: d3.Simulation<NodeItem, LinkItem> | null = null;
let zoomBehavior: d3.ZoomBehavior<SVGSVGElement, unknown> | null = null;

// Özel ve devre dışı bırakılmış ilişkilerin reaktif durumları
const customRelations = ref<any[]>([]);
const disabledRelations = ref<any[]>([]);

// Tüm ilişkileri birleştiren computed property (Açık, Örtük, Özel ve Pasifler) - Optimize edilmiş O(N) lookup
const allRelations = computed(() => {
  if (!schema.value) return [];
  const list: any[] = [];
  
  // 1. Aktif ilişkileri ekle (şemadaki edges)
  const activeEdges = schema.value.graph?.edges || [];
  const activeKeys = new Set<string>();
  
  activeEdges.forEach((edge: any) => {
    const key1 = `${edge.source}:${edge.source_col}->${edge.target}:${edge.target_col}`;
    const key2 = `${edge.target}:${edge.target_col}->${edge.source}:${edge.source_col}`;
    activeKeys.add(key1);
    activeKeys.add(key2);
    
    list.push({
      source: edge.source,
      source_col: edge.source_col,
      target: edge.target,
      target_col: edge.target_col,
      type: edge.type || 'explicit',
      disabled: false
    });
  });
  
  // 2. Devre dışı bırakılmış ilişkileri ekle
  const customKeys = new Set<string>();
  customRelations.value.forEach((cr: any) => {
    const key1 = `${cr.source}:${cr.source_col}->${cr.target}:${cr.target_col}`;
    const key2 = `${cr.target}:${cr.target_col}->${cr.source}:${cr.source_col}`;
    customKeys.add(key1);
    customKeys.add(key2);
  });

  disabledRelations.value.forEach((dr: any) => {
    if (!schema.value.tables[dr.source] || !schema.value.tables[dr.target]) return;
    
    const key1 = `${dr.source}:${dr.source_col}->${dr.target}:${dr.target_col}`;
    const key2 = `${dr.target}:${dr.target_col}->${dr.source}:${dr.source_col}`;
    
    if (!activeKeys.has(key1)) {
      const isCustom = customKeys.has(key1);
      list.push({
        source: dr.source,
        source_col: dr.source_col,
        target: dr.target,
        target_col: dr.target_col,
        type: isCustom ? 'custom' : 'implicit',
        disabled: true
      });
      // Dublikasyonu önlemek için listeye eklenenleri işaretle
      activeKeys.add(key1);
      activeKeys.add(key2);
    }
  });
  
  return list;
});

// Performans optimizasyonu: Tablolara gelen ilişkileri (FK) önceden eşleyen computed map - O(1) arama sağlar
const incomingRelationsMap = computed(() => {
  const map: Record<string, any[]> = {};
  if (!schema.value || !schema.value.tables) return map;
  
  for (const [sourceTable, meta] of Object.entries(schema.value.tables)) {
    const fks = (meta as any).foreign_keys || [];
    for (const fk of fks) {
      const refTbl = fk.referenced_table;
      if (!map[refTbl]) {
        map[refTbl] = [];
      }
      map[refTbl].push({
        source_table: sourceTable,
        source_column: fk.column,
        target_column: fk.referenced_column
      });
    }
  }
  return map;
});

const visibleTables = computed(() => {
  if (!schema.value || !schema.value.tables) return {};
  const entries = Object.entries(schema.value.tables);
  return Object.fromEntries(entries.slice(0, visibleTablesLimit.value));
});

const totalTablesCount = computed(() => {
  if (!schema.value || !schema.value.tables) return 0;
  return Object.keys(schema.value.tables).length;
});

const loadMoreTables = () => {
  visibleTablesLimit.value += 50;
};

const visibleRelations = computed(() => {
  return allRelations.value.slice(0, visibleRelationsLimit.value);
});

const loadMoreRelations = () => {
  visibleRelationsLimit.value += 50;
};

const validCustomRelations = computed(() => {
  if (!schema.value || !schema.value.tables) return [];
  return customRelations.value.filter(cr => 
    schema.value.tables[cr.source] && schema.value.tables[cr.target]
  );
});

// Form kontrol durumları
const newSourceTable = ref('');
const newSourceColumn = ref('');
const newTargetTable = ref('');
const newTargetColumn = ref('');
const sourceColumns = ref<any[]>([]);
const targetColumns = ref<any[]>([]);

// Performans için arama tabanlı filtreleme parametreleri
const sourceTableSearch = ref('');
const targetTableSearch = ref('');

const searchFilteredSourceTables = computed(() => {
  if (!schema.value || !schema.value.tables) return [];
  const allNames = Object.keys(schema.value.tables);
  if (!sourceTableSearch.value) {
    return allNames.slice(0, 100); // 2000 tabloda tarayıcı kasmasını önlemek için varsayılan 100 node limiti
  }
  const query = sourceTableSearch.value.toLowerCase();
  return allNames.filter(name => name.toLowerCase().includes(query)).slice(0, 100);
});

const searchFilteredTargetTables = computed(() => {
  if (!schema.value || !schema.value.tables) return [];
  const allNames = Object.keys(schema.value.tables);
  if (!targetTableSearch.value) {
    return allNames.slice(0, 100); // 2000 tabloda tarayıcı kasmasını önlemek için varsayılan 100 node limiti
  }
  const query = targetTableSearch.value.toLowerCase();
  return allNames.filter(name => name.toLowerCase().includes(query)).slice(0, 100);
});

watch(newSourceTable, (newVal) => {
  if (schema.value && schema.value.tables[newVal]) {
    sourceColumns.value = schema.value.tables[newVal].columns;
    newSourceColumn.value = sourceColumns.value[0]?.name || '';
  } else {
    sourceColumns.value = [];
    newSourceColumn.value = '';
  }
});

watch(newTargetTable, (newVal) => {
  if (schema.value && schema.value.tables[newVal]) {
    targetColumns.value = schema.value.tables[newVal].columns;
    newTargetColumn.value = targetColumns.value[0]?.name || '';
  } else {
    targetColumns.value = [];
    newTargetColumn.value = '';
  }
});

const loadRelations = async () => {
  try {
    const crRes = await apiService.getCustomRelations();
    customRelations.value = crRes.relations || [];
    
    const drRes = await apiService.getDisabledRelations();
    disabledRelations.value = drRes.relations || [];
  } catch (e) {
    console.error('İlişki ayarları yüklenemedi', e);
  }
};

const isRelationDisabled = (source: string, sourceCol: string, target: string, targetCol: string) => {
  return disabledRelations.value.some(r => 
    (r.source === source && r.source_col === sourceCol && r.target === target && r.target_col === targetCol) ||
    (r.source === target && r.source_col === targetCol && r.target === source && r.target_col === sourceCol)
  );
};

const toggleRelationStatus = async (rel: any) => {
  const isDisabled = isRelationDisabled(rel.source, rel.source_col, rel.target, rel.target_col);
  
  if (isDisabled) {
    disabledRelations.value = disabledRelations.value.filter(r => 
      !(
        (r.source === rel.source && r.source_col === rel.source_col && r.target === rel.target && r.target_col === rel.target_col) ||
        (r.source === rel.target && r.source_col === rel.target_col && r.target === rel.source && r.target_col === rel.source_col)
      )
    );
  } else {
    disabledRelations.value.push({
      source: rel.source,
      source_col: rel.source_col,
      target: rel.target,
      target_col: rel.target_col
    });
  }
  
  try {
    await apiService.saveDisabledRelations(disabledRelations.value);
    await loadSchema();
  } catch (e) {
    console.error('İlişki aktifliği değiştirilemedi', e);
  }
};

const addCustomRelation = async () => {
  if (!newSourceTable.value || !newSourceColumn.value || !newTargetTable.value || !newTargetColumn.value) return;
  
  if (newSourceTable.value === newTargetTable.value && newSourceColumn.value === newTargetColumn.value) {
    alert('Aynı kolonu kendisiyle bağlayamazsınız!');
    return;
  }
  
  const exists = customRelations.value.some(r => 
    (r.source === newSourceTable.value && r.source_col === newSourceColumn.value && r.target === newTargetTable.value && r.target_col === newTargetColumn.value) ||
    (r.source === newTargetTable.value && r.source_col === newTargetColumn.value && r.target === newSourceTable.value && r.target_col === newSourceColumn.value)
  );
  
  if (exists) {
    alert('Bu özel bağlantı zaten tanımlanmış!');
    return;
  }
  
  customRelations.value.push({
    source: newSourceTable.value,
    source_col: newSourceColumn.value,
    target: newTargetTable.value,
    target_col: newTargetColumn.value
  });
  
  try {
    await apiService.saveCustomRelations(customRelations.value);
    newSourceTable.value = '';
    newSourceColumn.value = '';
    newTargetTable.value = '';
    newTargetColumn.value = '';
    await loadSchema();
  } catch (e) {
    console.error('Özel bağlantı eklenemedi', e);
  }
};

const deleteCustomRelation = async (rel: any) => {
  customRelations.value = customRelations.value.filter(r => 
    !(
      (r.source === rel.source && r.source_col === rel.source_col && r.target === rel.target && r.target_col === rel.target_col) ||
      (r.source === rel.target && r.source_col === rel.target_col && r.target === rel.source && r.target_col === rel.source_col)
    )
  );
  
  try {
    await apiService.saveCustomRelations(customRelations.value);
    await loadSchema();
  } catch (e) {
    console.error('Özel bağlantı silinemedi', e);
  }
};

const loadSchema = async (force = false) => {
  loading.value = true;
  try {
    const typeRes = await apiService.getConfig('target_db_type');
    targetDbType.value = typeRes.value || 'sqlite';
    
    if (targetDbType.value === 'postgres') {
      const dbRes = await apiService.getConfig('target_pg_db');
      targetDbName.value = dbRes.value || 'postgres';
    } else if (targetDbType.value === 'oracle') {
      const dbRes = await apiService.getConfig('target_oracle_service');
      targetDbName.value = dbRes.value || 'ORCLPDB1';
    } else {
      const pathRes = await apiService.getConfig('target_sqlite_path');
      const parts = (pathRes.value || '').split(/[/\\]/);
      targetDbName.value = parts[parts.length - 1] || 'target_test.db';
    }

    const res = force ? await apiService.refreshSchema() : await apiService.getSchema();
    schema.value = res.schema || null;
  } catch (e: any) {
    console.error('Schema load failed', e);
  } finally {
    loading.value = false;
  }
};

const onDialectChange = async (newDialect: string) => {
  try {
    await apiService.setConfig('target_db_type', newDialect);
    await loadSchema(true);
  } catch (e) {
    console.warn('Dialect config set failed', e);
  }
};

const toggleTable = (tableName: string) => {
  if (expandedTable.value === tableName) {
    expandedTable.value = null;
  } else {
    expandedTable.value = tableName;
    showIncoming.value = false;
  }
};

const getIncomingRelations = (targetTableName: string) => {
  return incomingRelationsMap.value[targetTableName] || [];
};

// D3.js Şema Grafik Çizimi
const initGraph = () => {
  if (!svgRef.value || !schema.value || !schema.value.graph) return;

  const containerElement = svgRef.value.parentElement;
  const width = containerElement ? containerElement.clientWidth : 500;
  const height = containerElement ? containerElement.clientHeight : 400;

  // SVG temizliği
  const svg = d3.select(svgRef.value);
  svg.selectAll('*').remove();

  // D3 mutasyonundan korumak için derin kopya alalım, ve maxNodesLimit ile sınırlandıralım
  const MAX_NODES = maxNodesLimit.value;
  
  // Önce en çok bağlantısı olan (hub) tabloları bulalım
  const nodeDegrees: Record<string, number> = {};
  schema.value.graph.edges.forEach((edge: any) => {
    nodeDegrees[edge.source] = (nodeDegrees[edge.source] || 0) + 1;
    nodeDegrees[edge.target] = (nodeDegrees[edge.target] || 0) + 1;
  });

  // Tabloları bağlantı sayısına göre sıralayalım
  const sortedNodes = [...schema.value.graph.nodes].sort((a, b) => (nodeDegrees[b] || 0) - (nodeDegrees[a] || 0));
  
  // Eğer MAX_NODES 0'dan büyükse sınırla, değilse (0 veya boşsa) hepsini al
  const topNodes = MAX_NODES > 0 ? sortedNodes.slice(0, MAX_NODES) : sortedNodes;
  const topNodesSet = new Set(topNodes);

  const nodesData: NodeItem[] = topNodes.map((table: string) => ({ id: table }));
  const linksData: LinkItem[] = schema.value.graph.edges
    .filter((edge: any) => topNodesSet.has(edge.source) && topNodesSet.has(edge.target))
    .map((edge: any) => ({
      source: edge.source,
      target: edge.target,
      source_col: edge.source_col,
      target_col: edge.target_col,
      type: edge.type || 'explicit'
    }));

  if (nodesData.length === 0) return;

  // Marker ve Efektlerin Tanımlanması (Defs)
  const defs = svg.append('defs');
  
  // Yön Okları
  defs.append('marker')
    .attr('id', 'arrow')
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 24) // Düğüm merkezinden ok ucu mesafesi
    .attr('refY', 0)
    .attr('markerWidth', 6)
    .attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-3L8,0L0,3')
    .attr('fill', '#818cf8'); // Indigo 400

  // Neon Parlama Filtresi
  const filter = defs.append('filter')
    .attr('id', 'glow')
    .attr('x', '-30%')
    .attr('y', '-30%')
    .attr('width', '160%')
    .attr('height', '160%');
  
  filter.append('feGaussianBlur')
    .attr('stdDeviation', '4')
    .attr('result', 'blur');
  
  filter.append('feComposite')
    .attr('in', 'SourceGraphic')
    .attr('in2', 'blur')
    .attr('operator', 'over');

  // Radial Gradients for the Black Hole Singularity and Accretion Disk
  const radialGrad = defs.append('radialGradient')
    .attr('id', 'singularity-gradient')
    .attr('cx', '50%')
    .attr('cy', '50%')
    .attr('r', '50%');
  radialGrad.append('stop')
    .attr('offset', '0%')
    .attr('stop-color', '#000000');
  radialGrad.append('stop')
    .attr('offset', '70%')
    .attr('stop-color', '#09090b');
  radialGrad.append('stop')
    .attr('offset', '100%')
    .attr('stop-color', '#818cf8')
    .attr('stop-opacity', '0.4');

  const accretionGrad = defs.append('radialGradient')
    .attr('id', 'accretion-gradient')
    .attr('cx', '50%')
    .attr('cy', '50%')
    .attr('r', '50%');
  accretionGrad.append('stop')
    .attr('offset', '0%')
    .attr('stop-color', '#c084fc')
    .attr('stop-opacity', '0.8');
  accretionGrad.append('stop')
    .attr('offset', '40%')
    .attr('stop-color', '#818cf8')
    .attr('stop-opacity', '0.4');
  accretionGrad.append('stop')
    .attr('offset', '80%')
    .attr('stop-color', '#fbbf24')
    .attr('stop-opacity', '0.15');
  accretionGrad.append('stop')
    .attr('offset', '100%')
    .attr('stop-color', '#000000')
    .attr('stop-opacity', '0');

  // Intense neon black hole glow filter
  const bhGlow = defs.append('filter')
    .attr('id', 'black-hole-glow')
    .attr('x', '-50%')
    .attr('y', '-50%')
    .attr('width', '200%')
    .attr('height', '200%');
  bhGlow.append('feGaussianBlur')
    .attr('stdDeviation', '10')
    .attr('result', 'blur');
  bhGlow.append('feComponentTransfer')
    .append('feFuncA')
    .attr('type', 'linear')
    .attr('slope', '2');
  bhGlow.append('feMerge').selectAll('feMergeNode')
    .data(['blur', 'SourceGraphic'])
    .enter()
    .append('feMergeNode')
    .attr('in', (d: string) => d);

  // Grafik Ana Kapsayıcı Grubu (Zoom/Pan için)
  const gContainer = svg.append('g').attr('class', 'graph-container');

  // Spacetime Coordinate Grid Group (Background, inside zoomable container)
  const gridGroup = gContainer.append('g')
    .attr('class', 'spacetime-grid')
    .style('pointer-events', 'none');

  const centerX = width / 2;
  const centerY = height / 2;
  const gridSpacing = 50;
  const warpRange = 220;
  const warpStrength = 0.65;

  const getWarpedVerticalPath = (x: number) => {
    let points: string[] = [];
    const steps = 40;
    for (let i = 0; i <= steps; i++) {
      const y = (i / steps) * height * 1.5 - height * 0.25;
      const dx = x - centerX;
      const dy = y - centerY;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const warp = 1 - warpStrength * Math.exp(-(dist * dist) / (2 * warpRange * warpRange));
      const wx = centerX + dx * warp;
      const wy = centerY + dy * warp;
      points.push(`${wx.toFixed(1)},${wy.toFixed(1)}`);
    }
    return 'M' + points.join(' L');
  };

  const getWarpedHorizontalPath = (y: number) => {
    let points: string[] = [];
    const steps = 40;
    for (let i = 0; i <= steps; i++) {
      const x = (i / steps) * width * 1.5 - width * 0.25;
      const dx = x - centerX;
      const dy = y - centerY;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const warp = 1 - warpStrength * Math.exp(-(dist * dist) / (2 * warpRange * warpRange));
      const wx = centerX + dx * warp;
      const wy = centerY + dy * warp;
      points.push(`${wx.toFixed(1)},${wy.toFixed(1)}`);
    }
    return 'M' + points.join(' L');
  };

  const minX = -width * 0.25;
  const maxX = width * 1.25;
  const minY = -height * 0.25;
  const maxY = height * 1.25;

  for (let x = Math.floor(minX / gridSpacing) * gridSpacing; x <= maxX; x += gridSpacing) {
    gridGroup.append('path')
      .attr('d', getWarpedVerticalPath(x))
      .attr('fill', 'none')
      .attr('stroke', '#4f46e5')
      .attr('stroke-width', 0.5)
      .attr('opacity', 0.12);
  }
  for (let y = Math.floor(minY / gridSpacing) * gridSpacing; y <= maxY; y += gridSpacing) {
    gridGroup.append('path')
      .attr('d', getWarpedHorizontalPath(y))
      .attr('fill', 'none')
      .attr('stroke', '#4f46e5')
      .attr('stroke-width', 0.5)
      .attr('opacity', 0.12);
  }

  for (let r = 50; r <= 350; r += 50) {
    gridGroup.append('circle')
      .attr('cx', centerX)
      .attr('cy', centerY)
      .attr('r', r)
      .attr('fill', 'none')
      .attr('stroke', '#c084fc')
      .attr('stroke-width', 0.5)
      .attr('opacity', Math.max(0.02, 0.15 - (r / 350) * 0.12))
      .attr('stroke-dasharray', '4 4');
  }

  // Central Black Hole Group
  const blackHoleGroup = gContainer.append('g')
    .attr('class', 'black-hole-group')
    .attr('transform', `translate(${centerX}, ${centerY})`);

  // Swirling space dust particles inside D3 coordinate system (centered on the black hole)
  const dustGroup = blackHoleGroup.append('g')
    .attr('class', 'dust-particles-group')
    .style('pointer-events', 'none');
  for (let i = 0; i < 50; i++) {
    const radius = 30 + Math.random() * 200; // spread from 30px to 230px
    const angle = Math.random() * 2 * Math.PI;
    const x = radius * Math.cos(angle);
    const y = radius * Math.sin(angle);
    const size = 0.8 + Math.random() * 2.2;
    
    let color = '#818cf8'; // Indigo
    if (i % 3 === 0) color = '#fbbf24'; // Amber
    else if (i % 3 === 1) color = '#22d3ee'; // Cyan

    dustGroup.append('circle')
      .attr('cx', x.toFixed(1))
      .attr('cy', y.toFixed(1))
      .attr('r', size.toFixed(1))
      .attr('fill', color)
      .attr('opacity', (0.3 + Math.random() * 0.45).toFixed(2))
      .attr('class', 'dust-particle')
      .style('animation-delay', `${(-Math.random() * 20).toFixed(1)}s`)
      .style('animation-duration', `${6 + Math.random() * 10}s`)
      .style('pointer-events', 'none')
      .style('filter', 'url(#glow)');
  }

  blackHoleGroup.append('circle')
    .attr('r', 180)
    .attr('fill', 'url(#accretion-gradient)')
    .style('pointer-events', 'none')
    .attr('class', 'accretion-disk-aura');

  const getSpiralPath = (a: number, b: number, startAngle: number) => {
    let points: string[] = [];
    const numPoints = 80;
    for (let i = 0; i < numPoints; i++) {
      const theta = startAngle - (i * 0.08);
      const r = a * Math.exp(b * (i * 0.08));
      if (r < 10) break;
      const x = r * Math.cos(theta);
      const y = r * Math.sin(theta);
      points.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    }
    return 'M' + points.join(' L');
  };

  for (let i = 0; i < 4; i++) {
    const angle = (i * Math.PI) / 2;
    blackHoleGroup.append('path')
      .attr('d', getSpiralPath(180, -0.32, angle))
      .attr('fill', 'none')
      .attr('stroke', i % 2 === 0 ? '#fbbf24' : '#c084fc')
      .attr('stroke-width', 1.5 + Math.random() * 1.5)
      .attr('opacity', 0.45)
      .attr('class', `vortex-spiral-arm vortex-spiral-${i + 1}`)
      .style('pointer-events', 'none')
      .style('filter', 'url(#glow)');
  }

  blackHoleGroup.append('circle')
    .attr('r', 120)
    .attr('fill', 'none')
    .attr('stroke', '#a855f7')
    .attr('stroke-width', 1.5)
    .attr('stroke-dasharray', '80 40 120 30')
    .attr('opacity', 0.4)
    .attr('class', 'vortex-ring-outer')
    .style('pointer-events', 'none')
    .style('filter', 'url(#glow)');

  blackHoleGroup.append('circle')
    .attr('r', 75)
    .attr('fill', 'none')
    .attr('stroke', '#f59e0b')
    .attr('stroke-width', 2)
    .attr('stroke-dasharray', '60 30 90 20')
    .attr('opacity', 0.65)
    .attr('class', 'vortex-ring-middle')
    .style('pointer-events', 'none')
    .style('filter', 'url(#glow)');

  blackHoleGroup.append('circle')
    .attr('r', 45)
    .attr('fill', 'none')
    .attr('stroke', '#fb7185')
    .attr('stroke-width', 2.5)
    .attr('stroke-dasharray', '30 15 45 10')
    .attr('opacity', 0.75)
    .attr('class', 'vortex-ring-inner')
    .style('pointer-events', 'none')
    .style('filter', 'url(#glow)');

  blackHoleGroup.append('circle')
    .attr('r', 25)
    .attr('fill', 'url(#singularity-gradient)')
    .attr('stroke', '#818cf8')
    .attr('stroke-width', 2)
    .attr('class', 'singularity-core')
    .style('filter', 'url(#black-hole-glow)')
    .style('cursor', 'pointer')
    .on('click', () => {
      if (simulation) {
        simulation.alpha(0.8);
        nodesData.forEach((n: any) => {
          n.vx += (Math.random() - 0.5) * 50;
          n.vy += (Math.random() - 0.5) * 50;
        });
        simulation.restart();
      }
    });

  // İlişki Çizgileri Grubu
  const linkGroup = gContainer.append('g').attr('class', 'links');
  
  // Tablo Düğümleri Grubu
  const nodeGroup = gContainer.append('g').attr('class', 'nodes');

  // Zoom & Pan Davranışı
  zoomBehavior = d3.zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.15, 3])
    .on('zoom', (event) => {
      gContainer.attr('transform', event.transform);
    });

  svg.call(zoomBehavior);

  // Engelle: Mouse SVG üzerindeyken scroll yapıldığında sayfanın da beraberinde kaymasını ve titremesini önle
  svg.on('wheel', (event) => {
    event.stopPropagation();
  });

  // Fizik Motoru Kurulumu - Accretion radial forces keep nodes centered perfectly
  simulation = d3.forceSimulation<NodeItem>(nodesData)
    .force('link', d3.forceLink<NodeItem, LinkItem>(linksData).id((d: any) => d.id).distance(120).strength(0.2))
    .force('charge', d3.forceManyBody().strength(-200))
    .force('radial', d3.forceRadial(140, width / 2, height / 2).strength(0.35))
    .force('collide', d3.forceCollide().radius(55));

  // Kenarları (Edges) Çiz
  const links = linkGroup.selectAll('g.link-item')
    .data(linksData)
    .enter()
    .append('g')
    .attr('class', 'link-item');

  const linkLines = links.append('line')
    .attr('stroke', (d: any) => {
      if (d.type === 'implicit') return '#06b6d4'; // Örtük ilişkiler için Turkuaz
      if (d.type === 'custom') return '#f59e0b'; // Manuel özel ilişkiler için Turuncu/Amber
      return '#4f46e5'; // Sistem ilişkileri için Indigo
    })
    .attr('stroke-width', (d: any) => {
      if (d.type === 'implicit') return 1.5;
      return 2;
    })
    .attr('stroke-dasharray', (d: any) => {
      if (d.type === 'implicit') return '5 4'; // Kesikli çizgi
      if (d.type === 'custom') return '2 3'; // Noktalı çizgi
      return 'none'; // Düz çizgi
    })
    .attr('marker-end', 'url(#arrow)')
    .style('opacity', 0.5)
    .style('pointer-events', 'none')
    .style('transition', 'opacity 0.2s, stroke 0.2s, stroke-width 0.2s');

  // Hover durumunda kolon eşleştirmesini gösterecek metin etiketi
  const linkLabels = links.append('text')
    .attr('font-size', '8px')
    .attr('font-family', 'monospace')
    .attr('fill', '#a1a1aa') // Zinc 400
    .attr('text-anchor', 'middle')
    .attr('dy', -4)
    .style('opacity', 0)
    .style('pointer-events', 'none')
    .style('transition', 'opacity 0.2s')
    .text((d: any) => `${d.source_col} ➔ ${d.target_col}`);

  // Düğümleri (Nodes) Çiz
  const nodes = nodeGroup.selectAll('g.node-item')
    .data(nodesData)
    .enter()
    .append('g')
    .attr('class', 'node-item')
    .call(d3.drag<any, NodeItem>()
      .on('start', dragstarted)
      .on('drag', dragged)
      .on('end', dragended)
    );

  // Tablo Daireleri (Obsidian Glass)
  const nodeCircles = nodes.append('circle')
    .attr('r', 18)
    .attr('fill', '#09090b') // Zinc 950
    .attr('stroke', '#3f3f46') // Zinc 700
    .attr('stroke-width', 2)
    .style('filter', 'drop-shadow(0 4px 6px rgba(0, 0, 0, 0.45))')
    .style('cursor', 'pointer')
    .style('transition', 'r 0.2s, stroke 0.2s, fill 0.2s');

  // Tablo İsim Etiketleri
  const nodeTexts = nodes.append('text')
    .attr('text-anchor', 'middle')
    .attr('dy', 30)
    .attr('fill', '#d4d4d8') // Zinc 300
    .attr('font-size', '9.5px')
    .attr('font-weight', 'bold')
    .attr('font-family', 'monospace')
    .style('pointer-events', 'none')
    .style('transition', 'fill 0.2s, font-size 0.2s')
    .text((d: any) => d.id);

  // Düğüm İçi Veritabanı Tablo Simgesi
  nodes.append('rect')
    .attr('x', -6)
    .attr('y', -6)
    .attr('width', 12)
    .attr('height', 12)
    .attr('rx', 1.5)
    .attr('fill', 'none')
    .attr('stroke', '#818cf8') // Indigo 400
    .attr('stroke-width', 1.2)
    .style('pointer-events', 'none');

  nodes.append('line')
    .attr('x1', -3)
    .attr('y1', -2)
    .attr('x2', 3)
    .attr('y2', -2)
    .attr('stroke', '#818cf8')
    .attr('stroke-width', 0.8)
    .style('pointer-events', 'none');

  nodes.append('line')
    .attr('x1', -3)
    .attr('y1', 2)
    .attr('x2', 3)
    .attr('y2', 2)
    .attr('stroke', '#818cf8')
    .attr('stroke-width', 0.8)
    .style('pointer-events', 'none');

  // Fizik Güncelleme Adımları (Tick Listener)
  simulation.on('tick', () => {
    // Dynamic Black Hole Keplerian & Accretion Vortex Physics
    if (isPhysicsActive.value) {
      nodesData.forEach((d: any) => {
        if (d.fx !== undefined && d.fx !== null) return;

        const dx = d.x - centerX;
        const dy = d.y - centerY;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;

        // 1. Keplerian Swirling Force (tangential clockwise spin, faster near center)
        const orbitSpeed = Math.min(0.25, 2.5 / Math.sqrt(dist));
        const ndx = -dy / dist;
        const ndy = dx / dist;

        d.vx += ndx * orbitSpeed * 0.6;
        d.vy += ndy * orbitSpeed * 0.6;

        // 2. Gravitational Suction (draw inwards continuously, balanced by radial forces)
        const suctionStrength = 0.018;
        d.vx -= (dx / dist) * suctionStrength;
        d.vy -= (dy / dist) * suctionStrength;
      });
    }

    linkLines
      .attr('x1', (d: any) => d.source.x)
      .attr('y1', (d: any) => d.source.y)
      .attr('x2', (d: any) => d.target.x)
      .attr('y2', (d: any) => d.target.y);

    linkLabels
      .attr('x', (d: any) => ((d.source.x + d.target.x) / 2))
      .attr('y', (d: any) => ((d.source.y + d.target.y) / 2));

    nodes.attr('transform', (d: any) => `translate(${d.x},${d.y})`);
  });

  // Etkileşimler: 1-Hop Komşuluk Aydınlatması (Hover Highlight)
  nodes.on('mouseover', function(_event, d: NodeItem) {
    // Üzerine gelinen düğümü büyüt ve parlat
    d3.select(this).select('circle')
      .attr('r', 21)
      .attr('stroke', '#818cf8')
      .attr('fill', '#1e1b4b') // Indigo 950
      .style('filter', 'url(#glow)');

    d3.select(this).select('text')
      .attr('fill', '#ffffff')
      .attr('font-size', '10.5px');

    // Komşu olan tüm tablo düğümlerini bul
    const neighborIds = new Set<string>();
    neighborIds.add(d.id);

    linkLines.each(function(l: any) {
      if (l.source.id === d.id) {
        neighborIds.add(l.target.id);
      } else if (l.target.id === d.id) {
        neighborIds.add(l.source.id);
      }
    });

    // İlişkisiz elemanları matlaştır, ilişkilileri vurgula
    nodeCircles.style('opacity', (n: any) => neighborIds.has(n.id) ? 1 : 0.2);
    nodeTexts.style('opacity', (n: any) => neighborIds.has(n.id) ? 1 : 0.2);
    
    linkLines.style('opacity', (l: any) => {
      const connected = l.source.id === d.id || l.target.id === d.id;
      return connected ? 0.95 : 0.05;
    })
    .attr('stroke', (l: any) => {
      const connected = l.source.id === d.id || l.target.id === d.id;
      if (connected) {
        if (l.type === 'implicit') return '#22d3ee'; // Bright Cyan
        if (l.type === 'custom') return '#fbbf24'; // Bright Amber
        return '#818cf8'; // Bright Indigo
      }
      if (l.type === 'implicit') return '#06b6d4';
      if (l.type === 'custom') return '#f59e0b';
      return '#4f46e5';
    })
    .attr('stroke-width', (l: any) => {
      const connected = l.source.id === d.id || l.target.id === d.id;
      return connected ? 3 : (l.type === 'implicit' ? 1.5 : 2);
    });

    linkLabels.style('opacity', (l: any) => {
      return (l.source.id === d.id || l.target.id === d.id) ? 1 : 0;
    });
  });

  nodes.on('mouseout', function() {
    // Düğümü eski boyutuna/rengine döndür
    d3.select(this).select('circle')
      .attr('r', 18)
      .attr('stroke', '#3f3f46')
      .attr('fill', '#09090b')
      .style('filter', 'drop-shadow(0 4px 6px rgba(0, 0, 0, 0.45))');

    d3.select(this).select('text')
      .attr('fill', '#d4d4d8')
      .attr('font-size', '9.5px');

    // Her şeyi eski şeffaflık seviyesine çek
    nodeCircles.style('opacity', 1);
    nodeTexts.style('opacity', 1);
    
    linkLines
      .style('opacity', 0.5)
      .attr('stroke', (l: any) => {
        if (l.type === 'implicit') return '#06b6d4';
        if (l.type === 'custom') return '#f59e0b';
        return '#4f46e5';
      })
      .attr('stroke-width', (l: any) => l.type === 'implicit' ? 1.5 : 2);

    linkLabels.style('opacity', 0);
  });

  // Tıklanınca Odaklan ve Sol Listeden Seç
  nodes.on('click', (event, d: NodeItem) => {
    event.stopPropagation();
    focusNode(d);
  });
};

// Sürükle Bırak İşlevleri
function dragstarted(event: any, d: NodeItem) {
  if (!event.active && simulation) simulation.alphaTarget(0.3).restart();
  d.fx = d.x;
  d.fy = d.y;
}

function dragged(event: any, d: NodeItem) {
  d.fx = event.x;
  d.fy = event.y;
}

function dragended(event: any, d: NodeItem) {
  if (!event.active && simulation) simulation.alphaTarget(0);
  if (isPhysicsActive.value) {
    d.fx = null;
    d.fy = null;
  }
}

// Bir Düğüme ve Sol Listeye Odaklanma
const focusNode = (node: NodeItem) => {
  if (!svgRef.value || !zoomBehavior || !node) return;

  expandedTable.value = node.id;
  
  nextTick(() => {
    const el = document.getElementById(`table-card-${node.id}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  });

  const width = svgRef.value.clientWidth || 500;
  const height = svgRef.value.clientHeight || 400;

  // Kamera açısını yumuşak bir transition ile düğüme ortala
  const transform = d3.zoomIdentity
    .translate(width / 2 - (node.x || 0) * 1.2, height / 2 - (node.y || 0) * 1.2)
    .scale(1.2);

  d3.select(svgRef.value)
    .transition()
    .duration(750)
    .call(zoomBehavior.transform, transform);
};

// Kamera Görünümünü Sıfırlama
const resetZoom = () => {
  if (!svgRef.value || !zoomBehavior) return;
  
  d3.select(svgRef.value)
    .transition()
    .duration(750)
    .call(zoomBehavior.transform, d3.zoomIdentity);
};

// Fizik Simülasyonunu Aç/Kapat
const togglePhysics = () => {
  isPhysicsActive.value = !isPhysicsActive.value;
  if (!simulation) return;
  
  if (isPhysicsActive.value) {
    simulation.nodes().forEach((n: NodeItem) => {
      n.fx = null;
      n.fy = null;
    });
    simulation.alpha(0.3).restart();
  } else {
    simulation.stop();
    simulation.nodes().forEach((n: NodeItem) => {
      n.fx = n.x;
      n.fy = n.y;
    });
  }
};

// Şema Değişimini Dinle ve Grafiği Çiz
watch(schema, () => {
  nextTick(() => {
    initGraph();
  });
});

// Window resize olduğunda grafiği yeniden yapılandır
const handleResize = () => {
  if (svgRef.value && schema.value) {
    initGraph();
  }
};

onMounted(() => {
  loadSchema();
  loadRelations();
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  if (simulation) simulation.stop();
});
</script>

<template>
  <div class="relative">
    <!-- Header and DB Card Wrapper -->
    <div :class="[
      isTransitioning ? 'transition-[max-height,transform,opacity] duration-700 ease-in-out' : '',
      'flex flex-col relative z-30',
      isHidingElements ? 'transform translate-x-[120%] opacity-0' : 'transform translate-x-0 opacity-100',
      isGraphExpanded ? 'max-h-0 gap-0 overflow-hidden' : 'max-h-[400px] gap-6'
    ]">
      <!-- Header -->
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-2xl font-bold text-white tracking-tight">Veritabanı Şema Yöneticisi</h2>
          <p class="text-zinc-400 text-sm">Aktif hedef veritabanı şemasını, tabloları ve yabancı anahtar ilişkilerini denetleyin.</p>
        </div>

        <div class="flex items-center gap-4">
          <!-- Limit Kontrolü -->
          <div class="flex items-center gap-2 bg-black/30 px-3 py-1.5 rounded-lg border border-zinc-800">
            <label class="text-[10px] text-zinc-400 font-bold uppercase tracking-wider">Node Limiti (0=Sınırsız):</label>
            <input 
              v-model.number="maxNodesLimit" 
              @change="initGraph"
              type="number" 
              min="0"
              class="w-16 h-6 bg-zinc-900 border border-zinc-700 rounded text-xs text-center text-white focus:outline-none focus:border-indigo-500" 
            />
          </div>

          <button 
            @click="loadSchema(true)" 
            :disabled="loading"
            :class="[
              'h-9 px-4 bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 hover:border-zinc-700 text-zinc-300 hover:text-white font-semibold text-xs rounded-xl flex items-center gap-2 transition-all btn-laser',
          loading ? 'is-loading opacity-80 cursor-not-allowed' : ''
        ]"
      >
        <svg 
          xmlns="http://www.w3.org/2000/svg" 
          :class="['h-3.5 w-3.5', loading ? 'animate-spin' : '']" 
          viewBox="0 0 24 24" 
          fill="none" 
          stroke="currentColor" 
          stroke-width="2"
        >
          <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3 3m0 0l3-3m-3 3V8" />
        </svg>
        Önbelleği Yenile
      </button>
    </div>
  </div>

  <!-- Active DB Connection Info Card -->
    <div class="relative z-20 bg-zinc-950/70 rounded-2xl border border-white/10 shadow-lg shadow-black/30 p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
      <div class="flex items-center gap-4">
        <div class="w-12 h-12 rounded-xl bg-zinc-950 border border-zinc-850 flex items-center justify-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-indigo-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
          </svg>
        </div>
        <div class="text-left space-y-2">
          <h3 class="text-sm font-semibold text-white">Bağlantı Durumu: Aktif</h3>
          <div class="flex items-center gap-3">
            <PlanetDbSelector v-model="targetDbType" @change="onDialectChange" />
            <span class="text-xs text-zinc-500">
              Veritabanı: <code class="bg-zinc-950 text-indigo-400 px-1.5 py-0.5 rounded text-[10px]">{{ targetDbName }}</code>
            </span>
          </div>
        </div>
      </div>

      <div class="flex items-center gap-4 text-xs">
        <div class="bg-zinc-950/80 border border-zinc-850 px-3.5 py-2 rounded-xl text-left">
          <span class="text-zinc-500 block text-[9px] uppercase tracking-wider font-bold">Toplam Tablo</span>
          <span class="text-white font-mono font-bold text-sm">{{ schema ? Object.keys(schema.tables || {}).length : 0 }}</span>
        </div>
        <div class="bg-zinc-950/80 border border-zinc-850 px-3.5 py-2 rounded-xl text-left">
          <span class="text-zinc-500 block text-[9px] uppercase tracking-wider font-bold">Toplam İlişki</span>
          <span class="text-white font-mono font-bold text-sm">{{ schema ? (schema.graph?.edges || []).length : 0 }}</span>
        </div>
      </div>
    </div>
    </div>

    <!-- Tables & Graph Split Flex Layout -->
    <div :class="[
      isTransitioning ? 'transition-[margin,gap] duration-700 ease-in-out' : '',
      'flex flex-col lg:flex-row',
      isGraphExpanded ? 'gap-0 mt-0' : 'gap-6 mt-6'
    ]">
      
      <!-- Tables List (Left) -->
      <div :class="[
        isTransitioning ? 'transition-[width,height,transform,opacity] duration-700 ease-in-out' : '',
        'shrink-0',
        isHidingElements ? 'transform translate-x-[120%] opacity-0' : 'transform translate-x-0 opacity-100',
        isGraphExpanded ? 'w-0 h-0 overflow-hidden opacity-0 m-0' : 'w-full lg:w-[41.666667%] space-y-4'
      ]">
        <div class="bg-zinc-950/70 rounded-2xl border border-white/10 shadow-lg shadow-black/30 p-5 min-h-[400px] flex flex-col justify-start">
          <h3 class="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-4 text-left">Şema Tabloları</h3>

          <div v-if="loading && !schema" class="flex-1 flex flex-col items-center justify-center space-y-2">
            <svg class="animate-spin h-5 w-5 text-indigo-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <p class="text-[10px] text-zinc-500">{{ targetDbType === 'postgres' ? 'PostgreSQL' : targetDbType === 'oracle' ? 'Oracle' : 'SQLite' }} Tabloları Listeleniyor...</p>
          </div>

          <div v-else-if="!schema || Object.keys(schema.tables || {}).length === 0" class="flex-1 flex flex-col items-center justify-center text-center p-6 space-y-3">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-zinc-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <p class="text-xs text-zinc-500 font-medium">Veritabanından şema bilgisi çekilemedi. Bağlantı ayarlarınızı doğrulayın.</p>
          </div>

          <!-- Table Tree list -->
          <div v-else class="space-y-2 flex-1 overflow-y-auto max-h-[500px] pr-1.5 text-left pb-4">
            <div 
              v-for="(meta, name) in visibleTables" 
              :key="name"
              :id="'table-card-' + name"
              class="border border-zinc-800 rounded-xl overflow-hidden bg-zinc-950/20 shrink-0"
              :class="expandedTable === name ? 'border-indigo-500/80 ring-1 ring-indigo-500/20' : ''"
            >
              <!-- Table Title bar -->
              <button 
                @click="toggleTable(String(name))"
                class="w-full px-4 py-3 bg-zinc-900/30 hover:bg-zinc-900/60 flex items-center justify-between transition-colors"
              >
                <div class="flex items-center gap-2.5">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                  <span class="text-xs font-bold text-zinc-200 font-mono">{{ name }}</span>
                  <span class="text-[9px] font-semibold text-zinc-500 bg-zinc-900 border border-zinc-800 px-1.5 py-0.2 rounded-md">{{ meta.columns.length }} Kolon</span>
                </div>
                
                <svg 
                  xmlns="http://www.w3.org/2000/svg" 
                  :class="['h-4 w-4 text-zinc-500 transition-transform duration-200', expandedTable === name ? 'rotate-180' : '']" 
                  fill="none" 
                  viewBox="0 0 24 24" 
                  stroke="currentColor" 
                  stroke-width="2"
                >
                  <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              <!-- Columns & FKs Details -->
              <div 
                v-if="expandedTable === name" 
                class="border-t border-zinc-900 p-3 bg-zinc-950/50 space-y-3.5"
              >
                <!-- Columns list -->
                <div class="space-y-1.5">
                  <span class="text-[9px] font-bold text-zinc-500 uppercase tracking-wider block">Kolonlar:</span>
                  <div class="space-y-1">
                    <div 
                      v-for="col in meta.columns" 
                      :key="col.name"
                      class="flex items-center justify-between text-[11px] p-1.5 rounded bg-zinc-950/80 border border-zinc-900"
                    >
                      <span class="font-mono text-zinc-300 flex items-center gap-1.5">
                        <span 
                          v-if="col.primary_key" 
                          class="w-1.5 h-1.5 rounded-full bg-amber-400"
                          title="Primary Key"
                        ></span>
                        <span 
                          v-else 
                          class="w-1.5 h-1.5 rounded-full bg-zinc-700"
                        ></span>
                        {{ col.name }}
                      </span>
                      <span class="text-[10px] font-semibold text-indigo-400/90 font-mono">{{ col.type }}</span>
                    </div>
                  </div>
                </div>

                <!-- FKs list -->
                <div v-if="meta.foreign_keys && meta.foreign_keys.length > 0" class="space-y-1.5">
                  <span class="text-[9px] font-bold text-zinc-500 uppercase tracking-wider block">Foreign Keys:</span>
                  <div class="space-y-1 text-[10px] font-mono text-zinc-400">
                    <div 
                      v-for="fk in meta.foreign_keys" 
                      :key="fk.column"
                      class="bg-indigo-500/5 border border-indigo-500/10 p-2 rounded-lg flex items-center gap-1"
                    >
                      <span class="text-indigo-300 font-semibold">{{ fk.column }}</span>
                      <span class="text-zinc-600">&rarr;</span>
                      <span class="text-zinc-300">{{ fk.referenced_table }}({{ fk.referenced_column }})</span>
                    </div>
                  </div>
                </div>

                <!-- Incoming Relations (Referans Verenler) Accordion -->
                <div v-if="getIncomingRelations(String(name)).length > 0" class="space-y-1.5 mt-3">
                  <button 
                    @click="showIncoming = !showIncoming"
                    class="w-full flex items-center justify-between text-[9px] font-bold text-zinc-400 uppercase tracking-wider bg-zinc-900/30 hover:bg-zinc-800/40 p-1.5 rounded transition-colors"
                  >
                    <span class="flex items-center gap-1.5">
                      <span class="text-indigo-400">{{ showIncoming ? '[-]' : '[+]' }}</span>
                      Bu Tabloya Referans Verenler ({{ getIncomingRelations(String(name)).length }})
                    </span>
                    <svg 
                      xmlns="http://www.w3.org/2000/svg" 
                      :class="['h-3 w-3 transition-transform', showIncoming ? 'rotate-180' : '']" 
                      fill="none" viewBox="0 0 24 24" stroke="currentColor"
                    >
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                  
                  <div v-if="showIncoming" class="space-y-1 text-[10px] font-mono text-zinc-400 pl-2 border-l-2 border-indigo-500/20 mt-1.5">
                    <div 
                      v-for="inc in getIncomingRelations(String(name))" 
                      :key="inc.source_table + inc.source_column"
                      class="bg-zinc-950/40 border border-zinc-800/60 p-2 rounded-lg flex items-center gap-1"
                    >
                      <span class="text-zinc-300">{{ inc.source_table }}({{ inc.source_column }})</span>
                      <span class="text-zinc-600">&rarr;</span>
                      <span class="text-indigo-300 font-semibold">{{ inc.target_column }}</span>
                    </div>
                  </div>
                </div>

                <!-- Virtual / Implicit Relations list -->
                <div v-if="allRelations.filter(r => (r.source === name || r.target === name) && r.type !== 'explicit').length > 0" class="space-y-1.5 mt-3">
                  <span class="text-[9px] font-bold text-zinc-500 uppercase tracking-wider block">Sanal / Örtük Bağlantılar:</span>
                  <div class="space-y-1 text-[10px] font-mono text-zinc-400">
                    <div 
                      v-for="rel in allRelations.filter(r => (r.source === name || r.target === name) && r.type !== 'explicit')" 
                      :key="rel.source + '_' + rel.target + '_' + rel.source_col + '_' + rel.target_col"
                      class="bg-zinc-900/40 border p-2 rounded-lg flex items-center gap-1"
                      :class="[
                        rel.type === 'custom' ? 'border-amber-500/20' : 'border-cyan-500/20',
                        rel.disabled ? 'opacity-50' : ''
                      ]"
                    >
                      <span :class="rel.type === 'custom' ? 'text-amber-300' : 'text-cyan-300'" class="font-semibold">
                        {{ rel.source === name ? rel.source_col : rel.target_col }}
                      </span>
                      <span class="text-zinc-600">&harr;</span>
                      <span class="text-zinc-300">
                        {{ rel.source === name ? rel.target : rel.source }}<span class="text-zinc-500">.{{ rel.source === name ? rel.target_col : rel.source_col }}</span>
                      </span>
                      
                      <span v-if="rel.disabled" class="ml-auto text-[8px] px-1 bg-zinc-800 text-zinc-500 rounded">Pasif</span>
                      <span v-else class="ml-auto text-[8px] px-1.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded">Aktif</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Daha Fazla Yükle Butonu -->
            <button 
              v-if="totalTablesCount > visibleTablesLimit"
              @click="loadMoreTables"
              class="w-full mt-4 py-2.5 px-4 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 hover:border-zinc-700 text-zinc-400 hover:text-white font-bold text-xs rounded-xl flex items-center justify-center gap-2 transition-[background-color,border-color,color] duration-200 active:scale-[0.98]"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
              Daha Fazla Yükle ({{ totalTablesCount - visibleTablesLimit }} tablo kaldı)
            </button>
          </div>
        </div>
      </div>

      <!-- Graph Visualization Container (Right) -->
      <div :class="[
        isTransitioning ? 'transition-[width,flex] duration-700 ease-in-out' : '',
        'flex-1 flex flex-col min-w-0',
        isGraphExpanded ? 'w-full' : ''
      ]">
        <div :class="[
          'bg-zinc-950/70 rounded-2xl border border-white/10 shadow-lg shadow-black/30 p-5 flex flex-col justify-between relative overflow-hidden w-full',
          isTransitioning ? 'transition-[height,opacity] duration-700 ease-in-out' : '',
          isGraphExpanded ? 'h-[calc(100vh-4rem)]' : 'min-h-[460px] h-[600px]'
        ]">
          <div class="flex items-center justify-between mb-4 z-10">
            <h3 class="text-xs font-bold text-zinc-400 uppercase tracking-wider text-left">Topolojik Şema İlişkileri (D3.js)</h3>
            <div class="flex items-center gap-3">
              <div class="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-[10px] font-bold animate-pulse">
                <span class="w-1.5 h-1.5 rounded-full bg-indigo-400"></span>
                Görsel Grafik Hazır
              </div>
              <button 
                @click="toggleGraphExpand"
                class="p-1.5 hover:bg-zinc-800 rounded-lg transition-colors text-zinc-400 hover:text-white"
                :title="isGraphExpanded ? 'Küçült' : 'Tam Ekran Büyüt'"
              >
                <svg v-if="!isGraphExpanded" xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                </svg>
                <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 14h6m0 0v6m0-6l-7 7m17-11h-6m0 0V4m0 6l7-7M4 10h6m0 0V4m0 6l-7-7m17 11h-6m0 0v6m0-6l7 7" />
                </svg>
              </button>
            </div>
          </div>

          <!-- D3.js Live Graph View -->
          <div class="flex-1 bg-zinc-950/80 border border-zinc-850 rounded-xl relative overflow-hidden min-h-[360px] shadow-inner flex items-center justify-center live-graph-container">
            <div class="absolute inset-0 bg-radial-gradient pointer-events-none"></div>
            
            <svg 
              ref="svgRef" 
              data-lenis-prevent
              class="relative w-full h-full select-none cursor-grab active:cursor-grabbing z-10"
              style="min-height: 360px;"
            ></svg>

            <!-- Loading overlay when schema is fetched -->
            <div v-if="loading && !schema" class="absolute inset-0 bg-zinc-950/80 backdrop-blur-sm flex flex-col items-center justify-center space-y-3 z-20">
              <div class="w-8 h-8 rounded-full border-2 border-indigo-500/30 border-t-indigo-500 animate-spin"></div>
              <p class="text-xs text-zinc-400">{{ targetDbType === 'postgres' ? 'PostgreSQL' : targetDbType === 'oracle' ? 'Oracle' : 'SQLite' }} Şeması Görselleştiriliyor...</p>
            </div>

            <!-- Empty State -->
            <div v-else-if="!schema || !schema.graph || schema.graph.nodes.length === 0" class="absolute inset-0 flex flex-col items-center justify-center space-y-3 z-20 pointer-events-none">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-zinc-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
                <path stroke-linecap="round" stroke-linejoin="round" d="M11 3.055A9.003 9.003 0 1020.945 13H11V3.055z" />
              </svg>
              <p class="text-xs text-zinc-500 font-medium">Görselleştirilecek tablo ilişkisi bulunamadı.</p>
            </div>

            <!-- Controls overlay -->
            <div v-if="schema && schema.graph && schema.graph.nodes.length > 0" class="absolute bottom-4 right-4 flex items-center gap-2 z-10">
              <button 
                @click="resetZoom"
                class="h-8 w-8 bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 hover:border-zinc-750 text-zinc-400 hover:text-white rounded-lg flex items-center justify-center transition-colors shadow-lg active:scale-95"
                title="Kamerayı Sıfırla"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4.5 w-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3 3m0 0l3-3m-3 3V8" />
                </svg>
              </button>
              <button 
                @click="togglePhysics"
                class="h-8 px-2.5 bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 hover:border-zinc-750 text-zinc-400 hover:text-white rounded-lg flex items-center gap-1.5 transition-colors shadow-lg text-[10px] font-bold active:scale-95"
                :title="isPhysicsActive ? 'Fizik simülasyonunu durdur' : 'Fizik simülasyonunu aktifleştir'"
              >
                <span class="w-1.5 h-1.5 rounded-full transition-colors" :class="isPhysicsActive ? 'bg-emerald-400 shadow-md shadow-emerald-400/50' : 'bg-zinc-500'"></span>
                {{ isPhysicsActive ? 'Fizik Aktif' : 'Fizik Durgun' }}
              </button>
            </div>
          </div>
          
          <div class="text-[10px] text-zinc-500 mt-4 text-left">
            Grafikteki tabloları sürükleyebilir, fare tekerleğiyle yakınlaşabilir ve tablolara tıklayarak kolon detaylarını sol sütundan görüntüleyebilirsiniz.
          </div>
        </div>
      </div>
    </div>
    <!-- Sanal İlişki ve Bağlantı Editörü (Virtual Relationship Manager) -->
    <div :class="[
      'bg-zinc-950/70 border border-white/10 shadow-black/30 text-left overflow-hidden',
      isTransitioning ? 'transition-[max-height,transform,opacity,padding,margin] duration-700 ease-in-out' : '',
      isHidingElements ? 'transform translate-x-[120%] opacity-0' : 'transform translate-x-0 opacity-100',
      isGraphExpanded ? 'max-h-0 p-0 border-0 mt-0 shadow-none space-y-0' : 'max-h-[1500px] p-6 border shadow-lg mt-6 space-y-6'
    ]">
      <div>
        <h3 class="text-lg font-bold text-white tracking-tight flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
          </svg>
          Sanal İlişki ve Bağlantı Editörü
        </h3>
        <p class="text-zinc-400 text-xs mt-1">
          Veritabanı düzeyinde yabancı anahtar (FK) kısıtı olmayan tablolar arasında sanal veya otomatik örtük ilişkiler kurun, etkinleştirin veya devre dışı bırakın.
        </p>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <!-- Sol Kolon: Sanal Bağlantı Ekleme Formu -->
        <div class="lg:col-span-4 flex flex-col">
          <div class="bg-zinc-950/60 border border-zinc-850 p-4 rounded-xl space-y-4 flex flex-col justify-start h-[520px] min-h-0 overflow-y-auto">
            <h4 class="text-xs font-bold text-zinc-300 uppercase tracking-wider">Yeni Sanal İlişki Ekle</h4>
            
            <div class="space-y-3">
              <!-- Kaynak Tablo -->
              <div class="space-y-1">
                <div class="flex items-center justify-between">
                  <label class="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block">Kaynak Tablo</label>
                  <input 
                    v-model="sourceTableSearch"
                    type="text"
                    placeholder="Tablo ara..."
                    class="w-24 h-4 bg-zinc-950/80 border border-zinc-850 rounded text-[9px] px-1.5 text-zinc-300 focus:outline-none focus:border-indigo-500 font-mono"
                  />
                </div>
                <select 
                  v-model="newSourceTable"
                  class="w-full h-9 px-3 bg-zinc-900 border border-zinc-800 focus:border-indigo-500/80 focus:ring-1 focus:ring-indigo-500/20 text-zinc-200 text-xs rounded-lg outline-none font-mono transition-colors"
                >
                  <option value="" disabled selected>Tablo Seçin</option>
                  <option 
                    v-for="name in searchFilteredSourceTables" 
                    :key="'src_tbl_' + name" 
                    :value="name"
                  >
                    {{ name }}
                  </option>
                </select>
              </div>

              <!-- Kaynak Kolon -->
              <div class="space-y-1">
                <label class="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block">Kaynak Kolon</label>
                <select 
                  v-model="newSourceColumn"
                  :disabled="!newSourceTable"
                  class="w-full h-9 px-3 bg-zinc-900 border border-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed focus:border-indigo-500/80 focus:ring-1 focus:ring-indigo-500/20 text-zinc-200 text-xs rounded-lg outline-none font-mono transition-colors"
                >
                  <option value="" disabled selected>Kolon Seçin</option>
                  <option 
                    v-for="col in sourceColumns" 
                    :key="'src_col_' + col.name" 
                    :value="col.name"
                  >
                    {{ col.name }} ({{ col.type }})
                  </option>
                </select>
              </div>

              <!-- Yön Göstergesi (Premium Micro-animation) -->
              <div class="flex justify-center py-1">
                <div class="w-8 h-8 rounded-full bg-zinc-900/60 border border-zinc-800/80 flex items-center justify-center text-zinc-500 shadow-inner">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M19 13l-7 7-7-7m14-6l-7 7-7-7" />
                  </svg>
                </div>
              </div>

              <!-- Hedef Tablo -->
              <div class="space-y-1">
                <div class="flex items-center justify-between">
                  <label class="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block">Hedef Tablo</label>
                  <input 
                    v-model="targetTableSearch"
                    type="text"
                    placeholder="Tablo ara..."
                    class="w-24 h-4 bg-zinc-950/80 border border-zinc-850 rounded text-[9px] px-1.5 text-zinc-300 focus:outline-none focus:border-indigo-500 font-mono"
                  />
                </div>
                <select 
                  v-model="newTargetTable"
                  class="w-full h-9 px-3 bg-zinc-900 border border-zinc-800 focus:border-indigo-500/80 focus:ring-1 focus:ring-indigo-500/20 text-zinc-200 text-xs rounded-lg outline-none font-mono transition-colors"
                >
                  <option value="" disabled selected>Tablo Seçin</option>
                  <option 
                    v-for="name in searchFilteredTargetTables" 
                    :key="'tgt_tbl_' + name" 
                    :value="name"
                  >
                    {{ name }}
                  </option>
                </select>
              </div>

              <!-- Hedef Kolon -->
              <div class="space-y-1">
                <label class="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block">Hedef Kolon</label>
                <select 
                  v-model="newTargetColumn"
                  :disabled="!newTargetTable"
                  class="w-full h-9 px-3 bg-zinc-900 border border-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed focus:border-indigo-500/80 focus:ring-1 focus:ring-indigo-500/20 text-zinc-200 text-xs rounded-lg outline-none font-mono transition-colors"
                >
                  <option value="" disabled selected>Kolon Seçin</option>
                  <option 
                    v-for="col in targetColumns" 
                    :key="'tgt_col_' + col.name" 
                    :value="col.name"
                  >
                    {{ col.name }} ({{ col.type }})
                  </option>
                </select>
              </div>
            </div>

            <!-- Kaydet Butonu -->
            <button 
              @click="addCustomRelation"
              :disabled="!newSourceTable || !newSourceColumn || !newTargetTable || !newTargetColumn"
              class="w-full h-9 px-4 bg-amber-600 hover:bg-amber-500 disabled:bg-zinc-800/80 disabled:text-zinc-600 disabled:opacity-50 text-white font-semibold text-xs rounded-xl flex items-center justify-center gap-2 transition-all shadow-md shadow-amber-600/10 hover:shadow-amber-600/20"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clip-rule="evenodd" />
              </svg>
              Sanal İlişkiyi Kaydet
            </button>
          </div>
        </div>

        <!-- Sağ Kolon: Mevcut Tüm İlişkilerin Yönetim Listesi -->
        <div class="lg:col-span-8 flex flex-col">
          <div class="bg-zinc-950/60 border border-zinc-850 p-4 rounded-xl flex flex-col justify-start h-[520px] min-h-0">
            <h4 class="text-xs font-bold text-zinc-300 uppercase tracking-wider mb-4 shrink-0">Aktif ve Pasif Tüm İlişkiler</h4>
            
            <div v-if="allRelations.length === 0" class="flex-1 flex flex-col items-center justify-center text-center p-6 space-y-2">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-7 w-7 text-zinc-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M18.364 5.636l-3.536 3.536m0 5.656l3.536 3.536M9.172 9.172L5.636 5.636m3.536 9.192l-3.536 3.536M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-5 0a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
              <p class="text-xs text-zinc-500">Herhangi bir tablo ilişkisi tespit edilemedi veya eklenmedi.</p>
            </div>

            <div v-else class="flex flex-col flex-1 min-h-0 overflow-hidden">
              <div class="overflow-y-auto pr-1 space-y-2.5 pb-4 flex-1">
                <div 
                  v-for="rel in visibleRelations" 
                  :key="rel.source + '_' + rel.source_col + '_' + rel.target + '_' + rel.target_col"
                  class="flex flex-col sm:flex-row items-start sm:items-center justify-between p-3 rounded-xl border bg-zinc-900/10 hover:bg-zinc-900/40 transition-colors shrink-0"
                :class="[
                  rel.disabled ? 'border-zinc-900/60 opacity-60' : 'border-zinc-800',
                  rel.type === 'custom' ? 'hover:border-amber-500/30' : '',
                  rel.type === 'implicit' ? 'hover:border-cyan-500/30' : '',
                  rel.type === 'explicit' ? 'hover:border-indigo-500/30' : ''
                ]"
              >
                <!-- Sol Taraf: İlişki Bilgileri -->
                <div class="flex flex-col sm:flex-row sm:items-center gap-2.5">
                  <!-- Tür Rozeti -->
                  <div class="flex items-center">
                    <span 
                      v-if="rel.type === 'explicit'" 
                      class="px-2 py-0.5 rounded-full bg-indigo-500/10 border border-indigo-500/30 text-indigo-400 text-[9px] font-bold tracking-wider"
                    >
                      SİSTEM
                    </span>
                    <span 
                      v-else-if="rel.type === 'implicit'" 
                      class="px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 text-[9px] font-bold tracking-wider"
                    >
                      ÖRTÜK
                    </span>
                    <span 
                      v-else-if="rel.type === 'custom'" 
                      class="px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400 text-[9px] font-bold tracking-wider"
                    >
                      SANAL
                    </span>
                  </div>

                  <!-- Kolon Eşleşmesi -->
                  <div class="flex items-center gap-1.5 font-mono text-[11px]">
                    <span class="text-zinc-200 font-bold text-left">{{ rel.source }}</span>
                    <span class="text-zinc-500 text-[10px]">.{{ rel.source_col }}</span>
                    
                    <span class="text-zinc-500 px-1 font-semibold text-[10px]">&rarr;</span>
                    
                    <span class="text-zinc-200 font-bold text-left">{{ rel.target }}</span>
                    <span class="text-zinc-500 text-[10px]">.{{ rel.target_col }}</span>
                  </div>
                </div>

                <!-- Sağ Taraf: Toggles & Silme Butonları -->
                <div class="flex items-center gap-4 mt-2.5 sm:mt-0 w-full sm:w-auto justify-end">
                  <!-- Aktif/Pasif Toggle Switch -->
                  <div class="flex items-center gap-2">
                    <span class="text-[10px] font-bold" :class="rel.disabled ? 'text-zinc-550' : 'text-emerald-400'">
                      {{ rel.disabled ? 'Pasif' : 'Aktif' }}
                    </span>
                    
                    <button 
                      @click="toggleRelationStatus(rel)"
                      class="w-8 h-4 rounded-full p-0.5 transition-colors relative flex items-center"
                      :class="rel.disabled ? 'bg-zinc-800' : 'bg-emerald-600/30 border border-emerald-500/40'"
                    >
                      <span 
                        class="w-3 h-3 rounded-full transition-transform transform"
                        :class="[
                          rel.disabled ? 'translate-x-0 bg-zinc-500' : 'translate-x-4 bg-emerald-400 shadow-md shadow-emerald-400/50'
                        ]"
                      ></span>
                    </button>
                  </div>

                  <!-- Özel Bağlantı İçin Silme (Çöp Kutusu) -->
                  <button 
                    v-if="rel.type === 'custom'"
                    @click="deleteCustomRelation(rel)"
                    class="p-1.5 rounded-lg border border-zinc-850 hover:border-rose-500/30 hover:bg-rose-500/10 text-zinc-500 hover:text-rose-400 transition-all active:scale-95"
                    title="Bağlantıyı Sil"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                      <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
                    </svg>
                  </button>
                </div>
              </div>

              <!-- Daha Fazla Yükle Butonu (İlişkiler) -->
              <button 
                v-if="allRelations.length > visibleRelationsLimit"
                @click="loadMoreRelations"
                class="w-full mt-4 py-2.5 px-4 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 hover:border-zinc-700 text-zinc-400 hover:text-white font-bold text-xs rounded-xl flex items-center justify-center gap-2 transition-all active:scale-[0.98] shrink-0"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
                Daha Fazla Yükle ({{ allRelations.length - visibleRelationsLimit }} ilişki kaldı)
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
      </div>
    </div>

</template>

<style scoped>
/* Page container level subtle cosmic radial glow */
.bg-radial-gradient {
  background: radial-gradient(circle at 50% 50%, rgba(99, 102, 241, 0.12) 0%, rgba(168, 85, 247, 0.04) 40%, rgba(9, 9, 11, 0) 75%);
  transition: all 0.5s ease;
}

/* Accretion Disk Aura pulsing effect */
.accretion-disk-aura {
  animation: aura-breathe 8s ease-in-out infinite alternate;
  transform-origin: center;
}

@keyframes aura-breathe {
  0% {
    transform: scale(0.92);
    opacity: 0.7;
  }
  100% {
    transform: scale(1.08);
    opacity: 0.95;
  }
}

/* Event Horizon Singularity core pulsate */
.singularity-core {
  animation: core-pulse 4s ease-in-out infinite alternate;
  transform-origin: center;
}

@keyframes core-pulse {
  0% {
    transform: scale(0.95);
    stroke-width: 1.5;
    filter: drop-shadow(0 0 8px rgba(129, 140, 248, 0.4));
  }
  100% {
    transform: scale(1.05);
    stroke-width: 3.5;
    filter: drop-shadow(0 0 16px rgba(168, 85, 247, 0.7));
  }
}

/* Accretion Rings Swirling Animations (Dynamic Speeds) */
.vortex-ring-outer {
  animation: spin-clockwise 24s linear infinite;
  transform-origin: center;
}

.vortex-ring-middle {
  animation: spin-counter-clockwise 16s linear infinite;
  transform-origin: center;
}

.vortex-ring-inner {
  animation: spin-clockwise 8s linear infinite;
  transform-origin: center;
}

/* Swirling spiral accretion arms (winds/rotates fast near core) */
.vortex-spiral-arm {
  transform-origin: center;
}

.vortex-spiral-1 {
  animation: spin-clockwise 14s linear infinite;
}

.vortex-spiral-2 {
  animation: spin-clockwise 18s linear infinite;
}

.vortex-spiral-3 {
  animation: spin-clockwise 22s linear infinite;
}

.vortex-spiral-4 {
  animation: spin-clockwise 26s linear infinite;
}

/* Swirling and sucking space dust particles */
.dust-particle {
  animation: dust-suck 10s linear infinite;
  transform-origin: 0px 0px; /* Center of the black-hole-group! */
  transform-box: view-box;
}

@keyframes dust-suck {
  0% {
    transform: rotate(0deg) scale(1.5);
    opacity: 0;
  }
  15% {
    opacity: 0.7;
  }
  85% {
    opacity: 0.7;
  }
  100% {
    transform: rotate(360deg) scale(0.08);
    opacity: 0;
  }
}

/* Animation Keyframes */
@keyframes spin-clockwise {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

@keyframes spin-counter-clockwise {
  0% {
    transform: rotate(360deg);
  }
  100% {
    transform: rotate(0deg);
  }
}

/* High-performance hardware acceleration */
.black-hole-group circle,
.black-hole-group path,
.dust-particle {
  will-change: transform, opacity;
  transform-box: fill-box;
}

/* Live Graph View Container custom styling */
.live-graph-container {
  box-shadow: inset 0 0 40px rgba(0, 0, 0, 0.8), 0 0 25px rgba(99, 102, 241, 0.05);
  transition: border-color 0.3s, box-shadow 0.3s;
}

.live-graph-container:hover {
  border-color: rgba(99, 102, 241, 0.3);
  box-shadow: inset 0 0 50px rgba(0, 0, 0, 0.9), 0 0 35px rgba(99, 102, 241, 0.08);
}
</style>
