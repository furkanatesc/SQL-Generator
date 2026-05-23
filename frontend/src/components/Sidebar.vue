<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { apiService } from '../services/api';

defineProps<{
  activeTab: string;
}>();

const emit = defineEmits<{
  (e: 'update:activeTab', tab: string): void;
}>();

const apiStatus = ref<'checking' | 'connected' | 'disconnected'>('checking');

const checkHealth = async () => {
  apiStatus.value = 'checking';
  try {
    const res = await apiService.health();
    if (res.status === 'ok') {
      apiStatus.value = 'connected';
    } else {
      apiStatus.value = 'disconnected';
    }
  } catch (e) {
    apiStatus.value = 'disconnected';
  }
};

onMounted(() => {
  checkHealth();
  // Her 15 saniyede bir bağlantıyı tazele
  setInterval(checkHealth, 15000);
});
</script>

<template>
  <aside class="w-64 bg-zinc-950 border-r border-zinc-900 flex flex-col justify-between h-screen sticky top-0">
    <div class="space-y-6 p-5">
      
      <!-- Brand Logo -->
      <div class="flex items-center pb-3 border-b border-zinc-900">
        <h1 class="text-2xl font-bold text-white tracking-wider flex items-center gap-2 select-none">
          <img src="/logo.png" alt="SQLGen Logo" class="w-[72px] h-[72px] drop-shadow-[0_0_8px_rgba(139,92,246,0.8)]" />
          SQL<span class="text-indigo-500 font-extrabold">Gen</span>
        </h1>
      </div>

      <!-- Navigation links -->
      <nav class="space-y-1 text-left">
        <!-- SQL Üretici -->
        <button
          @click="emit('update:activeTab', 'dashboard')"
          :class="[
            'w-full px-3.5 py-2 rounded-lg text-[11px] font-semibold transition-all duration-200 flex items-center gap-2.5',
            activeTab === 'dashboard' 
              ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shadow-sm shadow-indigo-500/5' 
              : 'text-zinc-400 border border-transparent hover:text-zinc-250 hover:bg-zinc-900/30'
          ]"
        >
          <svg xmlns="http://www.w3.org/2500/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          SQL Üretim Merkezi
        </button>

        <!-- Geçmiş -->
        <button
          @click="emit('update:activeTab', 'history')"
          :class="[
            'w-full px-3.5 py-2 rounded-lg text-[11px] font-semibold transition-all duration-200 flex items-center gap-2.5',
            activeTab === 'history' 
              ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shadow-sm shadow-indigo-500/5' 
              : 'text-zinc-400 border border-transparent hover:text-zinc-250 hover:bg-zinc-900/30'
          ]"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Sorgu Geçmişi
        </button>

        <!-- Şema Yöneticisi -->
        <button
          @click="emit('update:activeTab', 'schema')"
          :class="[
            'w-full px-3.5 py-2 rounded-lg text-[11px] font-semibold transition-all duration-200 flex items-center gap-2.5',
            activeTab === 'schema' 
              ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shadow-sm shadow-indigo-500/5' 
              : 'text-zinc-400 border border-transparent hover:text-zinc-250 hover:bg-zinc-900/30'
          ]"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
          </svg>
          Veritabanı Şeması
        </button>

        <!-- RAG Vektör -->
        <button
          @click="emit('update:activeTab', 'rag')"
          :class="[
            'w-full px-3.5 py-2 rounded-lg text-[11px] font-semibold transition-all duration-200 flex items-center gap-2.5',
            activeTab === 'rag' 
              ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shadow-sm shadow-indigo-500/5' 
              : 'text-zinc-400 border border-transparent hover:text-zinc-250 hover:bg-zinc-900/30'
          ]"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
          RAG Vektör Yönetimi
        </button>

        <!-- Ayarlar Başlığı (Non-clickable) -->
        <div class="pt-4 pb-1">
          <span class="px-3.5 text-[10px] font-bold text-zinc-500 uppercase tracking-wider flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            Sistem Ayarları
          </span>
        </div>

        <button
          @click="emit('update:activeTab', 'settings_general')"
          :class="[
            'w-full pl-8 pr-3.5 py-1.5 rounded-lg text-[11px] font-semibold transition-all duration-200 flex items-center gap-2.5',
            activeTab === 'settings_general' 
              ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shadow-sm shadow-indigo-500/5' 
              : 'text-zinc-400 border border-transparent hover:text-zinc-250 hover:bg-zinc-900/30'
          ]"
        >
          Genel Ayarlar
        </button>

        <button
          @click="emit('update:activeTab', 'settings_database')"
          :class="[
            'w-full pl-8 pr-3.5 py-1.5 rounded-lg text-[11px] font-semibold transition-all duration-200 flex items-center gap-2.5',
            activeTab === 'settings_database' 
              ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shadow-sm shadow-indigo-500/5' 
              : 'text-zinc-400 border border-transparent hover:text-zinc-250 hover:bg-zinc-900/30'
          ]"
        >
          Veritabanı Ayarları
        </button>

        <button
          @click="emit('update:activeTab', 'settings_filters')"
          :class="[
            'w-full pl-8 pr-3.5 py-1.5 rounded-lg text-[11px] font-semibold transition-all duration-200 flex items-center gap-2.5',
            activeTab === 'settings_filters' 
              ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shadow-sm shadow-indigo-500/5' 
              : 'text-zinc-400 border border-transparent hover:text-zinc-250 hover:bg-zinc-900/30'
          ]"
        >
          Şema Filtreleri
        </button>
      </nav>
    </div>

    <!-- Bottom System Diagnostic HUD (Car Dashboard Style) -->
    <div class="mt-auto border-t border-zinc-900 bg-zinc-950/80 p-4 space-y-4 font-mono select-none overflow-hidden relative">
      <!-- Background subtle grid -->
      <div class="absolute inset-0 bg-[linear-gradient(to_right,rgba(99,102,241,0.03)_1px,transparent_1px),linear-gradient(to_bottom,rgba(99,102,241,0.03)_1px,transparent_1px)] bg-[size:8px_8px] pointer-events-none"></div>
      
      <!-- Title -->
      <div class="flex items-center gap-2 mb-2 relative z-10">
        <span class="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse shadow-[0_0_8px_rgba(99,102,241,0.8)]"></span>
        <span class="text-[9px] font-bold text-indigo-400 uppercase tracking-widest">SYS_DIAGNOSTICS</span>
      </div>

      <!-- Gauges container -->
      <div class="grid grid-cols-2 gap-3 relative z-10">
        <!-- Latency Gauge -->
        <div class="bg-black/40 rounded border border-zinc-800/60 p-2 flex flex-col items-center justify-center shadow-[inset_0_0_10px_rgba(0,0,0,0.8)]">
          <span class="text-[8px] text-zinc-500 uppercase tracking-wider mb-1">LATENCY</span>
          <div class="text-[13px] font-extrabold text-indigo-400 leading-none">1.24<span class="text-[9px] text-indigo-400/60">s</span></div>
          <span class="text-[7px] text-emerald-400 font-bold mt-1">-%8</span>
        </div>

        <!-- Semantic Cache Gauge -->
        <div class="bg-black/40 rounded border border-zinc-800/60 p-2 flex flex-col items-center justify-center shadow-[inset_0_0_10px_rgba(0,0,0,0.8)]">
          <span class="text-[8px] text-zinc-500 uppercase tracking-wider mb-1">CACHE</span>
          <div class="text-[13px] font-extrabold text-violet-400 leading-none">42<span class="text-[9px] text-violet-400/60"> DDL</span></div>
          <span class="text-[7px] text-zinc-500 font-bold mt-1">Dizinlendi</span>
        </div>
      </div>

      <!-- Single Wide Display for Node -->
      <div class="bg-black/40 rounded border border-zinc-800/60 p-2 shadow-[inset_0_0_10px_rgba(0,0,0,0.8)] relative z-10">
        <div class="flex justify-between items-center mb-1.5">
          <span class="text-[8px] text-zinc-500 uppercase tracking-wider">NODE</span>
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.9)]"></span>
        </div>
        <div class="text-[10px] font-bold text-emerald-300 tracking-wider">Llama-3.3-nim</div>
      </div>

      <!-- Status Bar -->
      <div class="flex justify-between items-center pt-2.5 border-t border-zinc-800/50 relative z-10">
        <!-- Connection state light -->
        <div 
          @click="checkHealth"
          :class="[
            'px-2 py-0.5 rounded-full text-[9px] font-bold tracking-wide cursor-pointer transition-colors flex items-center gap-1',
            apiStatus === 'connected' 
              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
              : apiStatus === 'disconnected'
                ? 'bg-red-500/10 text-red-400 border border-red-500/20 animate-pulse'
                : 'bg-zinc-800 text-zinc-400'
          ]"
          :title="apiStatus === 'connected' ? 'Sunucu Bağlantısı Aktif' : 'Sunucu Çevrimdışı (Yenilemek İçin Tıklayın)'"
        >
          <span 
            :class="[
              'w-1.5 h-1.5 rounded-full',
              apiStatus === 'connected' ? 'bg-emerald-400' : apiStatus === 'disconnected' ? 'bg-red-400' : 'bg-zinc-500 animate-ping'
            ]"
          ></span>
          {{ apiStatus === 'connected' ? 'Lokal' : apiStatus === 'disconnected' ? 'Çevrimdışı' : 'Bağlanıyor' }}
        </div>
        
        <span class="text-[7px] text-zinc-600">©2026 SQLGen</span>
      </div>
    </div>
  </aside>
</template>
