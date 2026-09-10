<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { apiService } from '../services/api';
import type { Job } from '../services/api';
import { describeError } from '../utils/errorInfo';

const jobs = ref<Job[]>([]);
const loading = ref(false);
const selectedJob = ref<Job | null>(null);
const copySuccess = ref(false);

// Client-side arama + status filtresi (yüklenmiş joblar üzerinde; yeni API çağrısı yok)
const searchText = ref('');
const statusFilter = ref<'all' | Job['status']>('all');

const filteredJobs = computed(() => {
  const q = searchText.value.trim().toLowerCase();
  return jobs.value.filter((job) => {
    if (statusFilter.value !== 'all' && job.status !== statusFilter.value) return false;
    if (!q) return true;
    const haystack = `${job.natural_query ?? ''} ${job.result_sql ?? ''}`.toLowerCase();
    return haystack.includes(q);
  });
});

const clearSearch = () => {
  searchText.value = '';
};

const loadHistory = async () => {
  loading.value = true;
  try {
    const res = await apiService.listJobs(100, 0);
    jobs.value = res.jobs || [];
  } catch (e: any) {
    console.error('History load failed', e);
  } finally {
    loading.value = false;
  }
};

const viewJobDetails = (job: Job) => {
  selectedJob.value = job;
  copySuccess.value = false;
};

const closeDetails = () => {
  selectedJob.value = null;
};

const copySql = () => {
  if (!selectedJob.value?.result_sql) return;
  navigator.clipboard.writeText(selectedJob.value.result_sql);
  copySuccess.value = true;
  setTimeout(() => {
    copySuccess.value = false;
  }, 2000);
};

const cancelJob = async (jobId: string) => {
  if (!confirm('Bu işin yürütülmesini iptal etmek istediğinizden emin misiniz?')) return;
  try {
    const res = await apiService.cancelJob(jobId);
    // Listede güncelle
    const index = jobs.value.findIndex(j => j.id === jobId);
    if (index !== -1) {
      jobs.value[index] = res.job;
    }
    if (selectedJob.value && selectedJob.value.id === jobId) {
      selectedJob.value = res.job;
    }
  } catch (e: any) {
    alert('İş iptal edilemedi: ' + e.message);
  }
};

