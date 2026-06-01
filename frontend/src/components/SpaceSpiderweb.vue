<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import * as THREE from 'three';
import gsap from 'gsap';

const props = defineProps<{
  activeTab: string;
}>();

const containerRef = ref<HTMLElement | null>(null);

let animationFrameId: number | null = null;
let renderer: THREE.WebGLRenderer;
let scene: THREE.Scene;
let camera: THREE.PerspectiveCamera;
let coreGeometry: THREE.BufferGeometry;
let coreMaterial: THREE.ShaderMaterial;
let innerGeometry: THREE.BufferGeometry;
let innerMaterial: THREE.ShaderMaterial;
let innerMesh: THREE.Mesh;
let starsGeometry: THREE.BufferGeometry;
let starsMaterial: THREE.ShaderMaterial;
let particleSystem: THREE.Points;
let outerTunnel: THREE.Mesh;
let clock: THREE.Clock;
let virtualScroll = 0; // The actual smooth scroll value
let targetVirtualScroll = 0; // The target scroll value set by the wheel

const blackHoleState = { strength: 0 };

let isMouseListenerActive = false;
let isRenderLoopRunning = false;

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

const startRenderLoop = () => {
  if (isRenderLoopRunning) return;
  isRenderLoopRunning = true;
  tick();
};

const stopRenderLoop = () => {
  isRenderLoopRunning = false;
  if (animationFrameId !== null) {
    cancelAnimationFrame(animationFrameId);
    animationFrameId = null;
  }
};

let lastTime = 0;
let blackHoleAngle = 0;
const tick = () => {
  if (!isRenderLoopRunning) return;
  if (!clock || !renderer || !scene || !camera) {
    animationFrameId = requestAnimationFrame(tick);
    return;
  }

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
  virtualScroll += (targetVirtualScroll - virtualScroll) * 0.05;
  
  // Update Shader Uniforms
  starsMaterial.uniforms.time.value = elapsedTime;
  starsMaterial.uniforms.scrollZ.value = virtualScroll;
  starsMaterial.uniforms.blackHoleStrength.value = blackHoleState.strength;
  starsMaterial.uniforms.blackHoleAngle.value = blackHoleAngle;
  
  coreMaterial.uniforms.time.value = elapsedTime;
  coreMaterial.uniforms.scrollZ.value = virtualScroll;
  coreMaterial.uniforms.blackHoleStrength.value = blackHoleState.strength;
  coreMaterial.uniforms.blackHoleAngle.value = blackHoleAngle;
  
  innerMaterial.uniforms.time.value = elapsedTime;
  innerMaterial.uniforms.scrollZ.value = virtualScroll;
  innerMaterial.uniforms.blackHoleStrength.value = blackHoleState.strength;
  innerMaterial.uniforms.blackHoleAngle.value = blackHoleAngle;

  // Slowly rotate layers independently for depth (slowed down for premium feel)
  particleSystem.rotation.z = elapsedTime * 0.012;
  innerMesh.rotation.y = elapsedTime * 0.008;
  innerMesh.rotation.x = Math.sin(elapsedTime * 0.08) * 0.04;

  renderer.render(scene, camera);
  animationFrameId = requestAnimationFrame(tick);
};

watch(() => props.activeTab, (newTab) => {
  updateMouseListener(newTab);
  if (newTab === 'schema') {
    stopRenderLoop();
    gsap.to(blackHoleState, {
      strength: 1.0,
      duration: 2.0,
      ease: 'power2.out'
    });
  } else {
    if (renderer) {
      startRenderLoop();
    }
    gsap.to(blackHoleState, {
      strength: 0.0,
      duration: 1.5,
      ease: 'power2.inOut'
    });
  }
}, { immediate: true });

