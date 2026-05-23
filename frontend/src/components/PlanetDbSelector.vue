<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';

const props = defineProps<{
  modelValue: string;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void;
  (e: 'change', value: string): void;
}>();

const isOpen = ref(false);
const dropdownRef = ref<HTMLElement | null>(null);

const dbOptions = [
  { 
    id: 'postgres', 
    name: 'PostgreSQL', 
    bgImage: '/postgres_texture.png', 
    shadow: 'shadow-[0_0_15px_rgba(59,130,246,0.6)]', 
    ring: 'border-blue-400/30' 
  },
  { 
    id: 'oracle', 
    name: 'Oracle', 
    bgImage: '/oracle_texture.png', 
    shadow: 'shadow-[0_0_15px_rgba(249,115,22,0.6)]', 
    ring: 'border-orange-400/30' 
  },
  { 
    id: 'sqlite', 
    name: 'SQLite', 
    bgImage: '/sqlite_texture.png', 
    shadow: 'shadow-[0_0_15px_rgba(148,163,184,0.6)]', 
    ring: 'border-slate-400/30' 
  },
];

const selectedDb = ref(dbOptions.find(opt => opt.id === props.modelValue) || dbOptions[0]);

watch(() => props.modelValue, (newVal) => {
  const opt = dbOptions.find(o => o.id === newVal);
  if (opt) selectedDb.value = opt;
});

const selectDb = (opt: typeof dbOptions[0]) => {
  selectedDb.value = opt;
  emit('update:modelValue', opt.id);
  emit('change', opt.id);
  isOpen.value = false;
};

// Click outside to close
const handleClickOutside = (event: MouseEvent) => {
  if (dropdownRef.value && !dropdownRef.value.contains(event.target as Node)) {
    isOpen.value = false;
  }
};

onMounted(() => {
  document.addEventListener('mousedown', handleClickOutside);
});

onUnmounted(() => {
  document.removeEventListener('mousedown', handleClickOutside);
});
</script>

<template>
  <div class="relative" ref="dropdownRef">
    <!-- Trigger Button -->
    <button 
      @click="isOpen = !isOpen"
      class="group flex items-center gap-3 bg-transparent border-transparent px-2 py-1.5 rounded-xl transition-all duration-300 min-w-[140px] focus:outline-none"
    >
      <!-- Mini Planet (Active) - 20%+ Bigger -->
      <div class="relative w-8 h-8 flex items-center justify-center">
        <!-- Realistic 3D Textured Planet Sphere -->
        <div 
          class="w-6 h-6 rounded-full planet-texture shadow-inner transition-transform duration-300 group-hover:scale-125"
          :class="[selectedDb.shadow]"
          :style="{ backgroundImage: `url(${selectedDb.bgImage})` }"
        >
          <!-- Atmosphere / Shadow Overlay -->
          <div class="absolute inset-0 bg-[radial-gradient(ellipse_at_30%_30%,_rgba(255,255,255,0.2)_0%,_rgba(0,0,0,0.6)_80%)] rounded-full mix-blend-overlay"></div>
        </div>
      </div>
      
      <!-- DB Name -->
      <span class="text-xs font-bold text-zinc-200 tracking-wide flex-1 text-left ml-1">{{ selectedDb.name }}</span>
      
      <!-- Chevron -->
      <svg 
        xmlns="http://www.w3.org/2000/svg" 
        :class="['h-3.5 w-3.5 text-zinc-400 transition-transform duration-300', isOpen ? 'rotate-180' : '']" 
        viewBox="0 0 20 20" 
        fill="currentColor"
      >
        <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd" />
      </svg>
    </button>

    <!-- Dropdown Menu -->
    <transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="transform scale-95 opacity-0 -translate-y-2"
      enter-to-class="transform scale-100 opacity-100 translate-y-0"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="transform scale-100 opacity-100 translate-y-0"
      leave-to-class="transform scale-95 opacity-0 -translate-y-2"
    >
      <div 
        v-if="isOpen" 
        class="absolute right-0 mt-3 w-56 bg-transparent z-50 overflow-visible flex flex-col gap-1"
      >
        <button
          v-for="opt in dbOptions"
          :key="opt.id"
          @click="selectDb(opt)"
          class="w-full px-3 py-2.5 flex items-center gap-3.5 bg-transparent border-transparent transition-colors group relative"
        >
          <!-- Selected Indicator -->
          <div 
            v-if="opt.id === selectedDb.id" 
            class="absolute left-0 top-0 bottom-0 w-0.5 bg-indigo-500"
          ></div>
          
          <!-- Menu Planet - 20%+ Bigger -->
          <div class="relative w-9 h-9 flex items-center justify-center">
            <div 
              class="w-7 h-7 rounded-full planet-texture transition-transform duration-300 group-hover:scale-125"
              :class="[opt.shadow]"
              :style="{ backgroundImage: `url(${opt.bgImage})` }"
            >
              <div class="absolute inset-0 bg-[radial-gradient(ellipse_at_30%_30%,_rgba(255,255,255,0.2)_0%,_rgba(0,0,0,0.6)_80%)] rounded-full mix-blend-overlay"></div>
            </div>
          </div>
          
          <!-- Name -->
          <span 
            :class="[
              'text-xs font-semibold transition-colors',
              opt.id === selectedDb.id ? 'text-white' : 'text-zinc-400 group-hover:text-zinc-200'
            ]"
          >
            {{ opt.name }}
          </span>
          
          <!-- Checkmark for selected -->
          <svg 
            v-if="opt.id === selectedDb.id" 
            xmlns="http://www.w3.org/2000/svg" 
            class="h-4 w-4 ml-auto text-indigo-400" 
            viewBox="0 0 20 20" 
            fill="currentColor"
          >
            <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
          </svg>
        </button>
      </div>
    </transition>
  </div>
</template>

<style scoped>
/* 3D Realistic Texture Mapping & Spinning Animation */
.planet-texture {
  background-size: 200% 100%;
  background-position: center;
  background-repeat: repeat-x;
  /* Soft lighting shadow map from top-left, darkness on bottom right */
  box-shadow: inset -6px -6px 12px rgba(0,0,0,0.85), inset 2px 2px 8px rgba(255,255,255,0.3);
  animation: spinPlanet 15s linear infinite;
  transform: translateZ(0); /* Hardware acceleration */
}

@keyframes spinPlanet {
  0% { background-position: 0% 50%; }
  100% { background-position: -200% 50%; }
}
</style>
