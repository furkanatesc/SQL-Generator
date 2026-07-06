// Sinaps darbe zamanlayıcısı — render'dan bağımsız saf durum makinesi.
// Zaman parametre olarak alınır (test edilebilirlik); render döngüsü
// clock.getElapsedTime() geçirir. Ambient ateşleme + zincirleme sıçrama +
// eşzamanlılık sınırı burada; shader yalnız aktif darbe listesini çizer.
import type { SynapseLayout } from './synapseLayout.ts';
import { mulberry32 } from './seededRandom.ts';

export interface PulseSpec {
  edgeIndex: number;
  direction: 1 | -1;
  startTime: number;
  duration: number;
  generation: number;
}

export interface PulseSchedulerOptions {
  seed?: number;
  maxConcurrent?: number;
  intervalMinSec?: number;
  intervalMaxSec?: number;
  maxHops?: number;
  pulseDurationSec?: number;
}

interface IncidentEdge { edgeIndex: number; otherNode: number; direction: 1 | -1 }
interface ActivePulse extends PulseSpec { arrivalNode: number }

export class PulseScheduler {
  private readonly rand: () => number;
  private readonly maxConcurrent: number;
  private readonly intervalMin: number;
  private readonly intervalMax: number;
  private readonly maxHops: number;
  private readonly duration: number;
  private readonly incidents: IncidentEdge[][];
  private readonly indexById: Map<string, number>;
  private active: ActivePulse[] = [];
  private nextAmbientAt: number | null = null;
  private enabled = true;

  constructor(layout: SynapseLayout, opts: PulseSchedulerOptions = {}) {
    this.rand = mulberry32(opts.seed ?? 1);
    this.maxConcurrent = opts.maxConcurrent ?? 8;
    this.intervalMin = opts.intervalMinSec ?? 2;
    this.intervalMax = opts.intervalMaxSec ?? 4;
    this.maxHops = opts.maxHops ?? 2;
    this.duration = opts.pulseDurationSec ?? 0.9;
    this.indexById = new Map(layout.nodes.map((nd, i) => [nd.id, i]));
    this.incidents = layout.nodes.map(() => []);
    layout.edges.forEach((e, edgeIndex) => {
      this.incidents[e.sourceIndex].push({ edgeIndex, otherNode: e.targetIndex, direction: 1 });
      this.incidents[e.targetIndex].push({ edgeIndex, otherNode: e.sourceIndex, direction: -1 });
    });
  }

  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
    if (!enabled) {
      this.active = [];
      this.nextAmbientAt = null;
    }
  }

  fire(nodeIds: string[], now: number): void {
    if (!this.enabled) return;
    for (const id of nodeIds) {
      const node = this.indexById.get(id);
      if (node === undefined) continue;
      this.spawnFromNode(node, now, 0);
    }
  }

  tick(now: number): PulseSpec[] {
    if (!this.enabled) return [];

    const finished = this.active.filter((p) => now >= p.startTime + p.duration);
    this.active = this.active.filter((p) => now < p.startTime + p.duration);
    for (const p of finished) {
      if (p.generation < this.maxHops) {
        this.spawnFromNode(p.arrivalNode, now, p.generation + 1, p.edgeIndex);
      }
    }

    if (this.nextAmbientAt === null) this.nextAmbientAt = now + this.nextInterval();
    if (now >= this.nextAmbientAt) {
      const candidates: number[] = [];
      this.incidents.forEach((inc, i) => { if (inc.length > 0) candidates.push(i); });
      if (candidates.length > 0) {
        this.spawnFromNode(candidates[Math.floor(this.rand() * candidates.length)], now, 0);
      }
      this.nextAmbientAt = now + this.nextInterval();
    }

    return this.active.map(({ arrivalNode: _arrival, ...spec }) => spec);
  }

  private nextInterval(): number {
    return this.intervalMin + this.rand() * (this.intervalMax - this.intervalMin);
  }

  private spawnFromNode(node: number, now: number, generation: number, excludeEdge?: number): void {
    if (this.active.length >= this.maxConcurrent) return;
    const options = this.incidents[node].filter((ie) => ie.edgeIndex !== excludeEdge);
    if (options.length === 0) return;
    const pick = options[Math.floor(this.rand() * options.length)];
    this.active.push({
      edgeIndex: pick.edgeIndex,
      direction: pick.direction,
      startTime: now,
      duration: this.duration,
      generation,
      arrivalNode: pick.otherNode,
    });
  }
}
