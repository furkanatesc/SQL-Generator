<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue';
import { apiService } from '../services/api';

const props = defineProps<{
  activeTab: string;
}>();

// General & LLM Configs
const backendUrl = ref('');
const localAuthKey = ref('');
const nvidiaApiKey = ref('');

// Database Configs
const targetDbType = ref('sqlite');
const targetSqlitePath = ref('');
const targetPgHost = ref('localhost');
const targetPgPort = ref('5432');
const targetPgUser = ref('postgres');
const targetPgPassword = ref('');
const targetPgDb = ref('postgres');
const targetOracleHost = ref('localhost');
const targetOraclePort = ref('1521');
const targetOracleUser = ref('system');
const targetOraclePassword = ref('');
const targetOracleService = ref('ORCL');

// Schema Filters Configs
const rawSchema = ref<any>(null);
const hiddenTables = ref<Set<string>>(new Set());
const hiddenColumns = ref<Record<string, Set<string>>>({});
const selectedTable = ref<string | null>(null);
const searchQuery = ref('');

const loading = ref(false);
const saving = ref(false);
const saveSuccess = ref(false);
const saveError = ref('');

const loadSettings = async () => {
  loading.value = true;
  saveError.value = '';
  try {
    // 1. Local Browser Storage settings
    backendUrl.value = localStorage.getItem('sqlgen_backend_url') || 'http://127.0.0.1:8000';
    localAuthKey.value = localStorage.getItem('sqlgen_api_key') || 'sqlgen_secret_dev_key';

    // 2. Load configurations from FastAPI Backend SQLite store
    // Health check to ensure API is reachable before fetching configs
    await apiService.health();

    const nvidiaRes = await apiService.getConfig('nvidia_api_key');
    nvidiaApiKey.value = nvidiaRes.value || '';

    const dbTypeRes = await apiService.getConfig('target_db_type');
    targetDbType.value = dbTypeRes.value || 'sqlite';

    const sqlitePathRes = await apiService.getConfig('target_sqlite_path');
    targetSqlitePath.value = sqlitePathRes.value || '';

    const pgHostRes = await apiService.getConfig('target_pg_host');
    targetPgHost.value = pgHostRes.value || 'localhost';

    const pgPortRes = await apiService.getConfig('target_pg_port');
    targetPgPort.value = pgPortRes.value || '5432';

    const pgUserRes = await apiService.getConfig('target_pg_user');
    targetPgUser.value = pgUserRes.value || 'postgres';

    const pgPasswordRes = await apiService.getConfig('target_pg_password');
    targetPgPassword.value = pgPasswordRes.value || '';

    const pgDbRes = await apiService.getConfig('target_pg_db');
    targetPgDb.value = pgDbRes.value || 'postgres';

    const oracleHostRes = await apiService.getConfig('target_oracle_host');
    targetOracleHost.value = oracleHostRes.value || 'localhost';

    const oraclePortRes = await apiService.getConfig('target_oracle_port');
    targetOraclePort.value = oraclePortRes.value || '1521';

    const oracleUserRes = await apiService.getConfig('target_oracle_user');
    targetOracleUser.value = oracleUserRes.value || 'system';

    const oraclePasswordRes = await apiService.getConfig('target_oracle_password');
    targetOraclePassword.value = oraclePasswordRes.value || '';

    const oracleServiceRes = await apiService.getConfig('target_oracle_service');
    targetOracleService.value = oracleServiceRes.value || 'ORCL';

  } catch (e: any) {
    saveError.value = 'Ayarlar yüklenemedi. Backend sunucusunun çalıştığını ve API Keyinizin doğru olduğunu doğrulayın.';
  } finally {
    loading.value = false;
  }
};

const loadFilters = async () => {
  try {
    const filters = await apiService.getSchemaFilters();
    hiddenTables.value = new Set(filters.hidden_tables || []);
    
    const hCols: Record<string, Set<string>> = {};
    for (const [tbl, cols] of Object.entries(filters.hidden_columns || {})) {
      hCols[tbl] = new Set(cols as string[]);
    }
    hiddenColumns.value = hCols;

    const schemaRes = await apiService.getRawSchema();
    rawSchema.value = schemaRes.schema;
  } catch(e) {
    console.error("Filter loading error", e);
  }
};

