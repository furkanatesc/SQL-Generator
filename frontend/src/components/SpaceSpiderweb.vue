<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import * as THREE from 'three';
import gsap from 'gsap';
import { apiService } from '../services/api';
import { buildSynapseGraph, type SynapseGraph } from '../utils/synapseNetwork';
import { computeSynapseLayout } from '../utils/synapseLayout';
import { PulseScheduler } from '../utils/synapsePulse';

const props = defineProps<{
  activeTab: string;
}>();

const containerRef = ref<HTMLElement | null>(null);

let animationFrameId: number;
let renderer: THREE.WebGLRenderer;
let camera: THREE.PerspectiveCamera;
let synapseNodesGeometry: THREE.BufferGeometry | null = null;
let synapseNodesMaterial: THREE.ShaderMaterial | null = null;
let synapseEdgesGeometry: THREE.BufferGeometry | null = null;
let synapseEdgesMaterial: THREE.ShaderMaterial | null = null;
let pulseScheduler: PulseScheduler | null = null;
let synapsePulseArrays: { start: Float32Array; duration: Float32Array; dir: Float32Array } | null = null;
let sceneClock: THREE.Clock | null = null;
let isDisposed = false;
let starsGeometry: THREE.BufferGeometry;
let starsMaterial: THREE.ShaderMaterial;
let virtualScroll = 0; // The actual smooth scroll value
let targetVirtualScroll = 0; // The target scroll value set by the wheel

const blackHoleState = { strength: 0 };

// Sinaps katmanı görsel ayarları — göz kararı ince ayar hep buradan yapılır
const SYNAPSE_STYLE = {
  maxNodes: 150,
  layoutRadius: 260,
  nodeBaseSize: 6.0,
  nodeSizePerDegree: 1.1,
  nodeMaxSize: 15.0,
  hubRatio: 0.1,                          // en bağlantılı %10 amber olur
  nodeColor: [0.85, 0.86, 0.92] as const, // zinc-beyaz
  hubColor: [0.98, 0.75, 0.35] as const,  // amber
  edgeOpacity: 0.2,
  pulseSeconds: 0.9,
  pulseGlowBoost: 1.1,
  pulseIntervalMinSec: 0,  // kesintisiz bayrak yarışı — biten darbenin yerine anında yenisi
  pulseIntervalMaxSec: 0,  // kesintisiz bayrak yarışı — biten darbenin yerine anında yenisi
  pulseMaxConcurrent: 1,   // ekranda her an tam 1 darbe
  depthStretch: 1.5,  // yerleşim z'sini sarmal koridora yayar (800 derinlik / ~520 küme)
} as const;

let isMouseListenerActive = false;

const onMouseMove = (e: MouseEvent) => {
  if (!camera) return;
  const mouseX = (e.clientX / window.innerWidth) * 2 - 1;
  const mouseY = -(e.clientY / window.innerHeight) * 2 + 1;
  
  gsap.to(camera.position, {
    x: mouseX * 40,
    y: mouseY * 40,
    duration: 2.0,
    ease: "power2.out"
  });
  
  gsap.to(camera.rotation, {
    x: mouseY * 0.08,
    y: -mouseX * 0.08,
    duration: 2.0,
    ease: "power2.out"
  });
};

const updateMouseListener = (tab: string) => {
  if (tab === 'schema') {
    if (isMouseListenerActive) {
      window.removeEventListener('mousemove', onMouseMove);
      isMouseListenerActive = false;
    }
  } else {
    if (!isMouseListenerActive) {
      window.addEventListener('mousemove', onMouseMove);
      isMouseListenerActive = true;
    }
  }
};

watch(() => props.activeTab, (newTab) => {
  updateMouseListener(newTab);
  if (newTab === 'schema') {
    gsap.to(blackHoleState, {
      strength: 1.0,
      duration: 3.2,
      ease: 'power2.inOut',
      overwrite: 'auto',
    });
  } else {
    gsap.to(blackHoleState, {
      strength: 0.0,
      duration: 2.8,
      ease: 'power2.inOut',
      overwrite: 'auto',
    });
  }
}, { immediate: true });

// Faz 2 kancası: sorgu pipeline'ı ilgili tablo adlarıyla çağıracak.
// Faz 1'de çağıran yok; bilinmeyen tablo adları PulseScheduler'da sessizce atlanır.
const fireSignal = (tableNames: string[]) => {
  if (!pulseScheduler || !sceneClock) return;
  pulseScheduler.fire(tableNames, sceneClock.getElapsedTime());
};
defineExpose({ fireSignal });

