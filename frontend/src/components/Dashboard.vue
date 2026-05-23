<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue';
import { apiService } from '../services/api';
import type { Job } from '../services/api';
import PlanetDbSelector from './PlanetDbSelector.vue';

const naturalQuery = ref('');
const dialect = ref('postgres');
const selectedFile = ref<File | null>(null);
const dragOver = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);

const triggerFileInput = () => {
  fileInput.value?.click();
};

const loading = ref(false);
const activeJob = ref<Job | null>(null);
const currentStep = ref(0);
const eventSource = ref<EventSource | null>(null);
const liveLogs = ref<Array<{ message: string; step: number; timestamp: string }>>([]);
const copySuccess = ref(false);

const steps = [
  { id: 1, name: 'Excel Analizi ve Yapısal Dönüşüm (AQR)', desc: 'Excel kolonları ve iş kuralları ayrıştırılıyor.' },
  { id: 2, name: 'Deterministik Şema Budama', desc: 'Veritabanı şeması %90+ oranında bağlama göre küçültülüyor.' },
  { id: 3, name: 'LLM SQL Üretimi (Writer Agent)', desc: 'NVIDIA NIM Llama-3.3 ile ilk taslak sorgu yazılıyor.' },
  { id: 4, name: 'SQLGLOT AST Doğrulama', desc: 'Sözdizimi ve diyalekt kuralları doğrulanıyor.' },
  { id: 5, name: 'Eleştirmen Ajan Düzeltmesi (Critic Loop)', desc: 'AST hataları iteratif olarak gideriliyor.' }
];

const handleFileDrop = (e: DragEvent) => {
  dragOver.value = false;
  const files = e.dataTransfer?.files;
  if (files && files.length > 0) {
    const file = files[0];
    if (file.name.endsWith('.xlsx') || file.name.endsWith('.xls')) {
      selectedFile.value = file;
    } else {
      alert('Yalnızca Excel (.xlsx, .xls) dosyaları desteklenir.');
    }
  }
};

const handleFileSelect = (e: Event) => {
  const target = e.target as HTMLInputElement;
  const files = target.files;
  if (files && files.length > 0) {
    selectedFile.value = files[0];
  }
};

const removeFile = () => {
  selectedFile.value = null;
};

const startGeneration = async () => {
  if (!naturalQuery.value && !selectedFile.value) return;

  loading.value = true;
  activeJob.value = null;
  currentStep.value = 1;
  copySuccess.value = false;
  liveLogs.value = [];

  try {
    let response;
    
    // Config target dialect'i güncelle
    try {
      await apiService.setConfig('target_db_type', dialect.value);
    } catch (e) {
      console.warn('Dialect config set failed', e);
    }

    if (selectedFile.value) {
      response = await apiService.uploadFile(selectedFile.value, naturalQuery.value);
    } else {
      response = await apiService.startJob(naturalQuery.value);
    }

    if (response && response.job) {
      activeJob.value = response.job;
      startSSE(response.job.id);
    } else {
      throw new Error('İş başlatılamadı');
    }
  } catch (err: any) {
    loading.value = false;
    alert(err.message || 'Bir hata oluştu.');
  }
};

const checkJobCompletion = async (jobId: string) => {
  try {
    const job = await apiService.getJob(jobId);
    activeJob.value = job;
    if (job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') {
      loading.value = false;
      if (eventSource.value) {
        eventSource.value.close();
        eventSource.value = null;
      }
    } else {
      // Eğer iş bitmediyse 1 saniye sonra tekrar sorgula
      setTimeout(() => checkJobCompletion(jobId), 1000);
    }
  } catch (e) {
    console.error('Error checking job completion', e);
  }
};

