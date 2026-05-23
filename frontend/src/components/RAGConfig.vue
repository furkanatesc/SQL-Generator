<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { apiService } from '../services/api';

const stats = ref<Record<string, number>>({
  schema_ddl: 0,
  business_rules: 0,
  sql_history: 0
});
const loadingStats = ref(false);

// Search states
const searchQuery = ref('');
const searchCollection = ref('business_rules');
const searchLimit = ref(3);
const searchResults = ref<any[]>([]);
const searching = ref(false);
const searchError = ref('');

// Indexing states
const indexMode = ref('business_rule'); // business_rule | sql_history
const ruleId = ref('');
const ruleText = ref('');
const ruleSql = ref('');

const historyId = ref('');
const historyNatural = ref('');
const historySql = ref('');

const indexing = ref(false);
const indexSuccess = ref(false);
const indexError = ref('');

const loadStats = async () => {
  loadingStats.value = true;
  try {
    const res = await apiService.getRagStats();
    if (res.status === 'success') {
      stats.value = res.stats;
    }
  } catch (e: any) {
    console.error('Failed to load RAG stats', e);
  } finally {
    loadingStats.value = false;
  }
};

const executeSearch = async () => {
  if (!searchQuery.value) return;
  searching.value = true;
  searchError.value = '';
  searchResults.value = [];
  try {
    const res = await apiService.searchRag(searchQuery.value, searchCollection.value, searchLimit.value);
    if (res.status === 'success') {
      searchResults.value = res.results || [];
    }
  } catch (e: any) {
    searchError.value = e.message || 'Semantik arama başarısız oldu. NVIDIA API Anahtarınızı kontrol edin.';
  } finally {
    searching.value = false;
  }
};

const handleIndex = async () => {
  indexing.value = true;
  indexError.value = '';
  indexSuccess.value = false;

  try {
    if (indexMode.value === 'business_rule') {
      if (!ruleId.value || !ruleText.value || !ruleSql.value) {
        throw new Error('Lütfen tüm alanları doldurun.');
      }
      await apiService.indexBusinessRule(ruleId.value, ruleText.value, ruleSql.value);
      ruleId.value = '';
      ruleText.value = '';
      ruleSql.value = '';
    } else {
      if (!historyId.value || !historyNatural.value || !historySql.value) {
        throw new Error('Lütfen tüm alanları doldurun.');
      }
      await apiService.indexSqlHistory(historyId.value, historyNatural.value, historySql.value);
      historyId.value = '';
      historyNatural.value = '';
      historySql.value = '';
    }
    indexSuccess.value = true;
    await loadStats();
    setTimeout(() => {
      indexSuccess.value = false;
    }, 3000);
  } catch (e: any) {
    indexError.value = e.message || 'İndeksleme başarısız oldu. API anahtarınızı denetleyin.';
  } finally {
    indexing.value = false;
  }
};