// Kara delik warp bloğu — tünel shader'ından devralınan sözleşme (bhCenter x=85)
const SYNAPSE_WARP_GLSL = `
  if (blackHoleStrength > 0.0) {
    vec2 bhCenter = vec2(85.0, 0.0);
    vec2 distVec = pos.xy - bhCenter;
    float r = length(distVec) + 0.1;
    float swirl = (4.5 / (r * 0.03 + 2.5)) * blackHoleStrength + blackHoleAngle;
    float cosA = cos(swirl);
    float sinA = sin(swirl);
    vec2 rotatedVec = mat2(cosA, -sinA, sinA, cosA) * distVec;
    float pull = mix(1.0, pow(clamp(r / 550.0, 0.0, 1.0), 1.8), blackHoleStrength * 0.95);
    pos.xy = bhCenter + rotatedVec * pull;
    pos.z -= mix(0.0, 750.0 / (r * 0.005 + 1.0), blackHoleStrength);
  }
`;

const SYNAPSE_NODE_VERT = `
  uniform float time;
  uniform float scrollZ;
  uniform float blackHoleStrength;
  uniform float blackHoleAngle;
  attribute float size;
  attribute vec3 color;
  varying vec3 vColor;
  varying float vDepth;
  void main() {
    vColor = color;
    vec3 pos = position;
    pos.z = mod(pos.z + scrollZ + 400.0, 800.0) - 400.0;
    ${SYNAPSE_WARP_GLSL}
    vDepth = pos.z;
    vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
    float breath = 1.0 + sin(time * 1.4 + position.x * 0.08) * 0.18;
    gl_PointSize = size * breath * (300.0 / -mvPosition.z);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const SYNAPSE_NODE_FRAG = `
  uniform sampler2D pointTexture;
  varying vec3 vColor;
  varying float vDepth;
  void main() {
    vec4 texColor = texture2D(pointTexture, gl_PointCoord);
    if (texColor.a < 0.01) discard;
    float depthFade = smoothstep(-400.0, 400.0, vDepth);
    gl_FragColor = vec4(vColor, depthFade) * texColor;
  }
`;

// Edge wrap per-EDGE yapılır (aMidZ): iki uç aynı offset'i alır, sınırda
// çizgi tüm tüneli kat eden "streak" artefaktı oluşmaz.
const SYNAPSE_EDGE_VERT = `
  uniform float time;
  uniform float scrollZ;
  uniform float blackHoleStrength;
  uniform float blackHoleAngle;
  attribute float aEndpoint;
  attribute float aMidZ;
  attribute float aPulseStart;
  attribute float aPulseDuration;
  attribute float aPulseDir;
  varying float vT;
  varying float vDepth;
  varying float vPulseStart;
  varying float vPulseDuration;
  varying float vPulseDir;
  void main() {
    vT = aEndpoint;
    vPulseStart = aPulseStart;
    vPulseDuration = aPulseDuration;
    vPulseDir = aPulseDir;
    vec3 pos = position;
    float midRaw = aMidZ + scrollZ;
    float offset = (mod(midRaw + 400.0, 800.0) - 400.0) - midRaw;
    pos.z = pos.z + scrollZ + offset;
    ${SYNAPSE_WARP_GLSL}
    vDepth = pos.z;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  }
`;

const SYNAPSE_EDGE_FRAG = `
  uniform float time;
  uniform float edgeOpacity;
  uniform float pulseGlowBoost;
  varying float vT;
  varying float vDepth;
  varying float vPulseStart;
  varying float vPulseDuration;
  varying float vPulseDir;
  void main() {
    vec3 base = vec3(0.31, 0.27, 0.90);   // indigo #4f46e5
    vec3 color = base;
    float alpha = edgeOpacity;
    if (vPulseStart >= 0.0 && vPulseDuration > 0.0) {
      float p = clamp((time - vPulseStart) / vPulseDuration, 0.0, 1.0);
      if (vPulseDir < 0.0) p = 1.0 - p;
      float d = vT - p;
      float glow = exp(-d * d * 35.0);
      color = mix(base, vec3(0.13, 0.83, 0.93), glow);   // cyan #22d3ee
      alpha += glow * pulseGlowBoost;
    }
    float depthFade = smoothstep(-400.0, 400.0, vDepth);
    gl_FragColor = vec4(color, alpha * depthFade);
  }