onMounted(() => {
  loadHistory();
});
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-white tracking-tight">Sorgu Geçmişi</h2>
        <p class="text-zinc-400 text-sm">Geçmişte üretilen tüm SQL sorgularını ve yürütme durumlarını inceleyin.</p>
      </div>
      
      <button 
        @click="loadHistory" 
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
        Yenile
      </button>
    </div>

    <!-- Filtre barı: arama + status -->
    <div v-if="jobs.length > 0" class="flex flex-wrap items-center gap-3">
      <div class="relative flex-1 min-w-[220px]">
        <svg xmlns="http://www.w3.org/2000/svg" class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          v-model="searchText"
          type="text"
          placeholder="Sorgu veya SQL'de ara…"
          class="w-full h-9 pl-9 pr-8 bg-zinc-900 border border-zinc-800 focus:border-indigo-500/60 rounded-xl text-xs text-zinc-200 placeholder-zinc-500 outline-none transition-colors"
        />
        <button
          v-if="searchText"
          @click="clearSearch"
          class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-zinc-500 hover:text-zinc-200"
          title="Aramayı temizle"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      <select
        v-model="statusFilter"
        class="h-9 px-3 bg-zinc-900 border border-zinc-800 focus:border-indigo-500/60 rounded-xl text-xs text-zinc-300 outline-none cursor-pointer transition-colors"
      >
        <option value="all">Tüm durumlar</option>
        <option value="completed">Başarılı</option>
        <option value="failed">Hatalı</option>
        <option value="processing">İşleniyor</option>
        <option value="cancelled">İptal Edildi</option>
        <option value="pending">Beklemede</option>
      </select>
      <span class="text-[11px] text-zinc-500 font-medium tabular-nums">{{ filteredJobs.length }} / {{ jobs.length }} sorgu</span>
    </div>

    <!-- History Table/List -->
    <div class="bg-black/10 backdrop-blur-[1px] rounded-2xl border border-white/10 shadow-lg shadow-black/30 overflow-hidden">
      <div v-if="loading && jobs.length === 0" class="p-12 flex flex-col items-center justify-center space-y-3">
        <svg class="animate-spin h-6 w-6 text-indigo-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <p class="text-xs text-zinc-500 font-medium">Yükleniyor...</p>
      </div>

      <div v-else-if="jobs.length === 0" class="p-16 flex flex-col items-center justify-center text-center space-y-4">
        <div class="w-14 h-14 rounded-2xl bg-zinc-950 border border-zinc-800 flex items-center justify-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-zinc-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div class="space-y-1">
          <h3 class="text-sm font-semibold text-zinc-300">Geçmiş Bulunmamaktadır</h3>
          <p class="text-xs text-zinc-500 max-w-[280px] mx-auto">Henüz hiçbir SQL sorgusu üretilmedi. İlk sorgunuzu SQL Üretim sayfasından yazabilirsiniz.</p>
        </div>
      </div>

      <!-- Filtreyle eşleşen yok -->
      <div v-else-if="filteredJobs.length === 0" class="p-16 flex flex-col items-center justify-center text-center space-y-4">
        <div class="w-14 h-14 rounded-2xl bg-zinc-950 border border-zinc-800 flex items-center justify-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-zinc-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
            <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <div class="space-y-1">
          <h3 class="text-sm font-semibold text-zinc-300">Eşleşen sorgu yok</h3>
          <p class="text-xs text-zinc-500 max-w-[280px] mx-auto">Arama veya durum filtresini değiştirin ya da temizleyin.</p>
        </div>
      </div>

      <div v-else class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="border-b border-zinc-800 bg-zinc-950/20 text-zinc-400 text-[10px] font-bold uppercase tracking-wider">
              <th class="py-4 px-5">Doğal Dil Sorgusu / Dosya</th>
              <th class="py-4 px-5">Hedef DB</th>
              <th class="py-4 px-5">Oluşturma Tarihi</th>
              <th class="py-4 px-5">Durum</th>
              <th class="py-4 px-5 text-right">İşlemler</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-zinc-800/60 text-xs text-zinc-300">
            <tr
              v-for="job in filteredJobs"
              :key="job.id"
              class="hover:bg-zinc-800/10 transition-colors group"
            >
              <!-- Natural Query & File -->
              <td class="py-3.5 px-5 max-w-[340px]">
                <div class="space-y-1">
                  <p class="font-medium text-zinc-200 truncate">{{ job.natural_query || 'Excel AQR Modeli' }}</p>
                  <div v-if="job.file_path" class="flex items-center gap-1 text-[10px] text-indigo-400 font-semibold">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <span>Excel AQR</span>
                  </div>
                </div>
              </td>

              <!-- Target DB (Dialect) -->
              <td class="py-3.5 px-5">
                <div 
                  class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider border"
                  :class="[
                    job.dialect === 'postgres' ? 'bg-blue-500/10 border-blue-500/20 text-blue-400' :
                    job.dialect === 'oracle' ? 'bg-orange-500/10 border-orange-500/20 text-orange-400' :
                    job.dialect === 'sqlite' ? 'bg-slate-500/10 border-slate-500/20 text-slate-400' :
                    'bg-zinc-800 border-zinc-700 text-zinc-400'
                  ]"
                >
                  <div 
                    class="w-1.5 h-1.5 rounded-full"
                    :class="[
                      job.dialect === 'postgres' ? 'bg-blue-400 shadow-[0_0_4px_rgba(96,165,250,0.8)]' :
                      job.dialect === 'oracle' ? 'bg-orange-400 shadow-[0_0_4px_rgba(251,146,60,0.8)]' :
                      job.dialect === 'sqlite' ? 'bg-slate-400 shadow-[0_0_4px_rgba(148,163,184,0.8)]' :
                      'bg-zinc-500'
                    ]"
                  ></div>
                  {{ job.dialect || 'Bilinmiyor' }}
                </div>
              </td>

              <!-- Created At -->
              <td class="py-3.5 px-5 text-zinc-500">
                {{ new Date(job.created_at).toLocaleString() }}
              </td>

              <!-- Status Badge -->
              <td class="py-3.5 px-5">
                <span 
                  v-if="job.status === 'completed'" 
                  class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-bold"
                >
                  <span class="w-1 h-1 rounded-full bg-emerald-400"></span>
                  Başarılı
                </span>
                <span 
                  v-else-if="job.status === 'failed'" 
                  class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-red-500/10 border border-red-500/20 text-red-400 text-[10px] font-bold"
                >
                  <span class="w-1 h-1 rounded-full bg-red-400"></span>
                  Hatalı
                </span>
                <span 
                  v-else-if="job.status === 'processing'" 
                  class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-[10px] font-bold animate-pulse"
                >
                  <span class="w-1 h-1 rounded-full bg-indigo-400 animate-ping"></span>
                  İşleniyor
                </span>
                <span 
                  v-else-if="job.status === 'cancelled'" 
                  class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-zinc-800 border border-zinc-700/60 text-zinc-400 text-[10px] font-bold"
                >
                  İptal Edildi
                </span>
                <span 
                  v-else 
                  class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 text-[10px] font-bold"
                >
                  Beklemede
                </span>
              </td>

              <!-- Actions -->
              <td class="py-3.5 px-5 text-right">
                <div class="flex items-center justify-end gap-2">
                  <button 
                    v-if="['pending', 'processing'].includes(job.status)"
                    @click.stop="cancelJob(job.id)"
                    class="p-1.5 rounded-lg hover:bg-red-500/10 border border-transparent hover:border-red-500/20 text-red-400 opacity-0 group-hover:opacity-100 transition-all duration-200"
                    title="İptal Et"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                    </svg>
                  </button>

                  <button
                    @click="viewJobDetails(job)"
                    class="h-7 px-2.5 bg-zinc-900 border border-zinc-800 text-[10px] font-bold hover:bg-zinc-850 hover:border-zinc-750 text-zinc-300 hover:text-white rounded-lg transition-all"
                  >
                    Detaylar
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Details Modal (Obsidian backdrop slide-in) -->
    <div 
      v-if="selectedJob" 
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 transition-all duration-300"
      @click.self="closeDetails"
    >
      <div class="bg-zinc-950 border border-zinc-800 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl flex flex-col max-h-[90vh] animate-scale-up">
        
        <!-- Modal Header -->
        <div class="p-5 border-b border-zinc-850 bg-zinc-900/40 flex items-center justify-between">
          <div class="text-left space-y-1">
            <h3 class="text-sm font-bold text-white">İş Detayları</h3>
            <p class="text-[10px] text-zinc-500 font-mono">{{ selectedJob.id }}</p>
          </div>
          <button 
            @click="closeDetails" 
            class="p-2 rounded-xl hover:bg-zinc-850 text-zinc-500 hover:text-zinc-200 transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4.5 w-4.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- Modal Content (Scrollable) -->
        <div class="p-6 overflow-y-auto space-y-5 text-left flex-1">
          
          <!-- Natural Language query -->
          <div class="space-y-1.5">
            <h4 class="text-xs font-bold text-zinc-400 uppercase tracking-wider">Doğal Dil İstemi:</h4>
            <div class="bg-zinc-900/60 border border-zinc-850 p-4 rounded-xl text-zinc-200 text-xs italic">
              "{{ selectedJob.natural_query || 'Excel dosyasından yükleme yapıldı.' }}"
            </div>
          </div>

          <!-- Status specific panel -->
          <div v-if="selectedJob.status === 'completed'" class="space-y-2">
            <div class="flex items-center justify-between">
              <h4 class="text-xs font-bold text-zinc-400 uppercase tracking-wider">Üretilen SQL Sorgusu:</h4>
              <button 
                @click="copySql"
                :class="[
                  'px-2.5 py-1.2 rounded-lg border text-[10px] font-bold flex items-center gap-1 transition-all',
                  copySuccess 
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' 
                    : 'bg-zinc-900 hover:bg-zinc-850 border-zinc-800 text-zinc-300'
                ]"
              >
                {{ copySuccess ? 'Kopyalandı!' : 'Kopyala' }}
              </button>
            </div>
            <pre class="bg-zinc-950 border border-zinc-850 p-4 rounded-xl overflow-x-auto text-indigo-300 font-mono text-xs max-h-60 select-all"><code>{{ selectedJob.result_sql }}</code></pre>
          </div>

          <div v-else-if="selectedJob.status === 'failed'" class="space-y-2">
            <h4 class="text-xs font-bold text-red-400 uppercase tracking-wider">Hata Detayı:</h4>
            <!-- 31.5 taksonomi reuse: kategori + etiket + ipucu -->
            <div
              class="rounded-xl p-3 border flex flex-col gap-1"
              :class="describeError(selectedJob.error_code, selectedJob.error_message).tone === 'warning'
                ? 'bg-amber-500/5 border-amber-500/25 text-amber-100'
                : 'bg-red-500/5 border-red-500/25 text-red-200'"
            >
              <div class="flex items-center gap-2 flex-wrap">
                <span class="text-xs font-semibold">{{ describeError(selectedJob.error_code, selectedJob.error_message).label }}</span>
                <span
                  class="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-md border"
                  :class="describeError(selectedJob.error_code, selectedJob.error_message).tone === 'warning'
                    ? 'border-amber-500/30 text-amber-300'
                    : 'border-red-500/30 text-red-300'"
                >{{ describeError(selectedJob.error_code, selectedJob.error_message).categoryLabel }}</span>
              </div>
              <span v-if="describeError(selectedJob.error_code, selectedJob.error_message).hint" class="text-[11px] opacity-75">💡 {{ describeError(selectedJob.error_code, selectedJob.error_message).hint }}</span>
            </div>
            <div v-if="selectedJob.error_message" class="bg-red-500/5 border border-red-500/25 p-4 rounded-xl text-red-200 text-xs font-mono break-all whitespace-pre-wrap">
              {{ selectedJob.error_message }}
            </div>
          </div>

          <div v-else class="p-8 text-center bg-zinc-900/40 rounded-xl border border-zinc-850 flex flex-col items-center justify-center space-y-3">
            <div class="w-10 h-10 rounded-full border-2 border-indigo-500/30 border-t-indigo-500 animate-spin"></div>
            <p class="text-xs text-zinc-400">İşlem henüz tamamlanmadı. Durum: <strong class="text-indigo-400 uppercase">{{ selectedJob.status }}</strong></p>
          </div>

          <!-- Metadata info -->
          <div class="grid grid-cols-2 gap-4 pt-3 border-t border-zinc-900 text-[10px] text-zinc-500 font-medium">
            <div class="space-y-1">
              <p>Oluşturulma: <span class="text-zinc-400">{{ new Date(selectedJob.created_at).toLocaleString() }}</span></p>
              <p>Son Güncelleme: <span class="text-zinc-400">{{ new Date(selectedJob.updated_at).toLocaleString() }}</span></p>
            </div>
            <div class="space-y-1 text-right">
              <p>Dosya: <span class="text-zinc-400">{{ selectedJob.file_path ? 'Yüklendi (Excel)' : 'Yok' }}</span></p>
              <p>Diyalekt: <span class="text-zinc-400 capitalize">{{ selectedJob.dialect || 'Bilinmiyor' }}</span></p>
              <p>Yürütme Durumu: <span class="text-zinc-400 capitalize">{{ selectedJob.status }}</span></p>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<style scoped>
.animate-scale-up {
  animation: scaleUp 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

@keyframes scaleUp {
  from {
    transform: scale(0.95);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}
</style>
