# Canlı Şema Sinapsı — Arka Plan Tasarımı (Faz 1)

**Tarih:** 2026-07-02 · **Kapsam:** Frontend (ara iş, sprint dışı; Faz 2 tetiklemesi ileride)
**İlgili dosyalar:** `frontend/src/components/SpaceSpiderweb.vue`,
`frontend/src/utils/graphSelection.ts` (yeniden kullanım), yeni `frontend/src/utils/synapse*.ts`

## 1. Amaç

Mevcut scroll-driven uzay arka planındaki jenerik **geodesic wireframe tüneli**,
uygulamanın kimliğini anlatan bir katmanla değiştirmek: **gerçek veritabanı
şemasından beslenen sinaptik ağ**. Node'lar bağlantılı tablolar, hatlar gerçek FK
ilişkileridir; ağ üzerinde periyodik "sinyal ateşlemeleri" (akson darbeleri) gezer.
Arka plan soyut bir süs olmaktan çıkıp ürünün verisini çizen bir imzaya dönüşür.

**Başarı ölçütü:** Tünel yerine sinaptik ağ render edilir; yıldız akışı ve kara
delik warp senkronu bozulmadan çalışır; ambient ateşleme akıcıdır (60fps hedef);
şema yoksa arka plan prosedürel ağ ile dolu kalır.

## 2. Kapsam dışı (bilinçli, sessiz düşürme yok)

- **Faz 2 — gerçek sorgu tetiklemesi:** `fireSignal()`'ın job pipeline olayına
  bağlanması bu işte YOK. Arayüz (metot) Faz 1'de çalışır halde teslim edilir,
  tetikleyicisi ileride bağlanır.
- Tablo adı/etiket render'ı YOK — arka plan okunabilir olmamalı, soyut kalmalı.
- Backend değişikliği YOK (mevcut `GET /api/schema` kullanılır).
- Şema sekmesindeki D3 graph'a dokunulmaz.

## 3. Mimari

Üç saf (pure) TS modülü + `SpaceSpiderweb.vue` içinde bir render katmanı:

### 3.1 `frontend/src/utils/synapseLayout.ts` (saf, testli)
```ts
interface SynapseNode { id: string; x: number; y: number; z: number; degree: number }
interface SynapseEdge { sourceIndex: number; targetIndex: number }
interface SynapseLayout { nodes: SynapseNode[]; edges: SynapseEdge[] }

function computeSynapseLayout(nodes: string[], edges: {source: string; target: string}[],
                              opts?: { iterations?: number; radius?: number }): SynapseLayout
```
- **Deterministik:** başlangıç pozisyonları tablo-adı hash'inden türetilir (seeded
  PRNG, örn. mulberry32); `Math.random`/`Date.now` KULLANILMAZ. Aynı şema → her
  açılışta aynı takımyıldız.
- ~200 iterasyon basit 3D force relaxation (bağlı çekme + evrensel itme + merkez
  yerçekimi). 150 node için CPU maliyeti milisaniyeler; mount'ta bir kez koşar.
- Hub'lar (yüksek degree) merkeze yakın konumlanır (degree ile ölçekli merkez çekimi).

### 3.2 `frontend/src/utils/synapseNetwork.ts` (saf, testli)
```ts
function buildSynapseGraph(schemaGraph: {nodes: string[]; edges: GraphEdgeInput[]} | null,
                           maxNodes?: number /* default 150 */): { nodes: string[]; edges: ... }
```
- Şema graph'ı varsa **`selectGraphData` (graphSelection.ts) yeniden kullanılır**:
  yalnız bağlantılı tablolar, degree-sıralı, üst sınır 150.
- Şema yok/boş/hata → **prosedürel fallback**: seeded küçük-dünya ağı (~60 node,
  ~90 edge). Arka plan asla boş kalmaz.

### 3.3 `frontend/src/utils/synapsePulse.ts` (saf, testli)
Darbe zamanlama/zincir durum makinesi — render'dan bağımsız:
```ts
interface Pulse { edgeIndex: number; startTime: number; duration: number; generation: number }
class PulseScheduler {
  constructor(layout: SynapseLayout, opts?: {seed?: number; maxConcurrent?: number /*8*/;
              intervalMin?: number /*2s*/; intervalMax?: number /*4s*/; maxHops?: number /*2*/})
  tick(now: number): Pulse[]          // aktif darbe listesi (shader attribute'larına yazılır)
  fire(nodeIds: string[], now: number): void  // Faz 2 giriş noktası
}
```
- `tick(now)`: zamanı parametre alır (test edilebilirlik; komponentte `clock.getElapsedTime()`).
- Ambient: 2–4 sn'de bir rastgele (seeded) node ateşler; darbe bitince komşu
  edge'lere `generation+1` ile sıçrar (maks 2 hop, sönümlenerek); eşzamanlı darbe
  sayısı 8 ile sınırlı (fazlası düşürülür).
- `fire()` aynı zincir mekanizmasını verilen node'lardan başlatır (Faz 2 kancası).

