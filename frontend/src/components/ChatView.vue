<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue';
import { apiService } from '../services/api';
import { explainSql } from '../utils/sqlExplain';
import PlanetDbSelector from './PlanetDbSelector.vue';

interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  content?: string;
  sql?: string;
  logs?: Array<{ message: string; step: number; timestamp: string }>;
  status?: 'loading' | 'completed' | 'failed' | 'cancelled';
  error?: string;
  jobId?: string;
}

const dialect = ref('postgres');
const messages = ref<ChatMessage[]>([
  {
    id: Date.now(),
    role: 'assistant',
    content: "Merhaba! Ben SQLGen Asistanı. Doğal dilde sorgunuzu yazabilir veya sağ alt köşedeki ataç simgesine tıklayarak Excel dosyası yükleyebilirsiniz."
  }
]);

const naturalQuery = ref('');
const inputRef = ref<HTMLTextAreaElement | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const selectedFile = ref<File | null>(null);
const loading = ref(false);
const eventSource = ref<EventSource | null>(null);
const activeMessageId = ref<number | null>(null);

// Sorgu Açıklaması paneli — aynı anda tek mesajın paneli açık (msg.id'ye keyed)
const expandedExplanationId = ref<number | null>(null);
const toggleExplanation = (messageId: number) => {
  expandedExplanationId.value = expandedExplanationId.value === messageId ? null : messageId;
};

const triggerFileInput = () => {
  fileInput.value?.click();
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

const scrollToBottom = () => {
  nextTick(() => {
    const container = document.getElementById('chat-scroll-container');
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  });
};

// Per-message copy state — a chat holds many SQL blocks, so keep the "copied"
// affordance keyed by message id. Inline + transient; no blocking alert().
const copiedMessageId = ref<number | null>(null);
const copyErrorMessageId = ref<number | null>(null);
let copyResetTimer: ReturnType<typeof setTimeout> | null = null;

const copyToClipboard = async (sql: string | undefined, messageId: number) => {
  if (!sql) return;
  if (copyResetTimer) { clearTimeout(copyResetTimer); copyResetTimer = null; }
  try {
    await navigator.clipboard.writeText(sql);
    copiedMessageId.value = messageId;
    copyErrorMessageId.value = null;
  } catch {
    // clipboard can reject (permissions / insecure context) — surface it inline
    copyErrorMessageId.value = messageId;
    copiedMessageId.value = null;
  }
  copyResetTimer = setTimeout(() => {
    copiedMessageId.value = null;
    copyErrorMessageId.value = null;
    copyResetTimer = null;
  }, 1600);
};

const startGeneration = async () => {
  if (!naturalQuery.value.trim() && !selectedFile.value) return;

  const query = naturalQuery.value.trim();
  naturalQuery.value = ''; // Input'u temizle
  if (inputRef.value) inputRef.value.style.height = 'auto'; // Reset height

  // Kullanıcı mesajını ekle
  let userContent = query;
  if (selectedFile.value) {
    userContent += `\n[Dosya Ekli: ${selectedFile.value.name}]`;
  }
  
  messages.value.push({
    id: Date.now(),
    role: 'user',
    content: userContent || '[Sadece Dosya Yüklendi]'
  });

  scrollToBottom();

  // Asistan "loading" mesajı oluştur
  const assistantMsgId = Date.now() + 1;
  activeMessageId.value = assistantMsgId;
  const assistantMsg: ChatMessage = {
    id: assistantMsgId,
    role: 'assistant',
    status: 'loading',
    logs: []
  };
  messages.value.push(assistantMsg);
  
  scrollToBottom();
  loading.value = true;

  try {
    try {
      await apiService.setConfig('target_db_type', dialect.value);
    } catch (e) {
      console.warn('Dialect config set failed', e);
    }

    let response;
    // Revizyon için son başarılı SQL'i bul (Eğer Excel yoksa)
    let previousSql = undefined;
    if (!selectedFile.value) {
      const lastAssistantMsg = [...messages.value].reverse().find(m => m.role === 'assistant' && m.sql);
      if (lastAssistantMsg) {
        previousSql = lastAssistantMsg.sql;
      }
    }

    if (selectedFile.value) {
      response = await apiService.uploadFile(selectedFile.value, query);
      selectedFile.value = null; // Dosya kullanıldı, temizle
    } else {
      response = await apiService.startJob(query, previousSql);
    }

    if (response && response.job) {
      const activeMsg = messages.value.find(m => m.id === assistantMsgId);
      if (activeMsg) {
        activeMsg.jobId = response.job.id;
      }
      startSSE(response.job.id, assistantMsgId);
    } else {
      throw new Error('İş başlatılamadı');
    }
  } catch (err: any) {
    loading.value = false;
    const activeMsg = messages.value.find(m => m.id === assistantMsgId);
    if (activeMsg) {
      activeMsg.status = 'failed';
      activeMsg.error = err.message || 'Bir hata oluştu.';
    }
  }
};

const checkJobCompletion = async (jobId: string, msgId: number) => {
  try {
    const job = await apiService.getJob(jobId);
    const activeMsg = messages.value.find(m => m.id === msgId);
    if (!activeMsg) return;

    if (job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') {
      loading.value = false;
      activeMsg.status = job.status;
      if (job.status === 'completed') {
        activeMsg.sql = job.result_sql || '';
      } else if (job.status === 'failed') {
        activeMsg.error = job.error_message || 'Bilinmeyen hata';
      }
      
      if (eventSource.value) {
        eventSource.value.close();
        eventSource.value = null;
      }
      scrollToBottom();
    } else {
      setTimeout(() => checkJobCompletion(jobId, msgId), 1000);
    }
  } catch (e) {
    console.error('Error checking job completion', e);
  }
};

const startSSE = (jobId: string, msgId: number) => {
  if (eventSource.value) {
    eventSource.value.close();
    eventSource.value = null;
  }

  const backendUrl = localStorage.getItem('sqlgen_backend_url') || 'http://127.0.0.1:8000';
  const apiKey = localStorage.getItem('sqlgen_api_key') || 'sqlgen_secret_dev_key';

  const url = `${backendUrl}/api/jobs/${jobId}/stream?api_key=${encodeURIComponent(apiKey)}`;
  const es = new EventSource(url);
  eventSource.value = es;

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data && typeof data === 'object') {
        const activeMsg = messages.value.find(m => m.id === msgId);
        if (activeMsg && activeMsg.logs) {
          activeMsg.logs.push(data);
          scrollToBottom();
          if (data.step === 5) {
            checkJobCompletion(jobId, msgId);
          }
        }
      }
    } catch (e) {
      console.error('SSE parse error', e);
    }
  };

  es.onerror = (err) => {
    console.error('SSE connection error, attempting final job check', err);
    checkJobCompletion(jobId, msgId);
  };
};