onMounted(() => {
  loadStats();
});
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-white tracking-tight">RAG Vektör Yönetimi</h2>
        <p class="text-zinc-400 text-sm">Lokal Qdrant vektör tabanı indekslerini izleyin, semantik arama yapın ve iş kuralları ekleyin.</p>
      </div>

      <button 
        @click="loadStats" 
        :disabled="loadingStats"
        class="h-9 px-4 bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 text-zinc-300 hover:text-white font-semibold text-xs rounded-xl flex items-center gap-2 transition-all"
      >
        Yenile
      </button>
    </div>

    <!-- Collection Stats Row -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
      <div 
        v-for="(count, name) in stats" 
        :key="name"
        class="bg-black/10 backdrop-blur-[1px] rounded-2xl border border-white/10 shadow-lg shadow-black/30 p-5 text-left flex items-center gap-4 relative overflow-hidden"
      >
        <div class="w-12 h-12 rounded-xl bg-zinc-950 border border-zinc-850 flex items-center justify-center text-indigo-400">
          <svg v-if="name === 'schema_ddl'" xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
          <svg v-else-if="name === 'business_rules'" xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
          </svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div>
          <h4 class="text-xs font-bold text-zinc-500 uppercase tracking-wider">
            {{ name === 'schema_ddl' ? 'ŞEMA DDL DİZİNİ' : name === 'business_rules' ? 'İŞ KURALLARI DİZİNİ' : 'GEÇMİŞ SQL ÇİFTLERİ' }}
          </h4>
          <p class="text-2xl font-bold text-white font-mono mt-0.5">{{ count }} <span class="text-xs text-zinc-500 font-sans font-normal">Kayıt</span></p>
        </div>
      </div>
    </div>

    <!-- Main Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
      
      <!-- Semantic Search Panel (Left) -->
      <div class="lg:col-span-7 space-y-6">
        <div class="bg-black/10 backdrop-blur-[1px] rounded-2xl border border-white/10 shadow-lg shadow-black/30 p-5 min-h-[460px] flex flex-col justify-start">
          <h3 class="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-4 text-left">Semantik Vektör Arama</h3>

          <!-- Search form -->
          <div class="grid grid-cols-1 md:grid-cols-12 gap-3.5 mb-5">
            <div class="md:col-span-6 text-left">
              <label class="block text-[10px] font-bold text-zinc-500 uppercase mb-1.5">Koleksiyon</label>
              <select 
                v-model="searchCollection"
                class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-zinc-300 focus:outline-none focus:border-indigo-500"
              >
                <option value="business_rules">İş Kuralları</option>
                <option value="schema_ddl">Schema DDL'leri</option>
                <option value="sql_history">SQL Sorgu Geçmişi</option>
              </select>
            </div>

            <div class="md:col-span-6 text-left">
              <label class="block text-[10px] font-bold text-zinc-500 uppercase mb-1.5">Limit</label>
              <select 
                v-model="searchLimit"
                class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-zinc-300 focus:outline-none focus:border-indigo-500"
              >
                <option :value="1">1 En Yakın Sonuç</option>
                <option :value="3">3 En Yakın Sonuç</option>
                <option :value="5">5 En Yakın Sonuç</option>
              </select>
            </div>

            <div class="md:col-span-10 text-left">
              <input 
                v-model="searchQuery"
                @keyup.enter="executeSearch"
                placeholder="Aramak istediğiniz semantik ifade..."
                class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-4 text-xs text-white focus:outline-none focus:border-indigo-500 placeholder-zinc-600"
              />
            </div>

            <div class="md:col-span-2">
              <button 
                @click="executeSearch"
                :disabled="searching || !searchQuery"
                class="w-full h-10 bg-indigo-600 hover:bg-indigo-500 active:scale-95 disabled:bg-zinc-800 text-white font-semibold text-xs rounded-xl flex items-center justify-center transition-all shadow-md shadow-indigo-600/10 hover:shadow-indigo-600/20"
              >
                <svg v-if="searching" class="animate-spin h-3.5 w-3.5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span v-else>Ara</span>
              </button>
            </div>
          </div>

          <!-- Search Results list -->
          <div class="flex-1 flex flex-col justify-start">
            <div v-if="searchError" class="p-4 bg-red-500/5 border border-red-500/20 rounded-xl text-left text-xs text-red-300">
              {{ searchError }}
            </div>

            <div v-else-if="searchResults.length === 0" class="flex-1 flex flex-col items-center justify-center text-center p-8 space-y-3">
              <div class="w-12 h-12 rounded-xl bg-zinc-950 border border-zinc-850 flex items-center justify-center text-zinc-700">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>
              <p class="text-xs text-zinc-500 font-medium">Arama sonucunuz burada sergilenecektir.</p>
            </div>

            <!-- List -->
            <div v-else class="space-y-3 text-left">
              <div 
                v-for="(hit, idx) in searchResults" 
                :key="idx"
                class="p-4 rounded-xl border border-zinc-850 bg-zinc-950/40 space-y-2 relative"
              >
                <!-- Badge for ranking score -->
                <span class="absolute top-4 right-4 bg-indigo-500/10 border border-indigo-500/20 px-2 py-0.5 rounded text-[9px] font-bold text-indigo-400">#{{ idx + 1 }} Eşleşme</span>
                
                <div v-if="searchCollection === 'business_rules'" class="space-y-2">
                  <span class="text-[9px] font-bold text-indigo-400 block font-mono">RULE: {{ hit.rule_id }}</span>
                  <p class="text-xs text-zinc-200 font-semibold">"{{ hit.rule }}"</p>
                  <pre class="bg-zinc-950 p-2 border border-zinc-900 rounded-lg text-[10px] font-mono text-zinc-400 overflow-x-auto">{{ hit.sql_mapping }}</pre>
                </div>
                
                <div v-else-if="searchCollection === 'schema_ddl'" class="space-y-2">
                  <span class="text-[9px] font-bold text-indigo-400 block font-mono">TABLE DDL: {{ hit.table_name }}</span>
                  <pre class="bg-zinc-950 p-2.5 border border-zinc-900 rounded-lg text-[10px] font-mono text-emerald-400/90 overflow-x-auto">{{ hit.ddl }}</pre>
                </div>

                <div v-else class="space-y-2">
                  <span class="text-[9px] font-bold text-indigo-400 block font-mono">HISTORICAL PAIR</span>
                  <p class="text-xs text-zinc-200 font-semibold">"{{ hit.natural_query }}"</p>
                  <pre class="bg-zinc-950 p-2 border border-zinc-900 rounded-lg text-[10px] font-mono text-indigo-300 overflow-x-auto">{{ hit.sql }}</pre>
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>

      <!-- Add to Vector DB (Right) -->
      <div class="lg:col-span-5 space-y-6">
        <div class="bg-black/10 backdrop-blur-[1px] rounded-2xl border border-white/10 shadow-lg shadow-black/30 p-5 min-h-[460px] flex flex-col justify-start">
          
          <!-- Mode Tabs -->
          <div class="flex items-center gap-1.5 bg-zinc-950 border border-zinc-850 p-1 rounded-xl mb-5">
            <button 
              @click="indexMode = 'business_rule'"
              :class="[
                'flex-1 py-1.8 text-[10px] font-bold rounded-lg uppercase tracking-wider transition-all duration-200',
                indexMode === 'business_rule' 
                  ? 'bg-zinc-900 border border-zinc-800 text-white' 
                  : 'text-zinc-500 hover:text-zinc-300'
              ]"
            >
              İş Kuralı Ekle
            </button>
            <button 
              @click="indexMode = 'sql_history'"
              :class="[
                'flex-1 py-1.8 text-[10px] font-bold rounded-lg uppercase tracking-wider transition-all duration-200',
                indexMode === 'sql_history' 
                  ? 'bg-zinc-900 border border-zinc-800 text-white' 
                  : 'text-zinc-500 hover:text-zinc-300'
              ]"
            >
              SQL Çifti Ekle
            </button>
          </div>

          <!-- Feedback alerts -->
          <div v-if="indexSuccess" class="p-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs rounded-xl text-left mb-4 flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
            </svg>
            Kayıt başarıyla gömüldü ve indekslendi.
          </div>
          
          <div v-if="indexError" class="p-3 bg-red-500/5 border border-red-500/20 text-red-300 text-xs rounded-xl text-left mb-4">
            {{ indexError }}
          </div>

          <!-- Form 1: Business Rule Index -->
          <div v-if="indexMode === 'business_rule'" class="space-y-4 text-left flex-1 flex flex-col justify-between">
            <div class="space-y-4">
              <div class="space-y-1.5">
                <label class="block text-[10px] font-bold text-zinc-400 uppercase tracking-wider">Kural ID / Adı</label>
                <input 
                  v-model="ruleId"
                  placeholder="Örn: salary_bonus_ratio"
                  class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-white focus:outline-none focus:border-indigo-500 placeholder-zinc-700 font-mono"
                />
              </div>

              <div class="space-y-1.5">
                <label class="block text-[10px] font-bold text-zinc-400 uppercase tracking-wider">İş Kuralı Açıklaması (Doğal Dil)</label>
                <textarea 
                  v-model="ruleText"
                  placeholder="Örn: Çalışanların yıllık bonus oranı prim yüzdesi ile maaş çarpımından elde edilir."
                  class="w-full h-20 bg-zinc-950 border border-zinc-800 rounded-xl px-3 py-2.5 text-xs text-white focus:outline-none focus:border-indigo-500 placeholder-zinc-700 resize-none"
                ></textarea>
              </div>

              <div class="space-y-1.5">
                <label class="block text-[10px] font-bold text-zinc-400 uppercase tracking-wider">SQL Karşılığı / Şablonu</label>
                <textarea 
                  v-model="ruleSql"
                  placeholder="Örn: employees.salary * (employees.bonus_percentage / 100.0) AS annual_bonus"
                  class="w-full h-20 bg-zinc-950 border border-zinc-800 rounded-xl px-3 py-2.5 text-xs text-white focus:outline-none focus:border-indigo-500 placeholder-zinc-700 font-mono resize-none"
                ></textarea>
              </div>
            </div>

            <button 
              @click="handleIndex"
              :disabled="indexing || !ruleId || !ruleText || !ruleSql"
              class="w-full h-11 bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-800 text-white font-semibold text-xs rounded-xl shadow-lg shadow-indigo-600/10 hover:shadow-indigo-600/20 mt-4 flex items-center justify-center gap-2"
            >
              <svg v-if="indexing" class="animate-spin h-3.5 w-3.5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              İndeksle ve Vektörize Et
            </button>
          </div>

          <!-- Form 2: SQL History Index -->
          <div v-else class="space-y-4 text-left flex-1 flex flex-col justify-between">
            <div class="space-y-4">
              <div class="space-y-1.5">
                <label class="block text-[10px] font-bold text-zinc-400 uppercase tracking-wider">Geçmiş ID</label>
                <input 
                  v-model="historyId"
                  placeholder="Örn: get_high_earners_ankara"
                  class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-white focus:outline-none focus:border-indigo-500 placeholder-zinc-700 font-mono"
                />
              </div>

              <div class="space-y-1.5">
                <label class="block text-[10px] font-bold text-zinc-400 uppercase tracking-wider">Doğal Dil Sorgusu</label>
                <textarea 
                  v-model="historyNatural"
                  placeholder="Örn: Ankara'da çalışan ve maaşı 5000'den büyük olan personellerin adını getir."
                  class="w-full h-20 bg-zinc-950 border border-zinc-800 rounded-xl px-3 py-2.5 text-xs text-white focus:outline-none focus:border-indigo-500 placeholder-zinc-700 resize-none"
                ></textarea>
              </div>

              <div class="space-y-1.5">
                <label class="block text-[10px] font-bold text-zinc-400 uppercase tracking-wider">Target SQL Kod</label>
                <textarea 
                  v-model="historySql"
                  placeholder="Örn: SELECT first_name FROM employees WHERE city = 'Ankara' AND salary > 5000;"
                  class="w-full h-20 bg-zinc-950 border border-zinc-800 rounded-xl px-3 py-2.5 text-xs text-white focus:outline-none focus:border-indigo-500 placeholder-zinc-700 font-mono resize-none"
                ></textarea>
              </div>
            </div>

            <button 
              @click="handleIndex"
              :disabled="indexing || !historyId || !historyNatural || !historySql"
              class="w-full h-11 bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-800 text-white font-semibold text-xs rounded-xl shadow-lg shadow-indigo-600/10 hover:shadow-indigo-600/20 mt-4 flex items-center justify-center gap-2"
            >
              <svg v-if="indexing" class="animate-spin h-3.5 w-3.5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              İndeksle ve Vektörize Et
            </button>
          </div>

        </div>
      </div>

    </div>
  </div>
</template>