### 3.4 `SpaceSpiderweb.vue` değişiklikleri
- **Kaldırılır:** geodesic tünel geometrileri/materyalleri/mesh'leri ve tüneli
  besleyen kod (barycentric helper YALNIZ tünel kullanıyorsa onunla birlikte).
- **Eklenir:** sinaps katmanı — tek `THREE.LineSegments` (edge'ler) + tek
  `THREE.Points` (node'lar), tek shader çifti.
  - Edge rengi: loş indigo (`#4f46e5`, düşük opacity, additive). Node: zinc-beyaz,
    degree'ye göre boyut; en yüksek degree'li ~%10 node hafif amber tonda.
  - **Darbe render'ı:** her edge'e `pulseStart`/`pulseDuration` attribute'ları;
    fragment/vertex shader `time` uniform'u ile darbe konumunu hat boyunca
    ilerletip cyan (`#22d3ee`) glow çizer. Frame başına CPU işi yalnız
    `PulseScheduler.tick()` sonucunu attribute buffer'a yazmaktır (≤8 darbe).
  - **Uniform sözleşmesi devralınır:** `time`, `scrollZ`, `blackHoleStrength`,
    `blackHoleAngle` — tünelin vertex-shader warp bloğu (vortex twist +
    spaghettification + z-pull, bhCenter x=85.0) sinaps shader'ına birebir taşınır.
    Böylece şema sekmesi geçişindeki kara delik efekti sinaps ağını da büker.
  - **Scroll:** tünel gibi `pos.z += scrollZ` + sonsuz wrap (mod 800, ±400) —
    kamera ağın kopyaları arasında süzülür.
- **Veri yükleme:** `onMounted`'ta `apiService.getSchema()` (cache'ten, `refresh=false`)
  best-effort çağrılır. Sinaps katmanı fetch sonuçlanınca **bir kez** kurulur
  (başarı → gerçek ağ, hata/boş → fallback); fetch bitene kadar yalnız yıldızlar
  görünür. Ara "fallback göster → sonra swap et" YAPILMAZ (görsel pop önlenir).
- **Dışa açılan API:** `defineExpose({ fireSignal(tableNames: string[]) })` —
  isimleri node id'lerine eşler, `PulseScheduler.fire()` çağırır. Faz 1'de çağıran yok.

## 4. Veri akışı

```
apiService.getSchema() ──(graph{nodes,edges})──> buildSynapseGraph (selectGraphData reuse)
        │ hata/boş                                        │
        └──> prosedürel fallback ─────────────────────────┤
                                                          ▼
                                              computeSynapseLayout (deterministik)
                                                          ▼
                     LineSegments/Points buffer'ları + PulseScheduler
                                                          ▼
                render döngüsü: tick(now) → pulse attribute'ları → shader
```

## 5. Hata yönetimi ve korkuluklar

- `getSchema` hatası sessizce yutulur (console.warn) → fallback ağ; arka plan
  hiçbir durumda uygulamayı bozamaz (try/catch ile katman kurulumunun tamamı korunur).
- `prefers-reduced-motion: reduce` → PulseScheduler devre dışı (statik loş ağ);
  mevcut yıldız/scroll davranışı bileşenin bugünkü haliyle aynı kalır.
- Node sayısı > 150 → `selectGraphData` limiti keser (en bağlantılı 150).
- Bellek: tünel kaldırıldığı için net GPU yükü artmaz; unmount'ta geometry/material
  dispose edilir (mevcut cleanup düzenine eklenir).

## 6. Test stratejisi

Frontend'de framework yok; mevcut düzen (`node --experimental-strip-types`,
`frontend/tests/`) kullanılır. Saf modüller TDD ile:
- `synapseLayout`: determinizm (aynı girdi → aynı çıktı), hub-merkez eğilimi
  (ortalama hub yarıçapı < ortalama yaprak yarıçapı), boş girdi çökmez.
- `synapseNetwork`: şema → selectGraphData yeniden kullanımı (bağlantılı-yalnız,
  150 sınırı), null/boş şema → fallback ağın node/edge sayıları ve determinizmi.
- `synapsePulse`: ambient aralık (2–4 sn), maxConcurrent=8 sınırı, 2-hop zincir
  sönümü, `fire()` verilen node'lardan başlatır, seeded determinizm.
Shader/görsel katman: manuel doğrulama (dev server + göz).

## 7. Riskler / açık noktalar

- **Görsel yoğunluk ayarı** (opacity/boyut/darbe parlaklığı) subjektiftir; koddaki
  sabitler tek bir `SYNAPSE_STYLE` objesinde toplanır ki elle ayar kolay olsun.
- Çok küçük şemalarda (ör. 5 tablo) ağ cılız kalabilir → fallback ağ ile
  harmanlanmaz (gerçek veri gerçek kalır); cılızlık kabul edilir.
- `vue-tsc` main'de zaten kırık (7 eski hata) — bu iş yeni tip hatası eklememeli;
  doğrulama `npx vite build` + testlerle yapılır.
