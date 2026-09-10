<script setup lang="ts">
import { computed } from 'vue';
import type { QueryResult } from '../services/api';

const props = defineProps<{ result: QueryResult }>();

const rowCount = computed(() => props.result.rows?.length ?? 0);
const hasRows = computed(() => rowCount.value > 0);

// null/undefined hücreleri "NULL" olarak göster; diğerlerini string'e çevir
const displayCell = (value: unknown): string => {
  if (value === null || value === undefined) return 'NULL';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};
</script>

<template>
  <div class="w-full bg-[#0d1117] border border-zinc-700/50 rounded-xl overflow-hidden">
    <!-- Üst bar: satır sayısı + süre + truncated rozeti -->
    <div class="flex items-center justify-between gap-2 px-4 py-2 bg-zinc-800/50 border-b border-zinc-700/50 text-xs">
      <span class="font-semibold text-zinc-400">
        Sonuç · {{ rowCount }} satır
        <span v-if="result.columns?.length" class="text-zinc-500">/ {{ result.columns.length }} sütun</span>
      </span>
      <span class="flex items-center gap-2">
        <span v-if="result.duration_ms != null" class="text-zinc-500 font-mono">{{ result.duration_ms }} ms</span>
        <span
          v-if="result.truncated"
          class="text-amber-300 bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 rounded-md"
          title="Sonuç satır limitine ulaştığı için kesildi"
        >kesildi</span>
      </span>
    </div>

    <!-- Boş sonuç durumu -->
    <div v-if="!hasRows" class="px-4 py-6 text-center text-xs text-zinc-500 italic">
      Sonuç boş (0 satır döndü).
    </div>

    <!-- Sonuç tablosu -->
    <div v-else class="overflow-x-auto">
      <table class="w-full text-xs border-collapse">
        <thead>
          <tr class="bg-zinc-900/40">
            <th
              v-for="(col, ci) in result.columns"
              :key="ci"
              scope="col"
              class="text-left font-semibold text-indigo-300 font-mono px-3 py-2 border-b border-zinc-800 whitespace-nowrap sticky top-0 bg-zinc-900/80 backdrop-blur"
            >{{ col }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, ri) in result.rows"
            :key="ri"
            class="hover:bg-zinc-900/30 transition-colors"
          >
            <td
              v-for="(cell, cci) in row"
              :key="cci"
              class="px-3 py-1.5 border-b border-zinc-900 font-mono text-zinc-300 align-top"
              :class="cell === null || cell === undefined ? 'text-zinc-600 italic' : ''"
            >{{ displayCell(cell) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