const autoResize = () => {
  if (inputRef.value) {
    inputRef.value.style.height = 'auto';
    inputRef.value.style.height = Math.min(inputRef.value.scrollHeight, 150) + 'px';
  }
};

const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    startGeneration();
  }
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
  if (copyResetTimer) clearTimeout(copyResetTimer);
});
</script>

<template>
  <div class="flex flex-col h-[85vh] bg-black/10 backdrop-blur-[2px] rounded-2xl border border-white/10 shadow-2xl relative overflow-hidden">
    
    <!-- Top Header -->
    <div class="flex-none p-4 border-b border-zinc-800/80 bg-zinc-950/50 flex items-center justify-between z-20">
      <div>
        <h2 class="text-lg font-bold text-white flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-indigo-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
          SQL Chat Asistanı
        </h2>
        <p class="text-xs text-zinc-400 mt-0.5">Qdrant RAG destekli akıllı SQL üretim asistanı</p>
      </div>
      <div>
        <PlanetDbSelector v-model="dialect" @change="onDialectChange" />
      </div>
    </div>

    <!-- Chat History Area -->
    <div id="chat-scroll-container" class="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-thin scrollbar-thumb-zinc-700 scrollbar-track-transparent">
      
      <div v-for="msg in messages" :key="msg.id" :class="['flex w-full', msg.role === 'user' ? 'justify-end' : 'justify-start']">
        
        <!-- Assistant Message -->
        <div v-if="msg.role === 'assistant'" class="flex gap-4 max-w-[85%]">
          <div class="flex-none w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center border border-indigo-400/30 shadow-lg mt-1">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          
          <div class="space-y-3 w-full">
            <!-- Text Content -->
            <div v-if="msg.content" class="bg-zinc-900/80 border border-zinc-800 rounded-2xl rounded-tl-sm p-4 text-sm text-zinc-200 leading-relaxed shadow-sm inline-block">
              {{ msg.content }}
            </div>

            <!-- Loading / Logs Accordion -->
            <div v-if="msg.status === 'loading' || (msg.logs && msg.logs.length > 0)" class="w-full max-w-xl">
              <details class="group bg-zinc-950/80 border border-zinc-800 rounded-xl overflow-hidden" :open="msg.status === 'loading'">
                <summary class="flex items-center gap-2 p-3 text-xs font-semibold text-zinc-400 cursor-pointer select-none hover:text-zinc-300 hover:bg-zinc-900/50 transition-colors">
                  <svg v-if="msg.status === 'loading'" class="animate-spin h-4 w-4 text-indigo-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-emerald-500" viewBox="0 0 20 20" fill="currentColor">
                    <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
                  </svg>
                  <span v-if="msg.status === 'loading'">Düşünüyor ve SQL Üretiyor... (RAG Devrede)</span>
                  <span v-else>İşlem Kayıtları (Tıklayarak Gizle/Göster)</span>
                  
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 ml-auto transition-transform group-open:rotate-180" viewBox="0 0 20 20" fill="currentColor">
                    <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd" />
                  </svg>
                </summary>
                
                <div class="p-3 bg-black/40 border-t border-zinc-800 font-mono text-[10px] space-y-1.5 max-h-40 overflow-y-auto">
                  <div v-for="(log, idx) in msg.logs" :key="idx" class="flex items-start gap-2 text-zinc-400">
                    <span class="text-zinc-600">[{{ new Date(log.timestamp).toLocaleTimeString() }}]</span>
                    <span class="px-1 py-0.5 rounded text-[8px] font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 whitespace-nowrap">
                      ADIM {{ log.step }}
                    </span>
                    <span class="text-zinc-300">{{ log.message }}</span>
                  </div>
                </div>
              </details>
            </div>

            <!-- SQL Result Code Block -->
            <div v-if="msg.sql" class="relative group w-full bg-[#0d1117] border border-zinc-700/50 rounded-xl overflow-hidden shadow-xl">
              <div class="flex items-center justify-between px-4 py-2 bg-zinc-800/50 border-b border-zinc-700/50">
                <span class="text-xs font-semibold text-zinc-400">SQL Sorgusu ({{ dialect }})</span>
                <button
                  @click="copyToClipboard(msg.sql, msg.id)"
                  class="text-xs flex items-center gap-1 transition-colors"
                  :class="copyErrorMessageId === msg.id ? 'text-red-400 hover:text-red-300'
                    : copiedMessageId === msg.id ? 'text-emerald-400'
                    : 'text-indigo-400 hover:text-indigo-300'"
                  :title="copiedMessageId === msg.id ? 'Panoya kopyalandı' : 'SQL\'i panoya kopyala'"
                >
                  <svg v-if="copiedMessageId === msg.id" xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                    <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
                  </svg>
                  <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                  </svg>
                  <span aria-live="polite">{{ copiedMessageId === msg.id ? 'Kopyalandı' : copyErrorMessageId === msg.id ? 'Kopyalanamadı' : 'Kopyala' }}</span>
                </button>
              </div>
              <pre class="p-4 overflow-x-auto text-sm text-indigo-200 font-mono leading-relaxed"><code>{{ msg.sql }}</code></pre>

              <!-- Sorgu Açıklaması (deterministik, client-side clause dökümü) -->
              <div class="border-t border-zinc-700/50">
                <button
                  @click="toggleExplanation(msg.id)"
                  class="w-full px-4 py-2 flex items-center justify-between text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
                  :aria-expanded="expandedExplanationId === msg.id"
                >
                  <span class="flex items-center gap-1.5 font-semibold">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Sorgu Açıklaması
                  </span>
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    class="h-3.5 w-3.5 transition-transform duration-200"
                    :class="expandedExplanationId === msg.id ? 'rotate-180' : ''"
                    fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"
                  >
                    <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
                <div v-if="expandedExplanationId === msg.id" class="px-4 pb-3 space-y-1.5">
                  <template v-if="explainSql(msg.sql).length > 0">
                    <div
                      v-for="(clause, ci) in explainSql(msg.sql)"
                      :key="ci"
                      class="text-xs flex flex-col gap-0.5 bg-zinc-900/40 border border-zinc-800 rounded-lg p-2"
                    >
                      <span class="font-semibold text-indigo-300">{{ clause.label }}</span>
                      <code class="text-zinc-300 font-mono break-all whitespace-pre-wrap">{{ clause.body || '—' }}</code>
                    </div>
                  </template>
                  <p v-else class="text-xs text-zinc-500 italic">Açıklama üretilemedi.</p>
                </div>
              </div>
            </div>

            <!-- Error -->
            <div v-if="msg.error" class="bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex gap-3 text-red-200 text-sm">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-red-400 flex-none" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
              </svg>
              <span>{{ msg.error }}</span>
            </div>
            
          </div>
        </div>

        <!-- User Message -->
        <div v-if="msg.role === 'user'" class="flex gap-4 max-w-[75%] flex-row-reverse">
          <div class="flex-none w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center border border-zinc-700 shadow-sm mt-1">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-zinc-400" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clip-rule="evenodd" />
            </svg>
          </div>
          <div class="bg-indigo-600 text-white rounded-2xl rounded-tr-sm p-4 text-sm whitespace-pre-wrap leading-relaxed shadow-lg border border-indigo-500/50">
            {{ msg.content }}
          </div>
        </div>

      </div>
    </div>

    <!-- Input Area (Bottom) -->
    <div class="flex-none p-4 bg-zinc-950/80 border-t border-zinc-800/80 z-20">
      
      <!-- Selected File Preview -->
      <div v-if="selectedFile" class="mb-3 flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-lg px-3 py-1.5 w-max">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M8 4a3 3 0 00-3 3v4a5 5 0 0010 0V7a1 1 0 112 0v4a7 7 0 11-14 0V7a5 5 0 0110 0v4a3 3 0 11-6 0V7a1 1 0 012 0v4a1 1 0 102 0V7a3 3 0 00-3-3z" clip-rule="evenodd" />
        </svg>
        <span class="text-xs font-semibold">{{ selectedFile.name }}</span>
        <button @click="removeFile" class="ml-2 hover:text-emerald-200">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
          </svg>
        </button>
      </div>

      <div class="relative flex items-end gap-2 bg-zinc-900 border border-zinc-700/80 rounded-2xl p-2 shadow-inner focus-within:border-indigo-500/50 focus-within:ring-1 focus-within:ring-indigo-500/30 transition-all">
        
        <!-- Attach Excel Button -->
        <button 
          @click="triggerFileInput"
          class="p-2.5 rounded-xl text-zinc-400 hover:text-indigo-400 hover:bg-zinc-800 transition-colors shrink-0"
          title="Excel Şablonu (AQR) Yükle"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
          </svg>
        </button>
        <input type="file" ref="fileInput" @change="handleFileSelect" accept=".xlsx,.xls" class="hidden" />

        <!-- Textarea -->
        <textarea
          ref="inputRef"
          v-model="naturalQuery"
          @input="autoResize"
          @keydown="handleKeydown"
          :disabled="loading"
          placeholder="Sorgunuzu buraya yazın veya ürettiğim SQL için revizyon isteyin (Örn: Buna doktor adını da ekle)..."
          class="w-full max-h-40 bg-transparent border-none focus:ring-0 text-zinc-200 text-sm py-3 resize-none scrollbar-thin scrollbar-thumb-zinc-700 scrollbar-track-transparent placeholder-zinc-500"
          rows="1"
        ></textarea>

        <!-- Send Button -->
        <button 
          @click="startGeneration"
          :disabled="loading || (!naturalQuery.trim() && !selectedFile)"
          class="p-2.5 rounded-xl shrink-0 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          :class="loading || (!naturalQuery.trim() && !selectedFile) ? 'bg-zinc-800 text-zinc-600' : 'bg-indigo-600 text-white hover:bg-indigo-500 shadow-md shadow-indigo-600/20'"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
          </svg>
        </button>
      </div>
      <p class="text-[10px] text-zinc-500 mt-2 text-center">NVIDIA NIM ve Qdrant RAG Altyapısı kullanılarak çalışır. Göndermek için Enter'a basın.</p>
    </div>
  </div>
</template>

<style scoped>
/* Optional specific overrides if needed */
details > summary {
  list-style: none;
}
details > summary::-webkit-details-marker {
  display: none;
}
</style>