const startSSE = (jobId: string) => {
  if (eventSource.value) {
    eventSource.value.close();
    eventSource.value = null;
  }

  liveLogs.value = [];
  currentStep.value = 1;

  const backendUrl = localStorage.getItem('sqlgen_backend_url') || 'http://127.0.0.1:8000';
  const apiKey = localStorage.getItem('sqlgen_api_key') || 'sqlgen_secret_dev_key';

  const url = `${backendUrl}/api/jobs/${jobId}/stream?api_key=${encodeURIComponent(apiKey)}`;
  const es = new EventSource(url);
  eventSource.value = es;

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data && typeof data === 'object') {
        liveLogs.value.push(data);
        if (data.step) {
          currentStep.value = data.step;
        }

        // Konsol çıktısını otomatik aşağı kaydır
        nextTick(() => {
          const container = document.getElementById('live-console-logs');
          if (container) {
            container.scrollTop = container.scrollHeight;
          }
        });

        // 5. adım son adımdır, işin tamamlanıp tamamlanmadığını kontrol etmeye başla
        if (data.step === 5) {
          checkJobCompletion(jobId);
        }
      }
    } catch (e) {
      console.error('SSE parse error', e);
    }
  };

  es.onerror = (err) => {
    console.error('SSE connection error, attempting final job check', err);
    // Hata durumunda veya bağlantı kapandığında iş durumunu son kez kontrol et
    checkJobCompletion(jobId);
  };
};

const cancelActiveJob = async () => {
  if (!activeJob.value) return;
  try {
    const res = await apiService.cancelJob(activeJob.value.id);
    activeJob.value = res.job;
    loading.value = false;
    if (eventSource.value) {
      eventSource.value.close();
      eventSource.value = null;
    }
  } catch (e: any) {
    alert('İş iptal edilemedi: ' + e.message);
  }
};

const copyToClipboard = () => {
  if (!activeJob.value?.result_sql) return;
  navigator.clipboard.writeText(activeJob.value.result_sql);
  copySuccess.value = true;
  setTimeout(() => {
    copySuccess.value = false;
  }, 2000);
};

const onDialectChange = async (newDialect: string) => {
  try {
    await apiService.setConfig('target_db_type', newDialect);
  } catch (e) {
    console.warn('Dialect config set failed', e);
  }
};

onMounted(async () => {
  try {
    const res = await apiService.getConfig('target_db_type');
    if (res.value) dialect.value = res.value;
  } catch (e) {
    console.warn('Could not load target db type', e);
  }
});