onMounted(() => {
  if (!containerRef.value) return;

  // 1. Scene Setup
  scene = new THREE.Scene();
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

  particleSystem = new THREE.Points(starsGeometry, starsMaterial);
  scene.add(particleSystem);


  // 5. Geodesic Wireframe Tunnel (Mixed Polygons: triangles + pentagons)
  // Helper: add barycentric coordinates to non-indexed geometry for thin wireframe rendering
  const addBarycentricAttr = (geo: THREE.BufferGeometry) => {
    const nonIndexed = geo.index ? geo.toNonIndexed() : geo.clone();
    const count = nonIndexed.attributes.position.count;
    const bary = new Float32Array(count * 3);
    for (let i = 0; i < count; i += 3) {
      bary[i * 3]     = 1; bary[i * 3 + 1] = 0; bary[i * 3 + 2] = 0;
      bary[(i+1) * 3] = 0; bary[(i+1) * 3 + 1] = 1; bary[(i+1) * 3 + 2] = 0;
      bary[(i+2) * 3] = 0; bary[(i+2) * 3 + 1] = 0; bary[(i+2) * 3 + 2] = 1;
    }
    nonIndexed.setAttribute('barycentric', new THREE.BufferAttribute(bary, 3));
    return nonIndexed;
  };

  // Barycentric wireframe vertex shader (shared)
  const wireVertexShader = `
    uniform float time;
    uniform float scrollZ;
    uniform float blackHoleStrength;
    uniform float blackHoleAngle;
    attribute vec3 barycentric;
    varying vec3 vBary;
    varying float vDepth;
    
    void main() {
      vBary = barycentric;
      vec3 pos = position;
      
      // Elegant twisting (slowed down for premium feel)
      float twist = sin(pos.z * 0.002 + time * 0.1) * 0.2;
      mat2 rot = mat2(cos(twist), -sin(twist), sin(twist), cos(twist));
      pos.xy = rot * pos.xy;
      
      // Gentle wave (slowed down for premium feel)
      float wave = sin(pos.x * 0.006 + time * 0.15) * 8.0;
      pos.z += wave;

      // Apply virtual scroll to move through the tunnel
      pos.z += scrollZ;

      // Wrap around for infinite tunnel
      pos.z = mod(pos.z + 400.0, 800.0) - 400.0;
      
      // Apply Gravitational Black Hole warp if active
      if (blackHoleStrength > 0.0) {
        // Shift gravity center to the right (x=85.0) to match the D3 topological schema black hole container position on screen
        vec2 bhCenter = vec2(85.0, 0.0);
        vec2 distVec = pos.xy - bhCenter;
        float r = length(distVec) + 0.1;
        
        // 1. Vortex swirl twist: spins vertices dramatically as they approach the center + continuous slow flow (reduced transition snap)
        float swirl = (4.5 / (r * 0.03 + 2.5)) * blackHoleStrength + blackHoleAngle;
        float cosA = cos(swirl);
        float sinA = sin(swirl);
        vec2 rotatedVec = mat2(cosA, -sinA, sinA, cosA) * distVec;
        
        // 2. High-Drama Spaghettification Suction: pulls vertices near center exponentially faster, stretching the geometry
        float pull = mix(1.0, pow(clamp(r / 550.0, 0.0, 1.0), 1.8), blackHoleStrength * 0.95);
        pos.xy = bhCenter + rotatedVec * pull;
        
        // 3. Extreme Singularity Z-Depth Suction: pulls the vortex center deep into the screen abyss
        pos.z -= mix(0.0, 750.0 / (r * 0.005 + 1.0), blackHoleStrength);
      }

      vDepth = pos.z;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
    }
  `;

  // Barycentric wireframe fragment shader (shared)
  const wireFragmentShader = `
    uniform float time;
    varying vec3 vBary;
    varying float vDepth;
    
    void main() {
      // Barycentric wireframe: ultra-thin edge detection
      float minBary = min(min(vBary.x, vBary.y), vBary.z);
      float edge = 1.0 - smoothstep(0.0, fwidth(minBary) * 1.5, minBary);
      
      if (edge < 0.05) discard;
      
      // Bright whitish iridescent / rainbow-shifted palette
      vec3 rainbow = 0.5 + 0.5 * cos(time * 0.6 + vDepth * 0.004 + vec3(0.0, 2.0, 4.0));
      vec3 color = mix(vec3(0.95, 0.95, 1.0), rainbow, 0.45);
      
      // Smooth depth fade
      float depthFade = smoothstep(-400.0, 400.0, vDepth);
      
      gl_FragColor = vec4(color, edge * 0.55 * depthFade);
    }
  `;

  // Primary layer: Icosahedron (geodesic triangular mesh - large outer tunnel)
  const icoBase = new THREE.IcosahedronGeometry(550, 2);
  coreGeometry = addBarycentricAttr(icoBase);
  icoBase.dispose();
  
  coreMaterial = new THREE.ShaderMaterial({
    uniforms: {
      time: { value: 0 },
      scrollZ: { value: 0 },
      blackHoleStrength: { value: 0 },
      blackHoleAngle: { value: 0 }
    },
    vertexShader: wireVertexShader,
    fragmentShader: wireFragmentShader,
    transparent: true,
    blending: THREE.AdditiveBlending,
    side: THREE.BackSide,
    extensions: { derivatives: true }
  });

  outerTunnel = new THREE.Mesh(coreGeometry, coreMaterial);
  scene.add(outerTunnel);

  // Secondary layer: Dodecahedron (pentagonal faces - smaller inner structure)
  const dodecBase = new THREE.DodecahedronGeometry(350, 1);
  innerGeometry = addBarycentricAttr(dodecBase);
  dodecBase.dispose();
  
  innerMaterial = new THREE.ShaderMaterial({
    uniforms: {
      time: { value: 0 },
      scrollZ: { value: 0 },
      blackHoleStrength: { value: 0 },
      blackHoleAngle: { value: 0 }
    },
    vertexShader: wireVertexShader,
    fragmentShader: wireFragmentShader,
    transparent: true,
    blending: THREE.AdditiveBlending,
    side: THREE.BackSide,
    extensions: { derivatives: true }
  });

  innerMesh = new THREE.Mesh(innerGeometry, innerMaterial);
  scene.add(innerMesh);

  // 6. Slower Scroll Event Listener with Smooth Target
  const onWheel = (e: WheelEvent) => {
    // We add to the TARGET, and the render loop will smoothly lerp to it
    targetVirtualScroll += e.deltaY * 0.4; 
  };
  window.addEventListener('wheel', onWheel, { passive: true });

  // 7. Mouse Tracking is now managed dynamically in the top-level script scope

  // 8. The Render Loop
  clock = new THREE.Clock();
  
  if (props.activeTab !== 'schema') {
    startRenderLoop();
  }

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
    stopRenderLoop();
    starsGeometry.dispose();
    starsMaterial.dispose();
    coreGeometry.dispose();
    coreMaterial.dispose();
    innerGeometry.dispose();
    innerMaterial.dispose();
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
