<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import Sidebar from './components/Sidebar.vue';
import ChatView from './components/ChatView.vue';
import History from './components/History.vue';
import SchemaManager from './components/SchemaManager.vue';
import RAGConfig from './components/RAGConfig.vue';
import Settings from './components/Settings.vue';
import Lenis from 'lenis';
import SpaceSpiderweb from './components/SpaceSpiderweb.vue';
import { computed } from 'vue';

const savedTabRaw = localStorage.getItem('sqlgen_active_tab');
const savedTab = savedTabRaw === 'settings' ? 'settings_general' : savedTabRaw;
const activeTab = ref(savedTab || 'dashboard');

watch(activeTab, (newTab) => {
  localStorage.setItem('sqlgen_active_tab', newTab);
});

const mainRef = ref<HTMLElement | null>(null);
let lenisInstance: Lenis | null = null;

const currentComponent = computed(() => {
  if (activeTab.value === 'dashboard') return ChatView;
  if (activeTab.value === 'history') return History;
  if (activeTab.value === 'schema') return SchemaManager;
  if (activeTab.value === 'rag') return RAGConfig;
  if (activeTab.value.startsWith('settings_')) return Settings;
  return ChatView;
});

// Scroll Navigation Logic
const TABS = ['dashboard', 'history', 'schema', 'rag', 'settings_general', 'settings_database', 'settings_filters'];
const resistanceY = ref(0);
const RESISTANCE_THRESHOLD = 0; // 0 direnç, anında geçiş
let isSwitching = false;

const triggerTabSwitch = (dir: 'next' | 'prev') => {
  const currentIndex = TABS.indexOf(activeTab.value);
  let newIndex = currentIndex;
  
  if (dir === 'next' && currentIndex < TABS.length - 1) {
    newIndex = currentIndex + 1;
  } else if (dir === 'prev' && currentIndex > 0) {
    newIndex = currentIndex - 1;
  }

  if (newIndex !== currentIndex) {
    isSwitching = true;
    activeTab.value = TABS[newIndex];
    resistanceY.value = 0;
    
    setTimeout(() => {
      if (lenisInstance) {
        lenisInstance.scrollTo(0, { immediate: true });
      } else if (mainRef.value) {
        mainRef.value.scrollTop = 0;
      }
    }, 50); // Small delay to let DOM settle after tab switch

    setTimeout(() => {
      isSwitching = false;
    }, 800); // Cooldown to prevent double-skipping
  } else {
    // At the very beginning or very end bounds
    resistanceY.value = 0;
  }
};

onMounted(() => {
  if (mainRef.value) {
    // Initialize Lenis smooth scroll on the main scrollable element
    lenisInstance = new Lenis({
      wrapper: mainRef.value,
      content: mainRef.value.firstElementChild as HTMLElement,
      duration: 1.2,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      orientation: 'vertical',
      gestureOrientation: 'vertical',
      smoothWheel: true,
    });

    const raf = (time: number) => {
      lenisInstance?.raf(time);
      requestAnimationFrame(raf);
    };

    requestAnimationFrame(raf);

    // Scroll Resistance & Tab Switching Logic
    mainRef.value.addEventListener('wheel', (e: WheelEvent) => {
      if (isSwitching) return;
      const el = mainRef.value;
      if (!el) return;

      const atTop = el.scrollTop <= 0;
      // Math.ceil deals with sub-pixel scroll values
      const atBottom = Math.ceil(el.scrollTop + el.clientHeight) >= el.scrollHeight - 1;

      if (atTop && e.deltaY < 0) {
        resistanceY.value += Math.abs(e.deltaY) * 0.6; // Increased multiplier
        if (resistanceY.value > RESISTANCE_THRESHOLD) {
          triggerTabSwitch('prev');
        }
      } else if (atBottom && e.deltaY > 0) {
        resistanceY.value -= Math.abs(e.deltaY) * 0.6; // Increased multiplier
        if (Math.abs(resistanceY.value) > RESISTANCE_THRESHOLD) {
          triggerTabSwitch('next');
        }
      } else {
        // Normal scroll inside content
      }
    }, { passive: true });
    
    // Easing loop for the resistance spring-back effect
    const springBack = () => {
      if (resistanceY.value !== 0 && !isSwitching) {
         resistanceY.value *= 0.85; // Spring back velocity
         if (Math.abs(resistanceY.value) < 1) resistanceY.value = 0;
      }
      requestAnimationFrame(springBack);
    };
    requestAnimationFrame(springBack);
  }
});

onUnmounted(() => {
  if (lenisInstance) {
    lenisInstance.destroy();
    lenisInstance = null;
  }
});
</script>

<template>
  <div class="min-h-screen bg-gradient-to-br from-zinc-950 via-zinc-900 to-black flex font-sans antialiased text-zinc-200 overflow-hidden relative">
    <!-- Sidebar Navigation -->
    <Sidebar v-model:activeTab="activeTab" />

    <!-- Space & Spiderweb Global Animated Backdrop (Fixed globally behind UI layout for 100% unified glassmorphism card blur) -->
    <div 
      class="fixed inset-0 pointer-events-none transition-all duration-500 z-0"
      style="width: 100vw; height: 100vh;"
    >
      <SpaceSpiderweb :active-tab="activeTab" />
    </div>

    <!-- Main Content Canvas with Lenis custom scroll wrapper (Fully transparent to let fixed background shine through uniformly) -->
    <main 
      id="main-scroll-container"
      ref="mainRef" 
      class="flex-1 h-screen overflow-y-auto bg-transparent relative z-10 scrollbar-none"
    >
      <!-- Scrollable content wrapper (Slides OVER the Curtain Footer) -->
      <div 
        id="main-content-wrapper" 
        :style="{ transform: `translateY(${resistanceY}px)` }"
        class="relative z-10 bg-transparent pb-52 min-h-screen border-b border-zinc-900/60 shadow-2xl overflow-hidden transition-transform duration-75 ease-out"
      >
        
        <div class="max-w-6xl mx-auto space-y-6 relative z-10 p-8">
          
          <!-- Render Active view component -->
          <Transition name="fade" mode="out-in">
            <KeepAlive>
              <component 
                :is="currentComponent" 
                :active-tab="activeTab.startsWith('settings_') ? activeTab.replace('settings_', '') : undefined" 
              />
            </KeepAlive>
          </Transition>

        </div>
      </div>
    </main>
  </div>
</template>

<style>
/* CSS transition transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s cubic-bezier(0.4, 0, 0.2, 1);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Custom scrollbars inside dark mode */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: rgba(9, 9, 11, 0.4);
}

::-webkit-scrollbar-thumb {
  background: rgba(63, 63, 70, 0.4);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: rgba(82, 82, 91, 0.6);
}

/* Hide scrollbar utility for main body during Lenis scroll */
.scrollbar-none::-webkit-scrollbar {
  display: none;
}
.scrollbar-none {
  -ms-overflow-style: none;  /* IE and Edge */
  scrollbar-width: none;  /* Firefox */
}
</style>