onUnmounted(() => {
  if (eventSource.value) {
    eventSource.value.close();
    eventSource.value = null;
  }
});
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-white tracking-tight">SQL Üretim Merkezi</h2>
        <p class="text-zinc-400 text-sm">Doğal dil sorguları ve Excel şablonlarını kullanarak optimize SQL üretin.</p>
      </div>
      
      <!-- Dialect Selector (Animated Planets) -->
      <div class="flex items-center">
        <PlanetDbSelector v-model="dialect" @change="onDialectChange" />
      </div>
    </div>

    <!-- Main Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
      
      <!-- Input Panel (Left) -->
      <div class="lg:col-span-5 space-y-6">
        <div class="bg-black/10 backdrop-blur-[1px] rounded-2xl border border-white/10 shadow-lg shadow-black/30 p-5 space-y-5">
          
          <!-- Natural Query -->
          <div class="space-y-2">
            <label class="block text-xs font-semibold text-zinc-300 uppercase tracking-wider">Doğal Dil Sorgusu</label>
            <textarea
              v-model="naturalQuery"
              placeholder="Örn: Bölüm bütçesi 50.000'den büyük olan ve Ankara'da çalışan personellerin isimlerini ve departmanlarını listele..."
              class="w-full h-36 bg-zinc-950/80 border border-zinc-800/80 rounded-xl px-4 py-3 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-indigo-500/80 focus:ring-1 focus:ring-indigo-500/30 transition-all resize-none"
            ></textarea>
          </div>

          <!-- File Upload Zone -->
          <div class="space-y-2">
            <label class="block text-xs font-semibold text-zinc-300 uppercase tracking-wider">Excel Şablonu Yükle (AQR - İsteğe Bağlı)</label>
            
            <div
              @dragover.prevent="dragOver = true"
              @dragleave="dragOver = false"
              @drop.prevent="handleFileDrop"
              :class="[
                'border-2 border-dashed rounded-xl p-5 flex flex-col items-center justify-center cursor-pointer transition-all duration-200 min-h-[140px]',
                dragOver ? 'border-indigo-500 bg-indigo-500/5' : 'border-zinc-800/80 hover:border-zinc-700 bg-zinc-950/40',
                selectedFile ? 'border-emerald-500/50 bg-emerald-500/5' : ''
              ]"
              @click="triggerFileInput"
            >
              <input 
                type="file" 
                ref="fileInput" 
                @change="handleFileSelect" 
                accept=".xlsx,.xls" 
                class="hidden" 
              />
              
              <!-- Icon/Text states -->
              <div v-if="!selectedFile" class="text-center space-y-2.5">
                <div class="w-10 h-10 rounded-xl bg-zinc-900 flex items-center justify-center mx-auto border border-zinc-800">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-indigo-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
                <div class="space-y-1">
                  <p class="text-xs font-semibold text-zinc-200">Dosyayı buraya sürükleyin veya göz atın</p>
                  <p class="text-[10px] text-zinc-500">Sadece Excel (.xlsx, .xls) dosyaları</p>
                </div>
              </div>

              <!-- Selected File state -->
              <div v-else class="w-full flex items-center justify-between p-1.5">
                <div class="flex items-center gap-3">
                  <div class="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <div class="text-left">
                    <p class="text-xs font-semibold text-zinc-200 max-w-[200px] truncate">{{ selectedFile.name }}</p>
                    <p class="text-[10px] text-zinc-500">{{ (selectedFile.size / 1024).toFixed(1) }} KB</p>
                  </div>
                </div>
                <button 
                  @click.stop="removeFile" 
                  class="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-200 transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          </div>

          <!-- Action Button -->
          <button
            @click="startGeneration"
            :disabled="(!naturalQuery && !selectedFile) || loading"
            class="w-full h-11 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 active:scale-[0.98] disabled:from-zinc-800 disabled:to-zinc-850 disabled:text-zinc-600 disabled:cursor-not-allowed text-white font-semibold text-sm rounded-xl shadow-lg shadow-indigo-600/10 hover:shadow-indigo-600/20 active:shadow-none transition-all duration-200 flex items-center justify-center gap-2"
          >
            <template v-if="loading">
              <svg class="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Sorgu Üretiliyor...
            </template>
            <template v-else>
              SQL Sorgusu Üret
            </template>
          </button>

        </div>
      </div>

      <!-- Results/Progress Panel (Right) -->
      <div class="lg:col-span-7 space-y-6">
        <div class="bg-black/10 backdrop-blur-[1px] rounded-2xl border border-white/10 shadow-lg shadow-black/30 p-5 min-h-[460px] flex flex-col">
          
          <!-- State 1: Idle -->
          <div v-if="!loading && !activeJob" class="flex-1 flex flex-col items-center justify-center text-center p-8 space-y-4">
            <div class="w-16 h-16 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center shadow-inner">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-7 w-7 text-zinc-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <path stroke-linecap="round" stroke-linejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
            <div class="space-y-1 max-w-[280px]">
              <h3 class="text-sm font-semibold text-zinc-300">İşlem Bekleniyor</h3>
              <p class="text-xs text-zinc-500">Soldaki alanları doldurarak ilk SQL üretim sürecinizi tetikleyin.</p>
            </div>
          </div>

          <!-- State 2: Loading (Progress Tracking) -->
          <div v-else-if="loading && activeJob" class="flex-1 flex flex-col justify-between space-y-6">
            <div class="space-y-4">
              <div class="flex items-center justify-between">
                <span class="text-xs font-semibold text-indigo-400 uppercase tracking-wider">İşlem Yürütülüyor</span>
                <button 
                  @click="cancelActiveJob"
                  class="px-2.5 py-1 text-[10px] font-semibold text-red-400 hover:text-red-300 bg-red-500/10 border border-red-500/20 hover:border-red-500/30 rounded-lg transition-all"
                >
                  İptal Et
                </button>
              </div>

              <!-- Pipeline step tracker -->
              <div class="space-y-3.5">
                <div 
                  v-for="step in steps" 
                  :key="step.id"
                  :class="[
                    'p-3.5 rounded-xl border flex items-start gap-3.5 transition-all duration-300',
                    currentStep >= step.id 
                      ? 'border-indigo-500/30 bg-indigo-500/5' 
                      : 'border-zinc-800 bg-zinc-950/20 opacity-40'
                  ]"
                >
                  <!-- Step Indicator -->
                  <div class="relative mt-0.5">
                    <div 
                      v-if="currentStep > step.id" 
                      class="w-5 h-5 rounded-full bg-emerald-500/20 border border-emerald-500 flex items-center justify-center"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3 text-emerald-400" viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
                      </svg>
                    </div>
                    <div 
                      v-else-if="currentStep === step.id"
                      class="w-5 h-5 rounded-full bg-indigo-600/30 border border-indigo-500 flex items-center justify-center animate-pulse"
                    >
                      <span class="w-1.5 h-1.5 rounded-full bg-indigo-400"></span>
                    </div>
                    <div 
                      v-else
                      class="w-5 h-5 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center text-[10px] text-zinc-500 font-semibold"
                    >
                      {{ step.id }}
                    </div>
                  </div>
                  
                  <div class="text-left space-y-0.5">
                    <h4 class="text-xs font-semibold text-zinc-200">{{ step.name }}</h4>
                    <p class="text-[10px] text-zinc-500">{{ step.desc }}</p>
                  </div>
                </div>
              </div>

              <!-- Live Console Logs (SSE) -->
              <div class="space-y-2 text-left pt-2 border-t border-zinc-800/60">
                <label class="block text-[10px] font-bold text-zinc-400 uppercase tracking-wider">Canlı İşlem Konsolu (SSE)</label>
                <div 
                  id="live-console-logs"
                  class="h-28 bg-zinc-950/80 border border-zinc-800/80 rounded-xl p-3 font-mono text-[10px] overflow-y-auto space-y-1.5 scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent shadow-inner text-left"
                >
                  <div v-if="liveLogs.length === 0" class="text-zinc-650 italic">
                    Konsol bağlantısı bekleniyor...
                  </div>
                  <div 
                    v-for="(log, idx) in liveLogs" 
                    :key="idx"
                    class="flex items-start gap-2 text-zinc-350 leading-relaxed text-left"
                  >
                    <span class="text-zinc-600 select-none">[{{ new Date(log.timestamp).toLocaleTimeString() }}]</span>
                    <span 
                      :class="[
                        'px-1 py-0.5 rounded text-[8px] font-semibold tracking-wide uppercase',
                        log.step === 1 ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20' :
                        log.step === 2 ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20' :
                        log.step === 3 ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' :
                        log.step === 4 ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                        'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      ]"
                    >
                      ADIM {{ log.step }}
                    </span>
                    <span class="flex-1 text-zinc-200 text-left whitespace-pre-wrap">{{ log.message }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Loading Bottom Status -->
            <div class="bg-zinc-950/80 border border-zinc-800 p-3.5 rounded-xl flex items-center gap-3.5">
              <div class="w-2 h-2 rounded-full bg-indigo-500 animate-ping"></div>
              <p class="text-xs text-zinc-400">Lokal orkestratör çalışıyor. İş Kimliği: <code class="text-indigo-400 text-[10px]">{{ activeJob.id }}</code></p>
            </div>
          </div>

          <!-- State 3: Completed Successfully -->
          <div v-else-if="!loading && activeJob && activeJob.status === 'completed'" class="flex-1 flex flex-col justify-between space-y-5">
            <div class="space-y-4 flex-1">
              
              <!-- Result Title -->
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                  <span class="text-xs font-bold text-emerald-400 uppercase tracking-wider">SQL ÜRETİMİ BAŞARILI</span>
                </div>
                
                <!-- Copy Button -->
                <button
                  @click="copyToClipboard"
                  :class="[
                    'px-3 py-1.5 rounded-lg border text-xs font-semibold flex items-center gap-1.5 transition-all duration-200',
                    copySuccess 
                      ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' 
                      : 'bg-zinc-900 hover:bg-zinc-850 border-zinc-800 text-zinc-300 hover:text-white'
                  ]"
                >
                  <template v-if="copySuccess">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                      <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
                    </svg>
                    Kopyalandı!
                  </template>
                  <template v-else>
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                    </svg>
                    SQL Kopyala
                  </template>
                </button>
              </div>

              <!-- SQL Query Display -->
              <div class="relative group flex-1 min-h-[220px] flex flex-col">
                <pre class="flex-1 w-full bg-zinc-950 border border-zinc-800 p-4 rounded-xl text-left overflow-auto font-mono text-xs text-indigo-200 select-all max-h-[300px]"><code>{{ activeJob.result_sql }}</code></pre>
              </div>

              <!-- Original Prompt Details -->
              <div class="bg-zinc-950/40 border border-zinc-850 p-4 rounded-xl text-left space-y-2">
                <h4 class="text-xs font-semibold text-zinc-300">Sorgu Detayları:</h4>
                <p class="text-xs text-zinc-400 italic">"{{ activeJob.natural_query || 'Excel AQR Şablon Girişi' }}"</p>
                <div class="flex items-center gap-4 text-[10px] text-zinc-500 pt-1 border-t border-zinc-900">
                  <span>Diyalekt: <strong class="text-zinc-400 capitalize">{{ dialect }}</strong></span>
                  <span>Tarih: <strong class="text-zinc-400">{{ new Date(activeJob.updated_at).toLocaleString() }}</strong></span>
                </div>
              </div>

            </div>
          </div>

          <!-- State 4: Failed -->
          <div v-else-if="!loading && activeJob && activeJob.status === 'failed'" class="flex-1 flex flex-col justify-between space-y-5">
            <div class="space-y-4 text-left">
              
              <!-- Result Title -->
              <div class="flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-red-500"></span>
                <span class="text-xs font-bold text-red-400 uppercase tracking-wider">SQL ÜRETİMİ BAŞARISIZ OLDU</span>
              </div>

              <!-- Error Box -->
              <div class="bg-red-500/5 border border-red-500/20 p-4 rounded-xl space-y-3">
                <div class="flex items-start gap-2.5">
                  <div class="w-5 h-5 rounded-md bg-red-500/10 flex items-center justify-center border border-red-500/20 mt-0.5">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                  </div>
                  <div>
                    <h4 class="text-xs font-semibold text-red-200">Hata Mesajı:</h4>
                    <p class="text-xs text-red-300/90 mt-1 font-mono break-words">{{ activeJob.error_message }}</p>
                  </div>
                </div>
              </div>

              <!-- Troubleshoot advice -->
              <div class="bg-zinc-950/60 border border-zinc-800 p-4 rounded-xl space-y-2">
                <h4 class="text-xs font-semibold text-zinc-300">Önerilen Çözüm Adımları:</h4>
                <ul class="text-[11px] text-zinc-500 space-y-1 list-disc list-inside">
                  <li><strong>Ayarlar Sayfası:</strong> NVIDIA API Key'inizin geçerli olduğunu kontrol edin.</li>
                  <li><strong>Veritabanı Şeması:</strong> Target veritabanı şemasının doğru yüklendiğinden emin olun.</li>
                  <li><strong>Sorgu Doğruluğu:</strong> Sorgu metninde yabancı kelimeleri veya karmaşık yapıları sadeleştirin.</li>
                </ul>
              </div>

            </div>

            <!-- Retry button -->
            <button
              @click="startGeneration"
              class="w-full h-10 bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 text-zinc-300 hover:text-white font-semibold text-sm rounded-xl transition-all"
            >
              Yeniden Dene
            </button>
          </div>

        </div>
      </div>

    </div>
  </div>
</template>
