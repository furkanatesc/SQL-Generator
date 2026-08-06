# Teknik Borç ve Geçici Çözümler (Tech Debt & Workarounds)

Bu dosya, projede karşılaşılan sorunları hızlıca çözmek için uygulanan geçici
yöntemleri (workarounds) ve teknik borç (technical debt) notlarını içerir.
İleride sistem mimarisi iyileştirilirken bu çözümler kalıcı yöntemlerle
değiştirilmelidir.

> Sürüm geçmişi için `CHANGELOG.md`, yol haritası için `ROADMAP.md` ve
> `docs/PLANNED-SPRINTS.md` dosyalarına bakın.

---

## 1. NVIDIA Batch Embedding API Token Limit Aşımı (22 Mayıs 2026) — ÇÖZÜLDÜ

**Hata Logu:**
`[SchemaEmbedding] Embedding indeksleme başarısız: NVIDIA Batch Embedding API Hatası 400: {"error":"Input length 1728 exceeds maximum allowed token size 512"}`

**Neden:**
NVIDIA NIM Embedding API'si (ve çoğu standart embedding modeli) metin başına
maksimum 512 token boyutunu kabul etmektedir. Şema indeksleme sırasında
(`backend/app/schema_embedding.py`), özellikle çok fazla kolonu olan tabloların
(örn: 100+ kolon) tüm kolon isimleri ve foreign key kısıtları birleştirilip
"semantic fingerprint" çıkarıldığında bu token limiti aşılmaktadır.

**Uygulanan Çözüm:**
`baai/bge-m3` modelinde yaşanan NVIDIA NIM sunucu çökmeleri (500 Error) sebebiyle,
varsayılan embedding modeli, daha geniş bağlam boyutunu destekleyen ve çok daha
stabil olan `nvidia/llama-nemotron-embed-1b-v2` ile değiştirildi. Qdrant'taki
vektör boyutu bu modele uygun olacak şekilde **2048** olarak ayarlandı. Karakter
kırpma (truncation) limiti `25000` karaktere çıkarılarak tüm tablo şemalarının
eksiksiz embedding işleminden geçmesi sağlandı; kolon veri tipleri de semantic
fingerprint'e dahil edildi.

**Tek doğru kaynak (kodla doğrulanmıştır):**
- Model: `nvidia/llama-nemotron-embed-1b-v2` — `backend/app/rag_manager.py:16`
- Vektör boyutu: `2048` — `backend/app/rag_manager.py:123`

> ✅ Not (27.11): `FEATURE.md` ve özel bir RAG dokümanı **YOK** — güncellenmesi
> gereken stale bir doküman bulunmuyor; `README` zaten koddaki değerlerle
> uyumlu. `backend/app/retrieval/nvidia_embedding_provider.py`'deki `dimension`
> parametresinin varsayılanı **1024 → 2048** olarak `rag_manager.py`'deki
> gerçek vektör boyutuyla hizalandı. Bu kalem tamamen kapandı.

**Gelecekte Yapılabilecek Geliştirmeler (Opsiyonel):**
- Tablolar indekslenirken bütün kolonların tek satıra sıkıştırılması yerine
  tabloları mantıksal alt parçalara (chunk) bölerek indeksleme (RAG için alt
  tablo stratejisi) düşünülmelidir.
- Büyük şemalarda kolon meta verileri ayrı node/vektör olarak tutulup
  hiyerarşik (Parent-Child Retriever) RAG mimarisi uygulanabilir.

---

## 2. D3 Graph UI Performans Limiti (maxNodesLimit = 5) — BÜYÜK ÖLÇÜDE ÇÖZÜLDÜ (2026-07-02 ara fix)

**Eski durum:** Tarayıcı çökmesini engellemek için `maxNodesLimit` varsayılan
olarak **5 tabloya** sınırlandırılmıştı; üstelik top-N seçimi *izole tablolar
dahil tüm tablolar* üzerinden yapılıp yalnızca iki ucu da seçimde kalan edge'ler
çizildiğinden, örnek şemada (2175 tablo / 93 FK) ilişkilerin yalnızca **3/93**'ü
görünüyordu. "Limitsiz" seçeneği ise 2073'ü tamamen izole olan 2175 node'u
render ederek tarayıcıyı kilitliyordu — donmanın asıl kaynağı buydu.

**Uygulanan çözüm (ara fix, 2026-07-02):** Node/edge seçim mantığı saf
`frontend/src/utils/graphSelection.ts` modülüne çıkarıldı. İzole (ilişkisiz)
tablolar artık **hiç çizilmiyor**; limit yalnızca bağlantılı tablolar arasında
uygulanıyor ve varsayılan `0 = tüm bağlantılı tablolar` oldu (örnek şemada 102
tablo + 93/93 ilişki, akıcı render). Graph paneli render istatistiği gösteriyor
("X/Y bağlantılı tablo · Z ilişki · N izole tablo gizlendi"). Test:
`frontend/tests/graphSelection.test.ts`.