const saveSettings = async () => {
  saving.value = true;
  saveSuccess.value = false;
  saveError.value = '';

  try {
    // 1. Save local client configs
    localStorage.setItem('sqlgen_backend_url', backendUrl.value.trim());
    localStorage.setItem('sqlgen_api_key', localAuthKey.value.trim());

    // 2. Save backend SQLite configurations
    await apiService.setConfig('nvidia_api_key', nvidiaApiKey.value.trim());
    await apiService.setConfig('target_db_type', targetDbType.value);
    await apiService.setConfig('target_sqlite_path', targetSqlitePath.value.trim());
    
    await apiService.setConfig('target_pg_host', targetPgHost.value.trim());
    await apiService.setConfig('target_pg_port', targetPgPort.value.trim());
    await apiService.setConfig('target_pg_user', targetPgUser.value.trim());
    await apiService.setConfig('target_pg_password', targetPgPassword.value);
    await apiService.setConfig('target_pg_db', targetPgDb.value.trim());

    await apiService.setConfig('target_oracle_host', targetOracleHost.value.trim());
    await apiService.setConfig('target_oracle_port', targetOraclePort.value.trim());
    await apiService.setConfig('target_oracle_user', targetOracleUser.value.trim());
    await apiService.setConfig('target_oracle_password', targetOraclePassword.value);
    await apiService.setConfig('target_oracle_service', targetOracleService.value.trim());

    if (localAuthKey.value.trim() !== 'sqlgen_secret_dev_key') {
      await apiService.setConfig('api_key', localAuthKey.value.trim());
    }

    // 3. Save Schema Filters
    const hColsPlain: Record<string, string[]> = {};
    for (const [tbl, colSet] of Object.entries(hiddenColumns.value)) {
      if (colSet.size > 0) {
        hColsPlain[tbl] = Array.from(colSet);
      }
    }
    await apiService.saveSchemaFilters(Array.from(hiddenTables.value), hColsPlain);

    saveSuccess.value = true;
    setTimeout(() => {
      saveSuccess.value = false;
    }, 3000);
  } catch (e: any) {
    saveError.value = e.message || 'Ayarlar kaydedilirken bir hata oluştu.';
  } finally {
    saving.value = false;
  }
};

onMounted(() => {
  loadSettings();
  if (props.activeTab === 'filters') {
    loadFilters();
  }
});

watch(() => props.activeTab, (newTab) => {
  if (newTab === 'filters' && !rawSchema.value) {
    loadFilters();
  }
});

// Computed properties for filters
const allTables = computed(() => {
  if (!rawSchema.value || !rawSchema.value.tables) return [];
  return Object.keys(rawSchema.value.tables).sort();
});

const filteredTables = computed(() => {
  if (!searchQuery.value) return allTables.value;
  return allTables.value.filter(t => t.toLowerCase().includes(searchQuery.value.toLowerCase()));
});

const selectedTableData = computed(() => {
  if (!selectedTable.value || !rawSchema.value) return null;
  return rawSchema.value.tables[selectedTable.value];
});

const selectedTableSequences = computed(() => {
  if (!rawSchema.value || !rawSchema.value.sequences || !selectedTable.value) return [];
  const seqs = rawSchema.value.sequences as any[];
  // If the sequence name contains the table name, it's likely related. Or we show all schema sequences if it's Oracle
  return seqs;
});

// Toggle functions
const toggleTableVisibility = (table: string) => {
  if (hiddenTables.value.has(table)) {
    hiddenTables.value.delete(table);
  } else {
    hiddenTables.value.add(table);
  }
};