`;

onMounted(() => {
  if (!containerRef.value) return;

  // 1. Scene Setup
  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x000000, 0.0015);

  // 2. Camera Setup
  camera = new THREE.PerspectiveCamera(
    85,
    window.innerWidth / window.innerHeight,
    0.1,
    2000
  );
  camera.position.z = 200;

  // 3. Renderer Setup
  renderer = new THREE.WebGLRenderer({ 
    alpha: true, 
    antialias: true,
    powerPreference: 'high-performance'
  });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  containerRef.value.appendChild(renderer.domElement);

  // 4. RESTORED: The Stars (Particles)
  const generateStarTexture = () => {
    const canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = 64;
    const ctx = canvas.getContext('2d');
    if (ctx) {
      const gradient = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
      gradient.addColorStop(0, 'rgba(255, 255, 255, 1)');
      gradient.addColorStop(0.1, 'rgba(168, 85, 247, 0.8)'); // Purple
      gradient.addColorStop(0.4, 'rgba(68, 136, 255, 0.3)'); // Blue
      gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, 64, 64);
    }
    return new THREE.CanvasTexture(canvas);
  };

  const particleCount = 3500;
  starsGeometry = new THREE.BufferGeometry();
  const starPositions = new Float32Array(particleCount * 3);
  const starColors = new Float32Array(particleCount * 3);
  const starSizes = new Float32Array(particleCount);

  for (let i = 0; i < particleCount; i++) {
    const radius = 900 * Math.cbrt(Math.random());
    const theta = Math.random() * 2 * Math.PI;
    const phi = Math.acos(2 * Math.random() - 1);
    
    starPositions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
    starPositions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
    starPositions[i * 3 + 2] = radius * Math.cos(phi);

    // Mix colors randomly
    starColors[i*3] = 0.6 + Math.random() * 0.4;
    starColors[i*3+1] = 0.6 + Math.random() * 0.4;
    starColors[i*3+2] = 1.0;
    
    starSizes[i] = Math.random() * 2.5 + 1.0;
  }

  starsGeometry.setAttribute('position', new THREE.BufferAttribute(starPositions, 3));
  starsGeometry.setAttribute('color', new THREE.BufferAttribute(starColors, 3));
  starsGeometry.setAttribute('size', new THREE.BufferAttribute(starSizes, 1));

  starsMaterial = new THREE.ShaderMaterial({
    uniforms: {
      time: { value: 0 },
      pointTexture: { value: generateStarTexture() },
      scrollZ: { value: 0 },
      blackHoleStrength: { value: 0 },
      blackHoleAngle: { value: 0 }
    },
    vertexShader: `
      uniform float time;
      uniform float scrollZ;
      uniform float blackHoleStrength;
      uniform float blackHoleAngle;
      attribute float size;
      attribute vec3 color;
      varying vec3 vColor;
      void main() {
        vColor = color;
        vec3 pos = position;
        
        // Stars fly past the camera with scroll
        pos.z += scrollZ;
        pos.z = mod(pos.z + 500.0, 1000.0) - 500.0;
        
        // Apply Gravitational Black Hole warp if active
        if (blackHoleStrength > 0.0) {
          // Shift gravity center to the right (x=85.0) to match the D3 topological schema black hole container position on screen
          vec2 bhCenter = vec2(85.0, 0.0);
          vec2 distVec = pos.xy - bhCenter;
          float r = length(distVec) + 0.1;
          
          // 1. Vortex twist: rotate exponentially faster near the singularity + continuous slow flow (reduced transition snap)
          float swirl = (5.0 / (r * 0.03 + 2.5)) * blackHoleStrength + blackHoleAngle;
          float cosA = cos(swirl);
          float sinA = sin(swirl);
          vec2 rotatedVec = mat2(cosA, -sinA, sinA, cosA) * distVec;
          
          // 2. Gravitational spaghettification attraction: pull stars exponentially into the singularity center
          float pull = mix(1.0, pow(clamp(r / 900.0, 0.0, 1.0), 2.5), blackHoleStrength * 0.98);
          pos.xy = bhCenter + rotatedVec * pull;
          
          // 3. Singularity z-pull: pull deep into the abyss (negative z)
          pos.z -= mix(0.0, 800.0 / (r * 0.003 + 1.0), blackHoleStrength);
        }
        
        vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
        float pulse = 1.0 + sin(time * 2.0 + position.x * 0.05) * 0.3;
        gl_PointSize = size * pulse * (300.0 / -mvPosition.z);
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: `
      uniform sampler2D pointTexture;
      varying vec3 vColor;
      void main() {
        vec4 texColor = texture2D(pointTexture, gl_PointCoord);
        if (texColor.a < 0.01) discard;
        gl_FragColor = vec4(vColor, 1.0) * texColor;
      }
    `,
    blending: THREE.AdditiveBlending,
    depthTest: false,
    transparent: true,
  });

  const particleSystem = new THREE.Points(starsGeometry, starsMaterial);
  scene.add(particleSystem);


  // 5. Canlı Şema Sinapsı — gerçek şemadan beslenen sinaptik ağ katmanı
  const initSynapseLayer = (graph: SynapseGraph) => {
    const layout = computeSynapseLayout(graph, { radius: SYNAPSE_STYLE.layoutRadius });
    if (layout.nodes.length === 0) return;

    const prefersReducedMotion =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    pulseScheduler = new PulseScheduler(layout, {
      seed: 7,
      pulseDurationSec: SYNAPSE_STYLE.pulseSeconds,
      intervalMinSec: SYNAPSE_STYLE.pulseIntervalMinSec,
      intervalMaxSec: SYNAPSE_STYLE.pulseIntervalMaxSec,
      maxConcurrent: SYNAPSE_STYLE.pulseMaxConcurrent,
    });
    pulseScheduler.setEnabled(!prefersReducedMotion);

    // --- Node'lar (tek Points) ---
    const n = layout.nodes.length;
    const nodePositions = new Float32Array(n * 3);
    const nodeColors = new Float32Array(n * 3);
    const nodeSizes = new Float32Array(n);
    const sortedDegrees = layout.nodes.map((nd) => nd.degree).sort((a, b) => b - a);
    const hubThreshold = sortedDegrees[Math.max(0, Math.floor(n * SYNAPSE_STYLE.hubRatio) - 1)] ?? Infinity;
    layout.nodes.forEach((nd, i) => {
      nodePositions[i * 3] = nd.x;
      nodePositions[i * 3 + 1] = nd.y;
      // z derinlikte gerilir: küme (~520) sarmal koridorun (800) tamamına yayılır,
      // scroll sırasında ağın büyük bölümü aynı anda kameranın arkasına düşmez.
      nodePositions[i * 3 + 2] = nd.z * SYNAPSE_STYLE.depthStretch;
      const c = nd.degree >= hubThreshold && nd.degree > 0 ? SYNAPSE_STYLE.hubColor : SYNAPSE_STYLE.nodeColor;
      nodeColors[i * 3] = c[0];
      nodeColors[i * 3 + 1] = c[1];
      nodeColors[i * 3 + 2] = c[2];
      nodeSizes[i] = Math.min(
        SYNAPSE_STYLE.nodeMaxSize,
        SYNAPSE_STYLE.nodeBaseSize + nd.degree * SYNAPSE_STYLE.nodeSizePerDegree
      );
    });
    synapseNodesGeometry = new THREE.BufferGeometry();
    synapseNodesGeometry.setAttribute('position', new THREE.BufferAttribute(nodePositions, 3));
    synapseNodesGeometry.setAttribute('color', new THREE.BufferAttribute(nodeColors, 3));
    synapseNodesGeometry.setAttribute('size', new THREE.BufferAttribute(nodeSizes, 1));
    synapseNodesMaterial = new THREE.ShaderMaterial({
      uniforms: {
        time: { value: 0 },
        pointTexture: { value: generateStarTexture() },
        scrollZ: { value: 0 },
        blackHoleStrength: { value: 0 },
        blackHoleAngle: { value: 0 },
      },
      vertexShader: SYNAPSE_NODE_VERT,
      fragmentShader: SYNAPSE_NODE_FRAG,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      transparent: true,
    });
    scene.add(new THREE.Points(synapseNodesGeometry, synapseNodesMaterial));

    // --- Sinaps hatları (tek LineSegments) ---
    const m = layout.edges.length;
    const edgePositions = new Float32Array(m * 6);
    const endpoint = new Float32Array(m * 2);
    const midZ = new Float32Array(m * 2);
    const pulseStart = new Float32Array(m * 2).fill(-1);
    const pulseDuration = new Float32Array(m * 2);
    const pulseDir = new Float32Array(m * 2).fill(1);
    layout.edges.forEach((e, i) => {
      const a = layout.nodes[e.sourceIndex];
      const b = layout.nodes[e.targetIndex];
      // Node buffer'ıyla aynı derinlik gerilmesi; midZ de gerilmiş z'lerden
      // hesaplanır ki per-edge wrap tutarlı kalsın.
      const az = a.z * SYNAPSE_STYLE.depthStretch;
      const bz = b.z * SYNAPSE_STYLE.depthStretch;
      edgePositions[i * 6] = a.x; edgePositions[i * 6 + 1] = a.y; edgePositions[i * 6 + 2] = az;
      edgePositions[i * 6 + 3] = b.x; edgePositions[i * 6 + 4] = b.y; edgePositions[i * 6 + 5] = bz;
      endpoint[i * 2] = 0; endpoint[i * 2 + 1] = 1;
      const mz = (az + bz) / 2;
      midZ[i * 2] = mz; midZ[i * 2 + 1] = mz;
    });
    synapsePulseArrays = { start: pulseStart, duration: pulseDuration, dir: pulseDir };
    synapseEdgesGeometry = new THREE.BufferGeometry();
    synapseEdgesGeometry.setAttribute('position', new THREE.BufferAttribute(edgePositions, 3));
    synapseEdgesGeometry.setAttribute('aEndpoint', new THREE.BufferAttribute(endpoint, 1));
    synapseEdgesGeometry.setAttribute('aMidZ', new THREE.BufferAttribute(midZ, 1));
    synapseEdgesGeometry.setAttribute('aPulseStart', new THREE.BufferAttribute(pulseStart, 1));
    synapseEdgesGeometry.setAttribute('aPulseDuration', new THREE.BufferAttribute(pulseDuration, 1));
    synapseEdgesGeometry.setAttribute('aPulseDir', new THREE.BufferAttribute(pulseDir, 1));
    synapseEdgesMaterial = new THREE.ShaderMaterial({
      uniforms: {
        time: { value: 0 },
        scrollZ: { value: 0 },
        blackHoleStrength: { value: 0 },
        blackHoleAngle: { value: 0 },
        edgeOpacity: { value: SYNAPSE_STYLE.edgeOpacity },
        pulseGlowBoost: { value: SYNAPSE_STYLE.pulseGlowBoost },
      },
      vertexShader: SYNAPSE_EDGE_VERT,
      fragmentShader: SYNAPSE_EDGE_FRAG,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      transparent: true,
    });
    scene.add(new THREE.LineSegments(synapseEdgesGeometry, synapseEdgesMaterial));
  };

  // Şema fetch sonuçlanınca katman BİR KEZ kurulur (spec: ara swap yok);
  // hata/boş/askıda kalan istek → prosedürel fallback. Arka plan uygulamayı asla bozamaz.
  // Backend'in hiç yanıt vermediği durumda (ör. erişilemeyen DB'de şema çıkarımı
  // dakikalarca bloklanır) fetch ne resolve ne reject olur; timeout ile fallback'e düşülür.
  // Timeout sonrası gerçek şema gelse bile katman değiştirilmez (tek kurulum kuralı).
  const SCHEMA_FETCH_TIMEOUT_MS = 6000;
  Promise.race([
    apiService.getSchema(false),
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('schema fetch timed out')), SCHEMA_FETCH_TIMEOUT_MS)
    ),
  ])
    .then((schema) => buildSynapseGraph(schema?.graph ?? null, SYNAPSE_STYLE.maxNodes))
    .catch(() => buildSynapseGraph(null))
    .then((graph) => {
      if (isDisposed) return;
      try {
        initSynapseLayer(graph);
      } catch (err) {
        console.warn('[SpaceSpiderweb] Sinaps katmanı kurulamadı:', err);
      }
    });

  // 6. Slower Scroll Event Listener with Smooth Target
  const onWheel = (e: WheelEvent) => {
    // We add to the TARGET, and the render loop will smoothly lerp to it
    targetVirtualScroll += e.deltaY * 0.4; 
  };
  window.addEventListener('wheel', onWheel, { passive: true });

  // 7. Mouse Tracking is now managed dynamically in the top-level script scope

  // 8. The Render Loop
  sceneClock = new THREE.Clock();
  const clock = sceneClock;
  let lastTime = 0;
  let blackHoleAngle = 0;
  
  const tick = () => {
    const elapsedTime = clock.getElapsedTime();
    const deltaTime = Math.min(elapsedTime - lastTime, 0.1); // Clamp deltaTime to prevent jumps on tab focus switch
    lastTime = elapsedTime;

    // Accumulate black hole rotation angle smoothly without time-dependent speed jump
    if (blackHoleState.strength > 0) {
      blackHoleAngle += deltaTime * blackHoleState.strength * 0.15;
    }
    
    // Ambient forward flow: push the target forward slowly (slowed down for cinematic flow)
    targetVirtualScroll += 0.12;
    
    // LERP (Linear Interpolation) for buttery smooth scroll / rewind
    // This removes the "frame by frame" choppy mouse wheel feel
    virtualScroll += (targetVirtualScroll - virtualScroll) * 0.05;
    
    // Update Shader Uniforms
    starsMaterial.uniforms.time.value = elapsedTime;
    starsMaterial.uniforms.scrollZ.value = virtualScroll;
    starsMaterial.uniforms.blackHoleStrength.value = blackHoleState.strength;
    starsMaterial.uniforms.blackHoleAngle.value = blackHoleAngle;
    
    if (synapseNodesMaterial) {
      synapseNodesMaterial.uniforms.time.value = elapsedTime;
      synapseNodesMaterial.uniforms.scrollZ.value = virtualScroll;
      synapseNodesMaterial.uniforms.blackHoleStrength.value = blackHoleState.strength;
      synapseNodesMaterial.uniforms.blackHoleAngle.value = blackHoleAngle;
    }
    if (synapseEdgesMaterial && synapseEdgesGeometry && pulseScheduler && synapsePulseArrays) {
      synapseEdgesMaterial.uniforms.time.value = elapsedTime;
      synapseEdgesMaterial.uniforms.scrollZ.value = virtualScroll;
      synapseEdgesMaterial.uniforms.blackHoleStrength.value = blackHoleState.strength;
      synapseEdgesMaterial.uniforms.blackHoleAngle.value = blackHoleAngle;

      const pulses = pulseScheduler.tick(elapsedTime);
      synapsePulseArrays.start.fill(-1);
      for (const p of pulses) {
        const i0 = p.edgeIndex * 2;
        synapsePulseArrays.start[i0] = p.startTime;
        synapsePulseArrays.start[i0 + 1] = p.startTime;
        synapsePulseArrays.duration[i0] = p.duration;
        synapsePulseArrays.duration[i0 + 1] = p.duration;
        synapsePulseArrays.dir[i0] = p.direction;
        synapsePulseArrays.dir[i0 + 1] = p.direction;
      }
      (synapseEdgesGeometry.attributes.aPulseStart as THREE.BufferAttribute).needsUpdate = true;
      (synapseEdgesGeometry.attributes.aPulseDuration as THREE.BufferAttribute).needsUpdate = true;
      (synapseEdgesGeometry.attributes.aPulseDir as THREE.BufferAttribute).needsUpdate = true;
    }

    // Slowly rotate star layer independently for depth (slowed down for premium feel)
    particleSystem.rotation.z = elapsedTime * 0.012;

    renderer.render(scene, camera);
    animationFrameId = requestAnimationFrame(tick);
  };
  
  tick();

  // 9. Resize Handling
  const onResize = () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  };
  window.addEventListener('resize', onResize);

  // 10. Cleanup
  onUnmounted(() => {
    window.removeEventListener('resize', onResize);
    if (isMouseListenerActive) {
      window.removeEventListener('mousemove', onMouseMove);
    }
    window.removeEventListener('wheel', onWheel);
    cancelAnimationFrame(animationFrameId);
    starsGeometry.dispose();
    starsMaterial.dispose();
    isDisposed = true;
    synapseNodesGeometry?.dispose();
    synapseNodesMaterial?.dispose();
    synapseEdgesGeometry?.dispose();
    synapseEdgesMaterial?.dispose();
    renderer.dispose();
  });
});
</script>

<template>
  <div 
    ref="containerRef" 
    class="w-full h-full pointer-events-none select-none overflow-hidden"
  ></div>
</template>