**Kalan borç (Phase 12 · 31.x UI/UX Production Layer'a aday):** *Bağlantılı*
tablo sayısının da binlere ulaştığı şemalarda D3 force-directed SVG render yine
zorlanır; kalıcı çözüm için kademeli yükleme (progressive/virtualized
rendering), WebGL tabanlı graph kütüphanesi veya sunucu tarafı layout
hesaplaması değerlendirilmelidir. `Node Limiti` girişi bu senaryo için kaçış
kapısı olarak korunmuştur. Ayrıca frontend'de test framework yok;
`graphSelection` testleri şimdilik `node --experimental-strip-types` ile koşulan
tek dosyalık script'tir (vitest kurulumu ayrı bir kalem).

*İlgili Dosyalar:* `frontend/src/components/SchemaManager.vue`,
`frontend/src/utils/graphSelection.ts`, `frontend/tests/graphSelection.test.ts`

---

## 3. SKIPPED span'lerde `duration_ms` düşürülüyor (Sprint 27.1w) — ÇÖZÜLDÜ (27.11)

> ✅ Çözüm (27.11): 5 builder'ın tamamı (intent/retrieval/prompt/generation/
> validation) artık SKIPPED dalında da kendilerine verilen ölçülen
> `duration_ms`'i taşıyor; aşağıdaki "Karar gerektiren nokta" seçenek (a)
> yönünde çözüldü (SECURITY span'inde zaten uygulanan precedent'le tutarlı).
> Testler: `backend/tests/trace/test_end_to_end_trace_builders.py`.

**Sorun:**
`build_intent_span` ve `build_retrieval_span`, `result is None` erken-dönüş
dalında `TraceSpan(..., status=SKIPPED)` kuruyor ve kendilerine verilen
`duration_ms` argümanını **hiç kullanmıyor** — imzaları kabul etmesine rağmen
sessizce düşüyor.

**Etkisi:**
Canlı yolda intent extraction koşmadığı için INTENT span'i her zaman SKIPPED
olur; dolayısıyla `_stage_intent`'in ölçülen süresi (`intent_ms`) happy path'te
payload'a **inmez**. Süre yalnızca INTENT *hata* dalında (elle kurulan ERROR
span'i) taşınır. Aynı desen RETRIEVAL/SKIPPED için de geçerli.

**Neden şimdilik böyle:**
27.1w planının düzyazı kuralı (satır 187) "duration_ms: her builder'a
`stage_timings.get(<stage adı>)` verilir" diyor, ama planın kendi referans kodu
INTENT/SECURITY'ye geçmiyordu — plan kendi içinde çelişiyordu. Whole-branch
review bunu yakaladı; SECURITY tarafı düzeltildi (`build_security_span` artık
`duration_ms` alıyor ve SKIPPED dahil tüm dallarda taşıyor). INTENT/RETRIEVAL'ın
SKIPPED dalına dokunmak onaylanan fix kapsamı dışındaydı ve semantik bir soru
içeriyor: **koşmamış (SKIPPED) bir stage'e süre iliştirmek doğru mudur?**
`_stage_intent` duvar saati harcıyor ama intent *extraction* koşmuyor.

**Karar gerektiren nokta:**
Ya (a) SKIPPED span'ler de gerçek duvar saatini taşısın (planın düzyazı kuralı
birebir uygulanır), ya da (b) SKIPPED span'in süresiz olması sözleşmenin bir
parçası kabul edilip planın düzyazı kuralı düzeltilir. Şu an (b) fiilen
geçerli ama yazılı değil.

*İlgili Dosyalar:* `backend/app/trace/end_to_end_trace_builders.py:114-115`
(`build_intent_span`), `:146-147` (`build_retrieval_span`),
`backend/app/trace/live_trace_assembly.py`

---

## §4. Error taxonomy v2'nin ulaşamadığı sınırlar (Sprint 27.2) — KISMEN ÇÖZÜLDÜ (27.2.1)

Sprint 27.2 taksonomiyi tek registry'de topladı ama bilinçli olarak pipeline
katmanında durdu. Kalanlar:

1. ~~**İş/API/frontend sınırı (27.2.1).**~~ — **ÇÖZÜLDÜ (Sprint 27.2.1).**
   `jobs` tablosuna `error_code TEXT` kolonu eklendi (`database.py`),
   `update_job_status` dinamik SET-clause'a refactor edildi, `main.py` job
   runner'ı pipeline kodunu `ErrorCode.value` string'i olarak persist ediyor,
   `JobDetailResponse` alanı taşıyor ve frontend `Job` interface'i onu
   alıyor. Beklenmeyen (INTERNAL) exception'da kod `NULL` kalır — registry'nin
   INTERNAL → kod-yok tasarımıyla tutarlı. `error_code`'un UI'da GÖRÜNÜR
   kullanımı (rozet, yerelleştirilmiş mesaj eşlemesi) hâlâ yapılmadı.