const toggleColumnVisibility = (table: string, column: string) => {
  if (!hiddenColumns.value[table]) {
    hiddenColumns.value[table] = new Set();
  }
  if (hiddenColumns.value[table].has(column)) {
    hiddenColumns.value[table].delete(column);
  } else {
    hiddenColumns.value[table].add(column);
  }
};
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="text-left">
      <h2 class="text-2xl font-bold text-white tracking-tight">Sistem Ayarları</h2>
      <p class="text-zinc-400 text-sm">Sunucu bağlantılarını yapılandırın ve şema verilerini yönetin.</p>
    </div>

    <!-- Feedback alerts -->
    <div v-if="saveSuccess" class="p-4 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs rounded-xl text-left flex items-center gap-2">
      <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" /></svg>
      Tüm parametreler başarıyla kaydedildi.
    </div>
    
    <div v-if="saveError" class="p-4 bg-red-500/5 border border-red-500/20 text-red-300 text-xs rounded-xl text-left">
      {{ saveError }}
    </div>

    <!-- TABS DELETED: MOVED TO SIDEBAR -->

    <!-- Main Settings Container -->
    <div class="text-left min-h-[400px] relative">
      
      <!-- Loading State Overlay -->
      <div v-if="loading" class="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black/50 backdrop-blur-sm rounded-2xl">
        <svg class="animate-spin h-8 w-8 text-indigo-500 mb-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span class="text-xs font-medium text-zinc-400">Ayarlar Yükleniyor...</span>
      </div>

      <!-- TAB 1: GENERAL -->
      <div v-if="activeTab === 'general'" class="bg-black/10 backdrop-blur-[1px] rounded-2xl border border-white/10 shadow-lg p-5 space-y-4 max-w-2xl">
        <h3 class="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-2">Sunucu & Yapay Zeka Ayarları</h3>
        
        <!-- Backend URL -->
        <div class="space-y-1.5">
          <label class="block text-[10px] font-bold text-zinc-500 uppercase tracking-wider">FastAPI Backend Sunucu URL</label>
          <input v-model="backendUrl" placeholder="http://127.0.0.1:8000" class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-white focus:outline-none focus:border-indigo-500 font-mono" />
        </div>

        <!-- Dev Auth Key -->
        <div class="space-y-1.5">
          <label class="block text-[10px] font-bold text-zinc-500 uppercase tracking-wider">Lokal Sunucu Yetkilendirme Anahtarı (X-API-Key)</label>
          <input v-model="localAuthKey" type="password" placeholder="sqlgen_secret_dev_key" class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-white focus:outline-none focus:border-indigo-500 font-mono" />
        </div>

        <!-- NVIDIA NIM Key -->
        <div class="space-y-1.5">
          <label class="block text-[10px] font-bold text-zinc-500 uppercase tracking-wider">NVIDIA NIM API Anahtarı (NVIDIA_API_KEY)</label>
          <input v-model="nvidiaApiKey" type="password" placeholder="nvapi-..." class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-indigo-200 focus:outline-none focus:border-indigo-500 font-mono" />
        </div>
      </div>

      <!-- TAB 2: DATABASE -->
      <div v-if="activeTab === 'database'" class="bg-black/10 backdrop-blur-[1px] rounded-2xl border border-white/10 shadow-lg p-5 space-y-4 max-w-2xl">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-xs font-bold text-zinc-400 uppercase tracking-wider">Hedef Veritabanı Yapılandırması</h3>
          
          <div class="flex items-center gap-1 bg-zinc-950 p-0.5 rounded-lg border border-zinc-855">
            <button @click="targetDbType = 'sqlite'" :class="['px-2.5 py-1 text-[9px] font-bold rounded uppercase transition-colors', targetDbType === 'sqlite' ? 'bg-indigo-600 text-white' : 'text-zinc-500']">SQLite</button>
            <button @click="targetDbType = 'postgres'" :class="['px-2.5 py-1 text-[9px] font-bold rounded uppercase transition-colors', targetDbType === 'postgres' ? 'bg-indigo-600 text-white' : 'text-zinc-500']">Postgres</button>
            <button @click="targetDbType = 'oracle'" :class="['px-2.5 py-1 text-[9px] font-bold rounded uppercase transition-colors', targetDbType === 'oracle' ? 'bg-orange-600 text-white' : 'text-zinc-500']">Oracle</button>
          </div>
        </div>

        <!-- Option A: SQLite -->
        <div v-if="targetDbType === 'sqlite'" class="space-y-4 animate-scale-up">
          <div class="space-y-1.5">
            <label class="block text-[10px] font-bold text-zinc-500 uppercase tracking-wider">Lokal Hedef SQLite Yolu</label>
            <input v-model="targetSqlitePath" class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-white focus:outline-none focus:border-indigo-500 font-mono" />
          </div>
        </div>

        <!-- Option B: Postgres -->
        <div v-else-if="targetDbType === 'postgres'" class="space-y-3.5 animate-scale-up">
          <div class="grid grid-cols-3 gap-3">
            <div class="col-span-2 space-y-1.5"><label class="block text-[10px] font-bold text-zinc-500">Host</label><input v-model="targetPgHost" class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-white font-mono" /></div>
            <div class="space-y-1.5"><label class="block text-[10px] font-bold text-zinc-500">Port</label><input v-model="targetPgPort" class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-white font-mono" /></div>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div class="space-y-1.5"><label class="block text-[10px] font-bold text-zinc-500">Kullanıcı</label><input v-model="targetPgUser" class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-white font-mono" /></div>
            <div class="space-y-1.5"><label class="block text-[10px] font-bold text-zinc-500">Şifre</label><input v-model="targetPgPassword" type="password" class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-white font-mono" /></div>
          </div>
          <div class="space-y-1.5"><label class="block text-[10px] font-bold text-zinc-500">Veritabanı İsmi</label><input v-model="targetPgDb" class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-white font-mono" /></div>
        </div>

        <!-- Option C: Oracle -->
        <div v-if="targetDbType === 'oracle'" class="space-y-3.5 animate-scale-up">
          <div class="grid grid-cols-3 gap-3">
            <div class="col-span-2 space-y-1.5"><label class="block text-[10px] font-bold text-zinc-500">Host</label><input v-model="targetOracleHost" class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-white font-mono" /></div>
            <div class="space-y-1.5"><label class="block text-[10px] font-bold text-zinc-500">Port</label><input v-model="targetOraclePort" class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-white font-mono" /></div>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div class="space-y-1.5"><label class="block text-[10px] font-bold text-zinc-500">Kullanıcı</label><input v-model="targetOracleUser" class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-white font-mono" /></div>
            <div class="space-y-1.5"><label class="block text-[10px] font-bold text-zinc-500">Şifre</label><input v-model="targetOraclePassword" type="password" class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-white font-mono" /></div>
          </div>
          <div class="space-y-1.5"><label class="block text-[10px] font-bold text-zinc-500">Service Name</label><input v-model="targetOracleService" class="w-full h-10 bg-zinc-950 border border-zinc-800 rounded-xl px-3 text-xs text-white font-mono" /></div>
        </div>
      </div>

      <!-- TAB 3: FILTERS -->
      <div v-if="activeTab === 'filters'" class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        <!-- Tablolar Listesi -->
        <div class="col-span-1 bg-black/10 backdrop-blur-[1px] rounded-2xl border border-white/10 shadow-lg p-5 flex flex-col h-[600px]">
          <h3 class="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-3 flex items-center justify-between">
            Tüm Tablolar
            <span class="text-[9px] bg-indigo-500/20 text-indigo-300 px-2 py-0.5 rounded">{{ allTables.length }}</span>
          </h3>
          <input v-model="searchQuery" placeholder="Tablo Ara..." class="mb-3 w-full h-9 bg-zinc-950 border border-zinc-800 rounded-lg px-3 text-xs text-white focus:outline-none focus:border-indigo-500" />
          
          <div class="flex-1 overflow-y-auto space-y-1 pr-2 custom-scrollbar">
            <div 
              v-for="table in filteredTables" 
              :key="table"
              :class="['flex items-center justify-between p-2 rounded-lg cursor-pointer transition-colors border', selectedTable === table ? 'bg-white/10 border-white/20' : 'bg-transparent border-transparent hover:bg-white/5']"
              @click="selectedTable = table"
            >
              <span :class="['text-xs font-mono truncate', hiddenTables.has(table) ? 'text-zinc-600 line-through' : 'text-zinc-300']">{{ table }}</span>
              <button 
                @click.stop="toggleTableVisibility(table)"
                :class="['text-[9px] px-2 py-1 rounded font-bold uppercase transition-colors', hiddenTables.has(table) ? 'bg-red-500/20 text-red-400 hover:bg-red-500/40' : 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/40']"
              >
                {{ hiddenTables.has(table) ? 'Gizli' : 'Aktif' }}
              </button>
            </div>
            <div v-if="filteredTables.length === 0" class="text-zinc-500 text-xs italic p-2">Tablo bulunamadı veya şema yüklenmedi.</div>
          </div>
        </div>

        <!-- Seçili Tablo Detayları (Kolonlar, Sequence, Constraint) -->
        <div class="col-span-2 bg-black/10 backdrop-blur-[1px] rounded-2xl border border-white/10 shadow-lg p-5 flex flex-col h-[600px]">
          <div v-if="selectedTable" class="flex flex-col h-full">
            <div class="flex items-center justify-between mb-4 border-b border-white/10 pb-4">
              <div>
                <h3 class="text-lg font-bold text-white font-mono flex items-center gap-2">
                  {{ selectedTable }}
                  <span v-if="hiddenTables.has(selectedTable)" class="bg-red-500/20 text-red-400 text-[10px] px-2 py-0.5 rounded uppercase">TAMAMI GİZLİ</span>
                </h3>
                <p class="text-zinc-500 text-xs">Kolonları gizleyebilir veya tablonun özelliklerini görebilirsiniz.</p>
              </div>
            </div>

            <div class="flex-1 overflow-y-auto space-y-6 pr-2 custom-scrollbar">
              <!-- Kolonlar -->
              <div>
                <h4 class="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-2">Kolonlar ({{ selectedTableData?.columns?.length || 0 }})</h4>
                <div class="grid grid-cols-2 gap-2">
                  <div 
                    v-for="col in selectedTableData?.columns" 
                    :key="col.name"
                    class="flex items-center justify-between p-2 bg-black/20 border border-white/5 rounded-lg"
                  >
                    <div class="flex items-center gap-2 overflow-hidden">
                      <span v-if="col.primary_key" class="text-amber-400" title="Primary Key">🔑</span>
                      <span :class="['text-xs font-mono truncate', hiddenColumns[selectedTable]?.has(col.name) ? 'text-zinc-600 line-through' : 'text-zinc-300']">
                        {{ col.name }} <span class="text-zinc-600 text-[9px]">({{ col.type }})</span>
                      </span>
                    </div>
                    <button 
                      @click="toggleColumnVisibility(selectedTable, col.name)"
                      :disabled="hiddenTables.has(selectedTable)"
                      :class="['text-[9px] px-2 py-1 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed', hiddenColumns[selectedTable]?.has(col.name) ? 'bg-red-500/20 text-red-400' : 'bg-white/10 text-zinc-400 hover:text-white']"
                    >
                      <span v-if="hiddenColumns[selectedTable]?.has(col.name)">Gizli</span>
                      <span v-else>👁️</span>
                    </button>
                  </div>
                </div>
              </div>

              <!-- Constraints -->
              <div v-if="selectedTableData?.constraints && selectedTableData.constraints.length > 0">
                <h4 class="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-2">Constraints (Kısıtlamalar) - Salt Okunur</h4>
                <div class="space-y-2">
                  <div v-for="cons in selectedTableData.constraints" :key="cons.name" class="p-2 bg-black/30 border border-amber-500/20 rounded-lg text-xs font-mono text-zinc-300">
                    <div class="flex justify-between text-amber-400 mb-1">
                      <span>{{ cons.name }}</span>
                      <span>Type: {{ cons.type }}</span>
                    </div>
                    <div v-if="cons.condition" class="text-zinc-500 truncate">{{ cons.condition }}</div>
                  </div>
                </div>
              </div>

              <!-- Sequences (Global list matched loosely) -->
              <div v-if="selectedTableSequences.length > 0">
                <h4 class="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-2">Global Sequences - Salt Okunur</h4>
                <div class="grid grid-cols-2 gap-2">
                  <div v-for="seq in selectedTableSequences" :key="seq.name" class="p-2 bg-black/30 border border-blue-500/20 rounded-lg text-xs font-mono text-zinc-300">
                    <div class="text-blue-400 mb-1 truncate" :title="seq.name">{{ seq.name }}</div>
                    <div class="flex gap-3 text-zinc-500 text-[10px]">
                      <span>Min: {{ seq.min }}</span>
                      <span>Max: {{ seq.max }}</span>
                      <span>Inc: {{ seq.inc }}</span>
                    </div>
                  </div>
                </div>
              </div>

            </div>
          </div>
          <div v-else class="flex-1 flex items-center justify-center text-zinc-500 text-sm">
            Soldan detaylarını görmek istediğiniz bir tablo seçin.
          </div>
        </div>

      </div>
    </div>

    <!-- Bottom Save bar -->
    <div class="flex justify-end pt-4 border-t border-zinc-900 mt-6">
      <button 
        @click="saveSettings"
        :disabled="loading || saving"
        :class="['h-9 px-4 bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 hover:border-zinc-700 text-zinc-300 hover:text-white font-semibold text-xs rounded-xl flex items-center gap-2 transition-all btn-laser', (loading || saving) ? 'is-loading opacity-80 cursor-not-allowed' : '']"
      >
        <template v-if="saving">
          <svg class="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          Kaydediliyor...
        </template>
        <template v-else>
          Ayarları Kaydet
        </template>
      </button>
    </div>
  </div>
</template>

<style scoped>
.animate-scale-up {
  animation: scaleUp 0.22s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

@keyframes scaleUp {
  from { transform: scale(0.97); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}

.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}
</style>