2. ~~**`api.ts` `detail` bug'ı (kullanıcı-görünür).**~~ — **ÇÖZÜLDÜ (Sprint 27.2.1).**
   Saf `extractApiErrorMessage` helper'ı çıkarıldı
   (`frontend/src/utils/apiError.ts`): önce `{"error":{"message"}}` envelope'una,
   sonra geriye dönük tolerans olarak `detail`'e bakar, ikisi de yoksa fallback
   döner. RAG search / business-rule index / SQL-history index çağrı noktaları
   bu helper'ı kullanıyor; kullanıcı artık backend'in gerçek mesajını görüyor.
   Testi `frontend/tests/apiError.test.ts` (node-script; vitest hâlâ kurulu
   değil ve frontend testleri CI'da koşmuyor — ayrı bir borç kalemi).
3. **`ExecutionSpanDetail.error_code` hâlâ beslenmiyor — ERTELENDİ (bağımlılık).**
   27.0 spec §137 bu alanı "mevcut error taxonomy kodu" için açmıştı. Enum artık
   gerçek bir değer sağlayabiliyor ama **canlı pipeline SQL'i execute etmiyor**:
   EXECUTION span'i koşulsuz `SKIPPED` (`live_trace_assembly.py:177`, 27.0 spec
   §1.4). Beslenecek bir execution `error_code`'u YOK; SKIPPED span için altyapı
   kurmak YAGNI ihlali olurdu. **Bu kalem taksonomi-sınır meselesi değildir;
   canlı execution'ı etkinleştiren faza bağımlıdır** ve o fazla birlikte
   çözülmelidir (Sprint 27.2.1'de bilinçli olarak kapsam dışı bırakıldı).
4. **`classify_sql_error` hâlâ düzyazı ayrıştırıyor.** Sıra bug'ı düzeltildi ama
   mimari çözüm (validator'ların kod döndürmesi, mesaj eşlemek yerine)
   yapılmadı.
5. **`SQLFailureCategory`** (`evaluation/failure_analytics.py:39`) ayrı bir
   taksonomi olarak duruyor — eval'e özel, farklı eksen, birleştirilmedi.
6. **HTTP `code` sözlüğü** (`api/errors.py:13`) hâlâ status-türevi ve domain
   taksonomisiyle hiçbir şey paylaşmıyor.
7. **`retryable` ekseni** registry'de yok; `EmbeddingRetryableError`
   (`retrieval/embedding_pipeline.py:18`) onu ayrı bir hiyerarşide yeniden icat
   etmiş durumda. Registry'ye alan eklemek kırıcı değildir — retry mantığı
   gelen sprint'te birleştirilebilir.
8. **`details["error_type"]`** (`sql_execution_errors.py:52`) bir Python sınıf
   adı taşıyor, taksonomi kodu değil. Ad çakışması kafa karıştırıcı; yeniden
   adlandırmak kapsam dışıydı.
9. **Geliştirme trace DB'si migrate edilmedi.** `backend/data/nl2sql_traces.db`
   gitignore'da; eski satırlar v1 kod adlarını taşır ve `?error_type=` filtresiyle
   eşleşmez. Kabul edilen maliyet.

---

## §5. Sprint 27.4 (Query Replay System) devirleri — AÇIK

1. ~~**Purity guard'ları aynı süreçte ölçüyor (kardeş paketler).**~~ —
   **ÇÖZÜLDÜ (27.11).** 27.4'te `app/replay/` guard'ı taze bir alt sürece
   (`subprocess`) taşındı, çünkü aynı süreçte `sys.modules` cache'i sızıntıyı
   maskeliyordu: whole-branch review `baseline_extraction.py`'ye kasten
   `app.trace` importu enjekte etti ve guard **tam suite'te tamamen yeşil
   kaldı** (yalnız izole koşuda fail etti). Aynı yapısal kusur
   `backend/tests/errors/test_errors_package_purity.py` ve
   `backend/tests/feedback/test_feedback_package_purity.py` içinde de vardı;
   errors+feedback purity guard'ları taze-alt-sürece taşındı (27.11) — ikisi de
   artık `subprocess` ile taze bir Python sürecinde koşuyor, `rule_suggestions`
   guard'ıyla aynı desen.
2. ~~**`test_api_surface.py`'deki `expected_routes` seti OpenAPI snapshot'ından
   türemiyor.**~~ — **ÇÖZÜLDÜ (27.11).** `backend/scripts/generate_contract_snapshots.py`
   onu senkron tutmuyordu; her yeni endpoint'te elle 1 satır ekleniyordu (27.3 ve
   27.4'te iki kez yapıldı). `expected_routes` artık OpenAPI snapshot'ından
   türetilir (27.11); tek kaynak snapshot — sessiz drift riski kapandı.
3. **`live_trace_assembly` güvenlik span'ini STAGE adına göre kuruyor.** 27.4'te
   replay tarafı 27.2 registry kategorisine geçirildi (`ErrorCategory.SECURITY`), ama
   *emit* tarafı hâlâ stage-tabanlı: `sql_parse_error` (kategorisi `validation`,
   retryable) canlı trace'in SECURITY span'ine `outcome="denied"` olarak yazılmaya
   devam ediyor. Replay artık bunu süzüyor, fakat trace'in kendisi hâlâ yanıltıcı —
   `/api/debug/traces` üzerinden bakan bir insan "güvenlik reddi" görür. Emit tarafını
   da kategoriye taşımak 27.4 kapsamı dışıydı (27.1w yüzeyini değiştirirdi).
4. **Fail olmuş job'ların üretilen SQL'i saklanmıyor** → replay'in
   `validation_recovery` verdict'i bugünkü veri modelinde **ulaşılamaz**, ve
   `security_regression` yalnız başarılı job'larda ölçülebilir. `jobs.result_sql`
   yalnız `"completed"` durumunda yazılıyor. Taksonomi üyesi sözleşme tamlığı için
   korunuyor; gerçek çözüm ayrı bir kalem (bkz. 27.4 spec §8).

---

## §6. Sprint 27.5 (Debug Bundle Export) devirleri — AÇIK

1. **`_latest_debug_trace` `trace_type` filtresi olmadan `limit=5` kullanıyor.**
   `bundle_service.py:38-47` job'ın en yeni 5 trace kaydını çekip aralarında
   `end_to_end` OLMAYANI arıyor. Bir job'a ait `end_to_end` trace sayısı debug
   trace'ten önce 5'i geçerse (örn. tekrarlanan replay/export çağrıları veya
   çok adımlı retry döngüsü ek `end_to_end` kaydı biriktirirse), asıl debug
   trace pencerenin dışında kalır ve bundle'ın `sql` bölümü `null` döner. Gerçek
   çözüm: sorguyu debug trace türüne göre filtrelemek (store adaptöründe
   `trace_type != end_to_end` desteği gerekiyor) ya da limiti büyütmek.
   *İlgili Dosya:* `backend/app/bundle_service.py:38-47`
2. **Şema bölümü tam DDL snapshot'ı taşımıyor.** `BundleSchemaInfo`
   (`backend/app/debug_bundle/contract.py:54-61`) yalnız `selected_tables` (isim
   listesi) + `schema_hash` taşır; kolon/tip/FK detayları bundle'a hiç girmez,
   çünkü tam DDL snapshot hiçbir yerde persist edilmiyor. Bilinçli kapsam dışı
   bırakıldı (27.5 spec); gerçek DDL snapshot ihtiyacı doğarsa ayrı bir
   persistence kalemi gerekir. *İlgili Dosya:*
   `backend/app/debug_bundle/{contract,projectors}.py`

---

## §7. Sprint 27.6 (Metrics Contract) devirleri — AÇIK

1. **`scan_cap` (10000) üstündeki pencerelerde metrikler tam popülasyon
   yerine çekilen alt küme üzerinden hesaplanır.** `metrics_service.py:13,20-39`
   RAW trace store'dan `scan_cap + 1` limitiyle fetch eder; pencere bu sınırı
   aşarsa `truncated=true` bayrağı doğru şekilde işaretlenir, ama `compute_metrics`
   yine de yalnızca ilk `scan_cap` kaydı görür — `success_rate`/`by_code`/
   percentile'lar tam popülasyonu değil, kesilmiş alt kümeyi yansıtır. Tam
   doğruluk için DB-side aggregation (COUNT/GROUP BY, percentile query'leri)
   gerekir; şu an yok — bilinçli kapsam dışı (27.6 spec), `scan_cap`'in
   query parametresinden ayarlanabilir olması da aynı nedenle ertelendi.
   *İlgili Dosya:* `backend/app/metrics_service.py:13-39`

---

## §8. Sprint 27.7 (Admin Observability Dashboard Backend) devirleri — AÇIK

Opus whole-branch review verdict'i **SHIP** (0 Critical, 0 bloke); aşağıdakiler
bilinçli olarak ertelendi (sessiz düşürme yok).

1. **`feedback` bölümü ile trace bölümleri (`metrics`/`timeseries`/`recent`) aynı
   istekte FARKLI zaman penceresi yansıtabilir (naive-timestamp sınırlarında).**
   *(Review bulgusu #1 — Important.)* `dashboard_service.build_dashboard` tek bir
   `created_after`/`created_before` sınırını iki tüketiciye fan-out eder ama
   filtreleme yolları farklı: (a) trace tarafı `TraceQuery` → `sqlite_store` sınırı
   `datetime.fromisoformat(...).astimezone(utc)` ile normalize eder → **naive** bir
   sınır sunucunun **yerel** saati sayılıp kayar; (b) `database.list_feedback` sınırı
   ham string olarak **leksikografik** karşılaştırır ve `feedback.created_at`
   `datetime.utcnow().isoformat()` (naive-UTC) saklanır. Sunucu UTC+3 iken
   `?created_after=2026-07-31T00:00:00` trace'leri `2026-07-30T21:00:00Z`'den, feedback'i
   `2026-07-31T00:00:00` UTC-clock'tan filtreler → tek `window` başlığı altında 3 saat
   daha geniş bir trace penceresi. **Kök neden büyük ölçüde pre-existing altyapı**
   (store'un naive→yerel davranışı + feedback'in naive-UTC saklaması); 27.7 yalnızca
   sınırı ikisine dağıtır. İkincil kenar: tam-saniye sınırında offset'li sınır string'i
   (`...+00:00`) offset'siz feedback damgasından uzun→büyük sıralanır, `>=` sınır satırını
   yanlışlıkla dışlar. **Çözüm:** ya sınırların offset-aware ISO olması dokümante edilir,
   ya da adaptör feedback sınırını trace yoluyla aynı normalize eder (altyapı-geneli
   timestamp uyumlaştırması). Yaklaşık bir debug/gözlemlenebilirlik aracı için bloke değil.
   *İlgili Dosya:* `backend/app/dashboard_service.py:29-30,49-51`, `backend/app/database.py` (`list_feedback`)

2. ~~**`feedback` `scan_cap`'te (10000) sessizce kesilir; `feedback_truncated` bayrağı
   YOK.**~~ — **ÇÖZÜLDÜ (27.11).** *(Review bulgusu #2 — Minor.)* Trace (`truncated`)
   ve timeseries (`timeseries_truncated`) eksenlerinin aksine feedback için kesme
   sinyali yoktu; bir pencere >10k feedback satırı içerirse `feedback.total` sessizce
   kapaklanıyordu. `feedback_truncated` bayrağı eklendi (27.11) — "sessiz kesme yok"
   invariant'ı artık feedback ekseninde de tutuluyor.
   *İlgili Dosya:* `backend/app/dashboard_service.py`, `backend/app/dashboard/contract.py`

3. **`scan_cap` üstü pencerelerde timeseries/metrics/top_errors tam popülasyon yerine
   çekilen alt küme üzerinden hesaplanır** (§7 ile aynı kök; dashboard 27.6'yı reuse
   ettiği için aynı sınırı devralır). `truncated=true` işaretlenir ama tam doğruluk
   DB-side aggregation ister. Zaman-serisi **zero-fill** yok (boş bucket'lar atlanır) —
   tüketici seyrek buckets'ı kendi doldurmalı. Bilinçli kapsam dışı (27.7 spec).
   *İlgili Dosya:* `backend/app/dashboard_service.py`, `backend/app/dashboard/compose.py`

4. **Küçük sağlamlık/semantik notları (Review #3–#5, hepsi Minor):** (a) debug kapalıyken
   geçersiz `bucket` 404 yerine 422 döner (param validation gate'ten önce çalışır →
   endpoint varlığını sızdırır; sibling `metrics_api` aynı in-handler desenini paylaşır
   ama kısıtlı param'ı yok) — AÇIK. (b) ~~`_floor_iso` `created_at`'in datetime olduğunu
   varsayar (`shape_recent`'teki `hasattr(...,"isoformat")` guard'ı yok) — string
   `created_at` yalnız defensive dict-record dalından gelirse `AttributeError`.~~ —
   **ÇÖZÜLDÜ (27.11).** `bucket_timeseries` artık non-datetime `created_at`'i atlıyor
   (caller guard'ı eklendi, `backend/app/llm_usage/compute.py::bucket_usage_timeseries`
   ile aynı desen); tutarsızlık kozmetikti ama guard artık kod tarafında da açık. (c)
   bucket `error_count` (terminal-status bazlı) ≠ `metrics.errors` (span-kod bazlı) —
   ikisi de doğru ama toplamları farklı; sözleşme dokümanına bir cümle notu değer — AÇIK.
   *İlgili Dosya:* `backend/app/api/dashboard_api.py`, `backend/app/dashboard/compose.py`

---

## §9. Sprint 27.8 (Cost & LLM Usage Telemetry) devirleri — AÇIK

Opus whole-branch review verdict'i **SHIP** (0 Critical, 0 bloke; 27.6 span-şekli tuzağı
YOK — extraction gerçek üreticiyle eşleşir); aşağıdakiler bilinçli ertelendi (sessiz
düşürme yok).

1. **Retry token eksik-sayımı (yapısal, en önemli).** `end_to_end` trace **tek**
   GENERATION span taşır; writer-critic retry döngüsündeki birden çok LLM çağrısından
   yalnız yakalanan (son) generation'ın token'ları payload'a iner. Retry'lı işlerde
   `total_tokens`/`estimated_cost` **eksik tahmin** edilir. Bu trace-contract'ın yapısal
   sınırı; per-attempt token yakalama ayrı bir iş (gelecek trace-contract revizyonu,
   kapsam dışı).
   *İlgili Dosya:* `backend/app/trace/end_to_end_trace_builders.py` (`build_generation_span`), `backend/app/llm_usage/compute.py` (`generation_events`)

2. **`scan_cap` üstü alt-küme + zaman-serisi zero-fill yok.** Pencere `scan_cap`'i (10000)
   aşarsa kullanım/maliyet çekilen alt küme üzerinden; `truncated=true` işaretlenir ama
   tam doğruluk DB-side aggregation ister (§7/§8 ile aynı kök). Zaman-serisi boş bucket'ları
   atlar (zero-fill yok); tüketici seyrek bucket'ları kendi doldurur. Bilinçli kapsam dışı.
   *İlgili Dosya:* `backend/app/llm_usage_service.py`, `backend/app/llm_usage/compute.py`

3. ~~**`model_id=None` olan generation üç yüzeyde tutarsız işlenir (Minor — review
   bulgusu).**~~ — **ÇÖZÜLDÜ (27.11).** Bir GENERATION span `model_id=None` taşırsa
   (provider model adını vermezse): (a) `totals.unpriced_request_count` onu sayar; (b)
   eskiden `pricing.models_missing_price` onu **listelemiyordu** (`seen_models` falsy
   `None`'ı düşürüyordu); (c) `by_model`'da `"unknown"` satırı olarak
   `estimated_cost=None` ile görünüyor. null-model generation artık `models_missing_price`'a
   `"unknown"` olarak uzlaşır (27.11) — `unpriced_request_count` (request-seviyesi) ile
   `models_missing_price` (model-seviyesi) arasındaki boşluk kapandı.
   *İlgili Dosya:* `backend/app/llm_usage/compute.py` (`compute_llm_usage` — `unpriced`/`seen_models`)

---

## §10. Sprint 27.9 (Feedback Review → Rule Suggestion) devirleri — AÇIK

Aşağıdakiler bilinçli ertelendi (sessiz düşürme yok); `GET /api/debug/rule-suggestions`
tasarım gereği yalnızca **öneri üretir**, hiçbir şey yazmaz.

1. **Onay-farkında değil / idempotency yok.** Öneri raporu `feedback`+`jobs` tablolarını
   her çağrıda yeniden tarar; bir öneri insan tarafından `POST /api/rag/index/sql-history`
   ile onaylanıp RAG'a indekslense bile, kaynak feedback satırları hâlâ pencerede olduğu
   sürece **aynı öneri tekrar görünür**. Onay/red durumu hiçbir yerde persist edilmez —
   ne `rule_suggestions` katmanında ne de feedback tablosunda. Gerçek çözüm ayrı bir
   onay-state sözleşmesi ister (kapsam dışı).
   *İlgili Dosya:* `backend/app/rule_suggestions_service.py`, `backend/app/rule_suggestions/compute.py`

2. **Yalnız literal eşleşme — semantik genelleme/synonym türetme yok.** Dedup anahtarı
   `(natural_query, suggested_sql, kind)` tam string eşitliğiyle çalışır; "İstanbul'daki
   müşteriler" ile "İstanbul'da yaşayan müşteriler" gibi anlamca eşdeğer ama harfiyen
   farklı sorgular ayrı öneri olarak kalır (support_count bölünür). LLM/embedding-tabanlı
   semantik gruplama ve synonym türetme bilinçli olarak kapsam dışı; insan RAG'a
   indekslerken bu genellemeyi elle yapar.
   *İlgili Dosya:* `backend/app/rule_suggestions/compute.py` (`compute_rule_suggestions` — dedup key)

3. **`scan_cap` üstü alt-küme.** Pencere `SCAN_CAP=10000` feedback satırını aşarsa öneri
   yalnızca çekilen alt küme üzerinden hesaplanır; `window.truncated=true` işaretlenir
   (sessiz kesme yok) ama tam doğruluk DB-side aggregation ister — 27.6/27.7/27.8 ile
   aynı yapısal kök (§7/§8/§9).
   *İlgili Dosya:* `backend/app/rule_suggestions_service.py` (`SCAN_CAP`)

4. **Confirmation önerisi `result_sql`'i okuma-anından alır.** `verdict=correct` bir
   feedback için confirmation önerisinin `suggested_sql`'i, feedback anındaki değil,
   **rapor çağrıldığı andaki** `job.result_sql`'dir (job daha sonra farklı bir SQL ile
   güncellenmişse — ör. replay/re-run — öneri o güncel değeri yansıtır, feedback verildiği
   andaki SQL'i değil). Job satırları pratikte immutable olduğundan düşük olasılıklı ama
   yapısal bir varsayım.
   *İlgili Dosya:* `backend/app/rule_suggestions/compute.py` (`classify_item` — confirmation dalı)

---

## §11. Sprint 27.10 (Per-Release Accuracy Regression Gate) devirleri — AÇIK

`evals/regression_gate_cli.py` yalnızca CLI/CI yüzeyinde çalışır; aşağıdakiler
bilinçli ertelendi (sessiz düşürme yok).

1. **Aggregate-per-case örtüşmesi.** Karşılaştırma iki katman taşır — per-case
   sıfır-tolerans (birincil) ve aggregate pass-rate (ikincil) — ama deterministik
   sahte pipeline'da per-case katman zaten sıfır-toleranslı olduğundan, aggregate
   dalının *tek başına* (per-case hiçbir şey yakalamazken) tetiklenebileceği
   senaryo yalnızca negatif/gevşetilmiş bir tolerans payı verildiğinde ortaya
   çıkar. Pratikte aggregate branch per-case'in üstüne **ek sinyal** eklemez;
   ikincil/raporlama rolünde kalır, kendi başına bağımsız bir regresyon
   kaynağı değildir. Gerçek çözüm (ör. per-case + aggregate'i farklı case
   alt-kümelerinde bağımsızlaştırmak) kapsam dışı bırakıldı.
   *İlgili Dosya:* `evals/regression_gate.py` (`compare_regression`)
2. **Gerçek accuracy değil.** Gate, deterministik sahte (fake) LLM pipeline'ı
   üzerinde çalışan golden eval raporunu tüketir — gerçek model çağrısı yok.
   Dolayısıyla yakaladığı şey **kod-kaynaklı regresyon**dur (bir refactor/PR
   golden case'leri kırdı mı?), **gerçek LLM/model doğruluğu** değil. Gerçek-LLM
   accuracy ölçümü ayrı bir eksen (subsystem C — execution harness, Sprint
   24/29.7 ailesi) ve bu sprintin kapsamı dışında.
   *İlgili Dosya:* `evals/regression_gate_cli.py`, `backend/app/eval/run_eval` (golden profil)
3. **Sürüm etiketi elle verilir.** Baseline history kaydı bir `version` etiketi
   taşır ama bu etiket git-tag'den runtime'da **okunmaz** — `--version` CLI
   bayrağıyla operatör tarafından elle sağlanır. Yanlış/eksik `--version`
   sessizce yanlış bir sürüm altında baseline kaydeder; doğrulama yok.
   *İlgili Dosya:* `evals/regression_gate_cli.py`
4. **CI'da baseline güncellemesi manuel.** `--update-baseline` bayrağı
   `evals/baselines/history.json`'a yeni bir kayıt ekler ama CI pipeline'ı bunu
   **otomatik** çağırmaz — release sırasında operatörün elle koşturması
   gerekir. Unutulursa baseline eskir ve gate giderek daha eski bir sürüme
   karşı karşılaştırma yapar (yanlış-negatif değil ama giderek anlamsızlaşan
   bir referans noktası).
   *İlgili Dosya:* `evals/regression_gate_cli.py`, `.github/workflows/backend-ci.yml`
5. **Case-düzeyi granülarite yok.** Karşılaştırma yalnızca case `id`+`passed`
   düzeyinde çalışır (`results[].id`+`.passed`); bir case'in *hangi check'i*
   (kolon/tablo/filtre/join/aggregation) regresyona uğradığı raporlanmaz —
   yalnızca case bütünüyle geçti/geçmedi bilgisi var. Check-düzeyi karşılaştırma
   (27.9'un `FeedbackCategory` ekseniyle benzer bir ayrım) kapsam dışı.
   *İlgili Dosya:* `evals/regression_gate.py` (`compare_regression`)

## §12. Sprint 28.0 (Large Schema Benchmark Suite) devirleri — KISMEN ÇÖZÜLDÜ (28.1, 28.2)

`backend/benchmarks/` yeni bir dev/CI aracıdır (`evals/`'in kardeşi); hiçbir
`app/` dosyası değişmedi, davranış korunur.

1. **✅ ÇÖZÜLDÜ (28.1) — İç patlama sayaçları eklendi.** Opsiyonel sıfır-ek-yük
   `ProfileProbe` (`backend/app/schema/profiling.py`, `probe: Optional[...] =
   None`) `find_join_paths`/`detect_implicit_relationships`/
   `select_schema_context`'e iplendi; `probe=None` iken davranış byte-for-byte
   korunur (mevcut `tests/schema` yeşil `+N/-0`). Benchmark v2 artık
   algoritmanın *iç* davranışını gösteren determinist sayaçları
   (`dfs_visit`, `adjacency_edge`, `path_recorded`, `pair_iteration`,
   `fuzzy_comparison`, `rule3_scan`, `table_scan`, `column_scan`,
   `related_expansion`) her hedefin metriklerine birleştiriyor — 2000-tablo
   ölçeğinde join-path/fuzzy-match patlamasının *neden* olduğu artık ölçülür.
   **Güncelleme (28.2):** bu sayaçlar artık yalnızca gözlem değil — 28.2
   `dfs_visit`/`adjacency_edge` sayaçlarını gerçek bir optimizasyonun
   (branch-and-bound + node-budget, bkz. madde 8) *önce/sonra* kanıtı olarak
   kullandı; profiling ile başlayan zincir gerçek bir performans iyileştirmesine
   ulaştı.
   *İlgili Dosya:* `backend/app/schema/profiling.py`, `backend/benchmarks/bench_metrics.py`, `backend/benchmarks/bench_runner.py`
2. **✅ ÇÖZÜLDÜ (28.1) — CI perf-gate kablolandı.** `.github/workflows/backend-ci.yml`'e
   yeni adım eklendi: `python -m benchmarks.bench_cli --gate --scales
   100,500,1000` — 27.10'un regresyon-gate'iyle aynı desende artık CI'da
   otomatik çalışıyor.
   *İlgili Dosya:* `backend/benchmarks/bench_cli.py`, `.github/workflows/backend-ci.yml`
3. **✅ ÇÖZÜLDÜ (28.1) — NetworkX/graph-backend benchmark hedefi eklendi.**
   Yeni **5. hedef** `graph_backend`: `NetworkXGraphBackend`'i (build +
   pagerank + shortest_path) `to_legacy_dict` reuse'iyle egzersiz eder —
   çıktı-türevli tam-sayı metrikler (`graph_nodes`/`graph_edges`/`sp_*`) +
   `wall_ms`; pagerank float bilinçli olarak **gate'lenmez** (bkz. madde 6).
   Not: bu, `app/schema_graph/`'daki graph pruning/hub detection katmanının
   *tamamının* değil, `NetworkXGraphBackend` adaptörünün benchmark'ıdır —
   `GraphPruner` candidate/policy derin entegrasyonu hâlâ AÇIK (madde 5).
   *İlgili Dosya:* `backend/benchmarks/bench_metrics.py` (`derive_graph_backend_metrics`), `backend/benchmarks/bench_runner.py`
4. **AÇIK — Embedding/RAG retrieval benchmark'ı yok.** Büyük şemalarda embedding
   pipeline'ının (top-k retrieval, context ranking) ölçeklenebilirliği hâlâ
   kapsam dışı — Sprint 28.8 (Embedding / RAG Re-Index Pipeline) için ayrılmış.
   *İlgili Dosya:* `backend/app/retrieval/`
5. **AÇIK — `GraphPruner` candidate/policy derin entegrasyonu + pruner iç
   probe'u yok.** 28.1'in `graph_backend` hedefi yalnızca
   `NetworkXGraphBackend`'in build/pagerank/shortest_path işlemlerini ölçer;
   `app/schema_graph/`'daki pruning candidate seçimi ve policy katmanı
   (hub detection, candidate scoring) ayrı bir benchmark hedefi veya
   `ProfileProbe` entegrasyonu olarak henüz kapsanmıyor.
   *İlgili Dosya:* `backend/app/schema_graph/`, `backend/benchmarks/bench_metrics.py`
6. **AÇIK (yeni, 28.1) — `scipy` kurulu değil, `personalized_pagerank`
   sessizce `{}`'e düşüyor.** `NetworkXGraphBackend.personalized_pagerank`
   NetworkX'in `pagerank` çağrısı `scipy` gerektirdiğinde `Exception`'ı
   yakalayıp `{}` döner (`app/schema_graph/networkx_backend.py`); bu yüzden
   `graph_backend` hedefinin pagerank kısmı gerçek iş yapmadan CI log
   gürültüsü üretiyor. Gate etkilenmiyor (pagerank float hiçbir zaman
   gate'lenmez, madde 3), ama gerçek pagerank profillemesi ve log
   temizliği için `scipy`'nin `requirements.txt`'e eklenmesi düşünülebilir.
   *İlgili Dosya:* `backend/app/schema_graph/networkx_backend.py`, `backend/requirements.txt`
7. **AÇIK (kozmetik, yeni, 28.1) — stale docstring/help metinleri.**
   `backend/benchmarks/bench_contract.py` docstring/yorumları hâlâ "4-way
   hedef" diyor ve `scale: 2000`'i bahsediyor; `backend/benchmarks/bench_cli.py`
   `--scales` yardım metni örneği hâlâ `100,500,1000,2000` gösteriyor — v2'nin
   5. hedefi (`graph_backend`) ve gate'lenen 3-ölçek (100/500/1000) ile
   senkron değil. Davranışı etkilemiyor, doc-sync borcu.
   *İlgili Dosya:* `backend/benchmarks/bench_contract.py`, `backend/benchmarks/bench_cli.py`
8. **✅ ÇÖZÜLDÜ (28.2) — `find_join_paths` kombinatoryal DFS patlaması iki
   katmanla sınırlandı.** Ters-BFS `hop` mesafelerinden admissible bir derinlik
   sınırı (`_hop_distances`) + kept-set dominance pruning (çıktı-koruyan
   branch-and-bound, brute-force denklik testiyle guard'lı) artı determinist
   `node_budget` güvenlik kemeri (`DEFAULT_JOIN_PATH_NODE_BUDGET = 200_000`,
   taşmada `budget_truncated=True`). Yeni `JoinPathSearchResult` sözleşmesi
   (13 çağrı noktası `.paths`'e taşındı); `select_schema_context` yeni
   `join_search_truncated` alanı kazandı (non-breaking, defaultlu). Benchmark
   v3 join_paths hedefinde `dfs_visit`/`adjacency_edge`'de büyük düşüş
   ölçtü, çıktı-türevli metrikler değişmedi (çıktı korumasının kanıtı).
   *İlgili Dosya:* `backend/app/schema/graph_traversal.py`, `backend/app/schema/schema_context_selector.py`
9. **AÇIK (28.2 bilinçli kapsam dışı) — ağırlıklı/maliyet-tabanlı path
   scoring + hub-penalty yok.** 28.2 yalnızca DFS *enumerasyonunu* sınırladı
   (hangi path'ler ziyaret edilir), path'lerin nasıl *skorlandığını/sıralandığını*
   değiştirmedi. `graph_traversal.py`'nin başındaki "Hub-table penalty is
   intentionally out of scope... Future work: penalize high-degree tables
   during path scoring" yorumu hâlâ AÇIK.
   *İlgili Dosya:* `backend/app/schema/graph_traversal.py:7-8`
10. **AÇIK (devam, 28.1'den) — `GraphPruner` candidate/policy derin
    entegrasyonu hâlâ yok.** Madde 5 ile aynı kalem; 28.2 yalnızca
    `find_join_paths`'i kapsadı, `app/schema_graph/`'daki pruning
    candidate seçimi ve policy katmanı (hub detection, candidate scoring)
    ayrı bir benchmark hedefi veya `ProfileProbe` entegrasyonu olarak henüz
    kapsanmıyor.
    *İlgili Dosya:* `backend/app/schema_graph/`
11. **AÇIK (28.2 bilinçli kapsam dışı) — empirik/adaptif budget tuning
    yok.** `DEFAULT_JOIN_PATH_NODE_BUDGET = 200_000` sabit, elle seçilmiş bir
    değer (scale-1000 ölçümünde gözlenen 2653 ziyaretin çok üzerinde,
    gated ölçeklerde asla tetiklenmeyecek kadar cömert); şema büyüklüğüne
    göre empirik/adaptif bir budget hesaplaması (ör. tablo sayısına göre
    ölçeklenen bir formül) kapsam dışı bırakıldı.
    *İlgili Dosya:* `backend/app/schema/graph_traversal.py`
12. **AÇIK (devam) — frontend `maxNodesLimit` kalıcı çözümü yok.** Bkz. §2
    (D3 Graph UI Performans Limiti) — ara fix uygulandı ama kalıcı çözüm
    (progressive/virtualized rendering, WebGL) hâlâ Phase 12 (31.x UI/UX
    Production Layer)'e ertelenmiş durumda; 28.2 backend-only bir sprint
    olduğu için bu kalemi kapsamadı.
    *İlgili Dosya:* `frontend/src/components/SchemaManager.vue`, `frontend/src/utils/graphSelection.ts`
