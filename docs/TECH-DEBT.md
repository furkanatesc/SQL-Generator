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
3. ~~**`live_trace_assembly` güvenlik span'ini STAGE adına göre kuruyor.**~~ —
   **✅ ÇÖZÜLDÜ (28.3.1).** Canlı SECURITY span'inin `outcome`'ı artık 27.2
   error registry'sinden türetiliyor: yeni `_security_outcome(reason_code)`
   helper'ı kodun `ErrorCategory.SECURITY` kategorisinde olup olmadığına bakar
   — kategori SECURITY ise `outcome="denied"`/`severity="error"`, değilse
   (ör. `sql_parse_error` gibi validation kategorisi bir stage'de yakalanmış
   kod) `outcome="flagged"`/`severity="warning"`. `_SECURITY_STAGES` seti
   (hangi stage'lerin security span'e girdiğini belirleyen) DEĞİŞMEDİ —
   yalnızca outcome artık kategoriye göre kuruluyor; pinning testi yeşil.
   Ayrıca kayıtlı olmayan sahte bir hata koduna dayanan 2 pre-existing test
   düzeltildi (registry'de gerçekten var olan kodlarla değiştirildi).
   *İlgili Dosya:* `backend/app/trace/live_trace_assembly.py` (`_security_outcome`)
4. **Fail olmuş job'ların üretilen SQL'i saklanmıyor** → replay'in
   `validation_recovery` verdict'i bugünkü veri modelinde **ulaşılamaz**, ve
   `security_regression` yalnız başarılı job'larda ölçülebilir. `jobs.result_sql`
   yalnız `"completed"` durumunda yazılıyor. Taksonomi üyesi sözleşme tamlığı için
   korunuyor; gerçek çözüm ayrı bir kalem (bkz. 27.4 spec §8).

---

## §6. Sprint 27.5 (Debug Bundle Export) devirleri — AÇIK

1. ~~**`_latest_debug_trace` `trace_type` filtresi olmadan `limit=5` kullanıyor.**~~ —
   **✅ ÇÖZÜLDÜ (28.3.1).** `_latest_debug_trace` artık `TraceQuery(trace_type=
   DEBUG_TRACE_TYPE, job_id=job_id, limit=1)` ile doğrudan debug trace türünü
   filtreliyor — "en yeni 5 kaydı çekip aralarında ara" penceresi kalktı;
   `end_to_end` trace sayısı 5'i geçse bile asıl debug trace artık kaçmıyor,
   bundle'ın `sql` bölümü `null` dönmüyor.
   *İlgili Dosya:* `backend/app/bundle_service.py` (`_latest_debug_trace`)
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

1. ~~**`feedback` bölümü ile trace bölümleri (`metrics`/`timeseries`/`recent`) aynı
   istekte FARKLI zaman penceresi yansıtabilir (naive-timestamp sınırlarında).**~~ —
   **✅ ÇÖZÜLDÜ (28.3.1).** `database.list_feedback` artık gelen
   `created_after`/`created_before` sınırını `_normalize_feedback_boundary` ile
   naive-UTC'ye normalize ediyor (offset-aware bir ISO damgası gelirse
   `astimezone(utc)` + offset düşürülür) — trace tarafının zaten naive-UTC
   sakladığı `feedback.created_at` ile artık tutarlı karşılaştırılıyor;
   offset'li ve naive sınır case'leri ayrı testlerle kilitli, mevcut
   naive-sınır testleri değişmedi.
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

4. **Küçük sağlamlık/semantik notları (Review #3–#5, hepsi Minor):** (a) ~~debug kapalıyken
   geçersiz `bucket` 404 yerine 422 döner (param validation gate'ten önce çalışır →
   endpoint varlığını sızdırır; sibling `metrics_api` aynı in-handler desenini paylaşır
   ama kısıtlı param'ı yok)~~ — **ÇÖZÜLDÜ (28.3.1).** Debug gate route-level
   `Depends(ensure_debug_enabled)` olarak taşındı (in-body çağrı kaldırıldı) →
   FastAPI dependency'leri param validation'dan önce çözdüğü için debug kapalıyken
   geçersiz `bucket` artık 404 (endpoint varlığı sızmıyor); debug açıkken 422
   (validation hâlâ çalışıyor). OpenAPI şeması değişmedi (`bucket` hâlâ
   `Literal["hour","day"]`). (b) ~~`_floor_iso` `created_at`'in datetime olduğunu
   varsayar (`shape_recent`'teki `hasattr(...,"isoformat")` guard'ı yok) — string
   `created_at` yalnız defensive dict-record dalından gelirse `AttributeError`.~~ —
   **ÇÖZÜLDÜ (27.11).** `bucket_timeseries` artık non-datetime `created_at`'i atlıyor
   (caller guard'ı eklendi, `backend/app/llm_usage/compute.py::bucket_usage_timeseries`
   ile aynı desen); tutarsızlık kozmetikti ama guard artık kod tarafında da açık. (c)
   ~~bucket `error_count` (terminal-status bazlı) ≠ `metrics.errors` (span-kod bazlı) —
   ikisi de doğru ama toplamları farklı; sözleşme dokümanına bir cümle notu değer.~~ —
   **ÇÖZÜLDÜ (28.3.1).** `backend/app/dashboard/contract.py::TimeseriesBucket`
   docstring'ine bir cümle not eklendi.
   *İlgili Dosya:* `backend/app/api/dashboard_api.py`, `backend/app/dashboard/compose.py`,
   `backend/app/dashboard/contract.py`

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
   bayrağıyla operatör tarafından elle sağlanır. ~~Yanlış/eksik `--version`
   sessizce yanlış bir sürüm altında baseline kaydeder; doğrulama yok.~~ —
   **✅ ÇÖZÜLDÜ (28.3.1, kısmen)** — doğrulama eksikliği kapandı: `--version`
   artık `_VERSION_RE = ^v?\d+\.\d+(\.\d+)?$` deseniyle doğrulanıyor; uyumsuz
   bir değer baseline'a hiç yazılmadan `exit 2` ile reddediliyor. Git-tag'den
   **otomatik** okuma (elle sağlama zorunluluğunun kendisi) hâlâ AÇIK —
   operatör hâlâ doğru sürümü elle girmek zorunda, yalnızca *format* hatası
   artık yakalanıyor.
   *İlgili Dosya:* `backend/evals/regression_gate_cli.py` (`_VERSION_RE`, `_run_update`)
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

## §12. Sprint 28.0 (Large Schema Benchmark Suite) devirleri — KISMEN ÇÖZÜLDÜ (28.1, 28.2, 28.3.1, 28.4); 28.3 genişletti (yeni madde 13-17)

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
6. ~~**AÇIK (yeni, 28.1) — `scipy` kurulu değil, `personalized_pagerank`
   sessizce `{}`'e düşüyor.**~~ — **✅ ÇÖZÜLDÜ (28.3.1, kısmen).**
   `personalized_pagerank` artık `scipy` eksikliğini `(ImportError,
   ModuleNotFoundError)` olarak ayrı yakalayıp DEBUG seviyesinde logluyor
   ("PPR skipped (optional scipy backend unavailable)") — beklenmeyen diğer
   hatalar hâlâ `logger.error` ile ayrı ele alınıyor; CI log gürültüsü kapandı.
   `scipy` bağımlılığı **eklenmedi** (bilinçli) — gerçek pagerank profillemesi
   hâlâ AÇIK, yalnızca eksiklik artık sessizce/gürültüyle değil temiz şekilde
   ele alınıyor.
   *İlgili Dosya:* `backend/app/schema_graph/networkx_backend.py` (`personalized_pagerank`)
7. ~~**AÇIK (kozmetik, yeni, 28.1) — stale docstring/help metinleri.**~~ —
   **✅ ÇÖZÜLDÜ (28.3.1) — VERIFY-CLOSE, kod değişikliği yok.** Bu kalem kod
   olarak zaten 28.1/28.2/28.3 düzeltme dalgalarında aşamalı olarak
   çözülmüştü: `bench_contract.py` docstring'i "Sprint 28.3" diyor ve 5
   hedefin tamamını (`graph_backend` dahil) listeliyor, "4-way"/`scale: 2000`
   metni yok; `bench_cli.py`'nin `--scales` yardım metni `100,500,1000`
   gösteriyor. Bu madde yalnızca doğrulayıp RESOLVED olarak işaretlemek için
   açık bırakılmıştı (28.3.1 Task 7 verify-close).
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
    olduğu için bu kalemi kapsamadı. **28.3 de kapsamadı** (config-driven
    cost model + benefit-density seçim backend-only kaldı) — kalem hâlâ
    Phase 12'ye ait.
    *İlgili Dosya:* `frontend/src/components/SchemaManager.vue`, `frontend/src/utils/graphSelection.ts`
13. ~~**AÇIK (28.3 bilinçli kapsam dışı) — ilişki-güven-ağırlıklı komşu
    benefit'i yok.**~~ — **✅ ÇÖZÜLDÜ (28.4).** `TableSelectionCostModel`'deki
    düz `explicit_neighbor`/`implicit_neighbor` (20.0/10.0) ağırlıkları tek bir
    `neighbor_base: float = 20.0` ile birleştirildi; komşu benefit'i artık
    `neighbor_base × effective_confidence`'tir (explicit/custom ilişki
    `confidence=None` → 1.0, implicit ilişki 0.60–0.90 aralığında ölçülü
    güven). `IMPLICIT_FUZZY` komşular yeni `include_fuzzy_neighbors: bool =
    False` ile opt-in (varsayılan kapalı). Muhafazakâr `neighbor_base=20.0`
    seçimi mevcut fixture'larda davranışı korudu (golden şemanın 6 kenarı
    hepsi explicit conf=None → `20×1.0=20` = eski `explicit_neighbor`);
    golden eval yeşil, fixture kürasyonu gerekmedi; benchmark v4 baseline'ı
    byte-identical kaldı (versiyon bump gerekmedi — sentetik şema yalnız
    explicit FK içeriyor).
    *İlgili Dosya:* `backend/app/schema/table_selection_cost.py`, `backend/app/schema/schema_context_selector.py`
14. **AÇIK (28.3 bilinçli kapsam dışı) — token-tabanlı gerçek maliyet yok.**
    `table_cost() = w_base + w_col*n_columns + w_fk*n_fks` kolon/FK
    **sayısını** bir proxy olarak kullanır; tablonun prompt'a serialize
    edildiğinde gerçekte kaç token tuttuğunu (kolon adı uzunluğu, tip
    bilgisi, açıklama metni vb.) ölçmez. Token-tabanlı gerçek maliyet
    fonksiyonu kapsam dışı bırakıldı.
    *İlgili Dosya:* `backend/app/schema/table_selection_cost.py` (`table_cost`)
15. **AÇIK (28.3 bilinçli kapsam dışı) — gerçek 0/1-knapsack optimalliği
    yok.** Seçim algoritması benefit-density (`benefit/cost`) sıralı
    **deterministik greedy**'dir (skip-and-continue); bu, klasik 0/1-knapsack
    probleminin optimal çözümünü GARANTİ ETMEZ (greedy yaklaşım bazı
    girdilerde optimalden sapabilir). Gerçek knapsack optimalliği (ör.
    dynamic programming) kapsam dışı bırakıldı — determinizm ve performans
    tercih edildi.
    *İlgili Dosya:* `backend/app/schema/schema_context_selector.py`
16. ~~**AÇIK (yeni, 28.3, minor) — fallback yolu `cost_budget`'a gate
    edilmiyor.**~~ — **✅ ÇÖZÜLDÜ (28.3.1).** Fallback rejimi artık
    `budget_exhausted=False` set ediyor (fallback bir bütçe-dalı değil,
    bounded bir güvenlik ağıdır — bkz. `schema_context_selector.py` satır
    ~171-174 yorumu); önceki çelişkili `budget_exhausted=True` +
    `fallback_used=True` kombinasyonu artık üretilmiyor. Fallback davranışının
    kendisi (en fazla `max_fallback_tables=5` tablo, `cost_budget` kontrolü
    olmadan ekleme) DEĞİŞMEDİ — yalnızca debug metadata'sındaki bayrak
    çelişkisi kapandı, güvenlik ağı korundu.
    *İlgili Dosya:* `backend/app/schema/schema_context_selector.py`
17. ~~**AÇIK (yeni, 28.3, minor) — pipeline wiring testi yalnızca parse
    sözleşmesini kilitliyor, uçtan-uca enjeksiyonu değil.**~~ —
    **✅ ÇÖZÜLDÜ (28.3.1).** Yeni bir uçtan-uca test
    (`test_wiring_end_to_end_config_override_changes_selection`) `configs`
    üzerinden verilen bir `table_selection_cost_model` override'ının gerçek
    bir pipeline çalıştırmasında seçim sonucunu **fiilen değiştirdiğini**
    kanıtlıyor — önceki test yalnızca `from_config`/parse çağrısını
    doğruluyordu, bu boşluk kapandı.
    *İlgili Dosya:* `backend/app/sql_pipeline.py`, `backend/tests/schema/test_cost_model_pipeline_wiring.py`

## §13. Sprint 28.5 (Missing Foreign Key Inference v2) devirleri — AÇIK

`detect_implicit_relationships` artık PK-aware (yeni saf `resolve_target_key(table)`
yardımcısı); aşağıdakiler tasarım spec'inde (§7) bilinçli olarak kapsam dışı
bırakıldı (sessiz düşürme yok).

1. **Type-uyumluluk sinyali/gate yok.** Kaynak kolonun veri tipi hedef PK'nin
   tipiyle karşılaştırılmıyor — bir `customer_id INTEGER` kaynak kolonu,
   hedefteki PK `TEXT` olsa bile salt isim/PK-anahtar eşleşmesiyle FK adayı
   sayılabilir. Tip-uyumluluk kontrolü ayrı bir precision katmanı olarak
   kapsam dışı bırakıldı.
   *İlgili Dosya:* `backend/app/schema/implicit_relationships.py` (`resolve_target_key`, Rule 1-3)
2. **Config-driven eşikler yok.** Confidence değerleri (0.90/0.75/0.65/0.60),
   fuzzy-ratio eşiği (`0.85`/`0.90`) ve generic-kolon listesi hâlâ kod içinde
   hardcoded — 27.8/28.3 `from_config()` desenindeki gibi bir config yüzeyi
   yok.
   *İlgili Dosya:* `backend/app/schema/implicit_relationships.py`
3. **Unique-ama-PK-olmayan hedefler tanınmıyor.** `resolve_target_key` yalnız
   deklare edilmiş PK'yi (veya PK yoksa `id`/`<singular>_id` konvansiyonunu)
   hedef anahtar sayar; `UNIQUE` kısıtlı ama PK olmayan bir kolona işaret eden
   gerçek bir FK ilişkisi hâlâ yakalanmaz (PK-only tasarım kararı, Q2).
   *İlgili Dosya:* `backend/app/schema/implicit_relationships.py` (`resolve_target_key`)
4. **Composite-PK hedefli FK çıkarımı yok.** `resolve_target_key` composite PK
   (2+ deklare edilmiş PK kolonu) taşıyan bir tabloda `None` döner —
   yalnız tek-kolonlu PK'lere odaklanılır; çok-kolonlu FK çıkarımı kapsam
   dışı bırakıldı.
   *İlgili Dosya:* `backend/app/schema/implicit_relationships.py` (`resolve_target_key`)
5. **Veri örneklemesi / value-overlap / cardinality yok.** Çıkarım tamamen
   schema-only kalır (kolon adı + deklare edilmiş PK metadata'sı); gerçek
   satır verisi üzerinde value-overlap veya cardinality analizi (ör. kaynak
   kolon değerlerinin hedef PK değer kümesine ne oranda düştüğü) bilinçli
   olarak kapsam dışı bırakıldı.
   *İlgili Dosya:* `backend/app/schema/implicit_relationships.py`

## §14. Sprint 28.6 (Schema Cache Invalidation) devirleri — KISMEN ÇÖZÜLDÜ (28.7, 28.8)

`SchemaManager.load_schema` artık içerik-fingerprint'li (yeni saf
`app/schema_cache_fingerprint.py`: `compute_cache_fingerprint(*, db_type,
hidden_tables_raw, hidden_columns_raw, embedding_model, cache_version=
SCHEMA_CACHE_VERSION)` → sha256); aşağıdakiler tasarım spec'inde bilinçli
olarak kapsam dışı bırakıldı (sessiz düşürme yok).

1. ~~**Ham DB şema drift'i (tablo/kolon değişikliği) yakalanmıyor.**
   Fingerprint self-contained'dır (yalnız `db_type` + hidden-tables/columns
   config'i + embedding model'i özetler); veritabanında bir tablo/kolon
   eklenip/kaldırılırsa/tipi değişirse cache bunu göremez — yeni bir DB
   sorgusu gerekir.~~ — **✅ ÇÖZÜLDÜ (28.7).** Yeni saf
   `app/schema/schema_signature.py`: `normalize_structure` (dialect-agnostic,
   sıra-bağımsız kanonik yapı) + `compute_schema_signature` (sha256) +
   `diff_structures` → `StructuralDrift`. `SchemaManager._current_schema_signature()`
   `extract_schema_metadata()`'yı yeniden çalıştırıp taze bir signature üretir
   (ultra-ucuz ayrı bir DB fingerprint sorgusu **değil** — extract-reuse
   tercih edildi, bkz. §15.4); cache payload'ı artık `schema_signature`
   taşıyor. `load_schema`'da **opt-in** kontrol (`auto_schema_drift_check`
   config, varsayılan KAPALI — 28.6 davranışı korunur); açıldığında
   uyuşmazlıkta tam yeniden çıkarım tetiklenir.
   *İlgili Dosya:* `backend/app/schema/schema_signature.py`, `backend/app/schema_manager.py` (`load_schema`, `_current_schema_signature`)
2. **AÇIK — TTL/zaman-tabanlı invalidation yok.** Cache yalnızca fingerprint/
   signature uyuşmazlığında veya `force_refresh=True` ile yenilenir; belirli
   bir süre sonra otomatik "bayatla" mekanizması (ör. `cache_ttl_seconds`)
   kapsam dışı bırakıldı. 28.7 de kapsamadı.
   *İlgili Dosya:* `backend/app/schema_manager.py` (`load_schema`)
3. ~~**Explicit invalidation endpoint/event yok.** Cache'i manuel/programatik
   olarak temizleyen bir debug endpoint'i veya olay-tabanlı tetikleyici
   eklenmedi; tek yol hâlâ `force_refresh=True` parametresi veya cache
   dosyasının silinmesi.~~ — **✅ ÇÖZÜLDÜ (28.7).** Yeni debug-gated router
   `app/api/schema_sync_api.py`: yan-etkisiz `GET /api/debug/schema/drift`
   (cache okur + taze signature hesaplar, rebuild YOK) ve drift-aware
   `POST /api/debug/schema/sync?force=` (yalnız `drifted` veya `force=true`
   ise `load_schema(force_refresh=True)` çağırır). Rebuild hâlâ tüm-cache'dir
   (kısmi/seçici değil, bkz. §15.6).
   *İlgili Dosya:* `backend/app/api/schema_sync_api.py`
4. ~~**AÇIK — Granüler embedding-only invalidation yok.** Embedding model
   değişince (veya herhangi bir fingerprint girdisi değişince) tüm cache
   (`schema` + `embeddings`) yeniden yazılıyor; yalnızca embedding kısmını
   yeniden hesaplayıp şema kısmını koruyan daha ince taneli bir yol kapsam
   dışı bırakıldı.~~ — **✅ ÇÖZÜLDÜ (28.8).** Yeni saf `app/schema/
   reindex_planner.py` (`plan_reindex` → `to_embed`/`to_keep`/`to_delete`) +
   `app/schema_reindex.py::reindex_embeddings` yalnız yeni/değişen tabloları
   embed eder, değişmeyenlerin vektörünü reuse eder. `load_schema`'nın
   rebuild dalı artık bu granüler yolu kullanıyor; `force_refresh=True` hâlâ
   tam yeniden-embed yapar (bilinçli — bkz. §16). Ayrıca `POST /api/debug/
   schema/reindex` embedding-model değişikliğinde **DB re-extract'e hiç
   dokunmadan** yalnız embedding'i güncelleyen elle-tetiklenen bir kısa yol
   sağlıyor (otomatik kısa-devre değil — bkz. §16 madde 2).
   *İlgili Dosya:* `backend/app/schema/reindex_planner.py`, `backend/app/schema_reindex.py`, `backend/app/schema_manager.py` (`load_schema`)

## §15. Sprint 28.7 (Incremental Schema Sync) devirleri — KISMEN ÇÖZÜLDÜ (28.8)

`app/schema/schema_signature.py` (saf, sha256 tabanlı yapısal signature) +
`SchemaManager`'ın opt-in `auto_schema_drift_check`'i (varsayılan KAPALI) +
debug-gated `GET /api/debug/schema/drift` / `POST /api/debug/schema/sync`
§14.1 ve §14.3'ü çözdü; aşağıdakiler tasarım spec'inde bilinçli olarak
kapsam dışı bırakıldı (sessiz düşürme yok).

1. **True per-table incremental re-extract/merge yok.** Drift tespit
   edildiğinde (opt-in kontrol veya `POST /sync`) hâlâ **tam** şema yeniden
   çıkarımı (`extract_schema_metadata()`) tetiklenir; yalnızca değişen
   tablo(lar)ı tespit edip cache'teki değişmeyen tabloları koruyarak
   birleştiren (merge) daha ince taneli bir yol kapsam dışı bırakıldı.
   *İlgili Dosya:* `backend/app/schema_manager.py` (`load_schema`)
2. ~~**Granüler embedding-only re-index yok (→ 28.8).** Drift'te tüm cache
   (`schema` + `embeddings`) yeniden yazılıyor; yalnızca embedding kısmını
   yeniden hesaplayıp şema kısmını koruyan bir yol hâlâ kapsam dışı — bu
   §14.4'ün devamıdır, 28.8 Embedding/RAG Re-Index Pipeline'a ertelendi.~~ —
   **✅ ÇÖZÜLDÜ (28.8).** Bkz. §14 madde 4 ve §16. `load_schema`'nın rebuild
   dalı artık `reindex_embeddings` ile yalnız yeni/değişen tabloları embed
   eder; drift'te `schema` yine tam yeniden çıkarılır (§15 madde 1 ile aynı
   yapısal sınır — bu 28.8'in kapsamı dışı, yalnız embedding tarafı kapandı),
   ama `embeddings` artık granüler güncellenir.
   *İlgili Dosya:* `backend/app/schema_manager.py` (`load_schema`), `backend/app/schema_reindex.py`
3. **TTL/zaman-tabanlı invalidation hâlâ yok (§14.2 devam ediyor).** 28.7
   yalnızca yapısal drift kontrolü ekledi; belirli bir süre sonra otomatik
   "bayatla" mekanizması kapsam dışı kaldı.
   *İlgili Dosya:* `backend/app/schema_manager.py` (`load_schema`)
4. **Ultra-ucuz tek-sorgulu DB-taraflı drift sinyali kullanılmadı.**
   `_current_schema_signature()` taze bir signature üretmek için tam
   `extract_schema_metadata()`'yı yeniden çalıştırır (extract-reuse); hafif
   per-dialect bir DB-side sinyal (ör. `information_schema`/`sqlite_master`
   üzerinde tablo/kolon sayımı veya DDL-versiyon/`updated_at` benzeri ucuz
   bir sorgu) bilinçli olarak tercih edilmedi — extract zaten mevcut ve
   deterministik olduğu için basitlik/tutarlılık tercih edildi; büyük
   şemalarda (2000+ tablo) `GET /drift`'in her çağrısı tam extract maliyeti
   taşır.
   *İlgili Dosya:* `backend/app/schema/schema_signature.py`, `backend/app/schema_manager.py`
5. **Yalnızca yapısal drift; satır/veri-seviyesi drift yok.**
   `normalize_structure`/`compute_schema_signature` yalnız tablo/kolon/FK
   metadata'sını (isim, tip, PK, nullable, referans) özetler; satır sayısı,
   veri dağılımı, cardinality veya değer-seviyesi değişiklikler drift olarak
   sayılmaz (schema-only tasarım kararı, 28.5'in `implicit_relationships`
   kapsam dışılarıyla tutarlı).
   *İlgili Dosya:* `backend/app/schema/schema_signature.py`
6. **`POST /sync` rebuild'i tüm-cache'dir, kısmi/seçici değil.** Drift
   tespit edilince `SchemaManager().load_schema(force_refresh=True)`
   çağrılır — bu, madde 1'deki "true incremental" eksikliğinin endpoint
   yüzeyindeki yansımasıdır; yalnızca drift'e uğrayan tabloları hedefleyen
   seçici bir sync kapsam dışı bırakıldı.
   *İlgili Dosya:* `backend/app/api/schema_sync_api.py` (`schema_sync`)

## §16. Sprint 28.8 (Embedding / RAG Re-Index Pipeline) devirleri — AÇIK

`app/schema/reindex_planner.py` (saf: `build_table_embedding_text`/
`compute_embedding_fingerprint`/`stable_point_id`/`plan_reindex`) +
`app/schema_reindex.py::reindex_embeddings` + `rag_manager.py`'nin
deterministik point id'leri + `GET /reindex-status`/`POST /reindex`
§14.4 ve §15.2'yi çözdü; aşağıdakiler tasarım spec'inde bilinçli olarak
kapsam dışı bırakıldı (sessiz düşürme yok).

1. **`business_rules`/`sql_history` koleksiyonları hâlâ non-deterministic
   `hash()` point id kullanıyor; granüler re-index yok.** 28.8 yalnızca
   `schema_ddl` koleksiyonunu (ve onu besleyen `index_ddl`/
   `index_schema_batch`'i) `stable_point_id`'ye taşıdı.
   `index_business_rule`/`index_sql_history` (`rag_manager.py`) hâlâ eski
   `hash(...) % 10**8` desenini kullanıyor — aynı restart-bağımlı
   orphan/duplicate-point riski bu iki koleksiyonda **devam ediyor**;
   granüler embed-only re-index de yalnız `schema_ddl` için var, bu iki
   koleksiyon için bir `reindex_embeddings` eşdeğeri yok. Bilinçli kapsam
   dışı — kapsam `schema_ddl` ile sınırlandı (28.8 spec).
   *İlgili Dosya:* `backend/app/rag_manager.py` (`index_business_rule`, `index_sql_history`)
2. **Embedding-model değişikliğinde otomatik embedding-only kısa-devre
   yok.** 28.6'nın `compute_cache_fingerprint` girdileri arasında
   `embedding_model` var; model değişince fingerprint uyuşmazlığı `load_schema`
   içinde hâlâ **TAM** `base_schema is None` dalını tetikler (DB'den yeniden
   `extract_schema_metadata()` — 28.8 bunu granüler embedding re-index'e
   bağladı ama `extract` adımının kendisini atlamıyor). Yalnızca elle
   çağrılan `POST /api/debug/schema/reindex` DB re-extract'e hiç dokunmadan
   embedding-only kısa yolu sağlıyor — otomatik/algılanan bir kısa-devre
   (ör. "yalnız `embedding_model` değiştiyse `extract`'i atla") kapsam dışı
   bırakıldı.
   *İlgili Dosya:* `backend/app/schema_manager.py` (`load_schema`), `backend/app/api/schema_sync_api.py` (`reindex`)
3. **Qdrant collection/vector_size migration kapsam dışı.** `stable_point_id`
   yalnızca point id üretim şemasını değiştirdi; koleksiyonun kendisinin
   (`schema_ddl`, sabit `vector_size`) yeniden boyutlandırılması/migrate
   edilmesi bir senaryo olarak ele alınmadı — embedding modeli vektör
   boyutunu değiştirirse (bkz. TECH-DEBT §1) ayrı bir migration adımı
   gerekir, 28.8 bunu üstlenmedi.
   *İlgili Dosya:* `backend/app/rag_manager.py`
4. **Embed-text zenginleştirme (örnek değerler) kapsam dışı.**
   `build_table_embedding_text` yalnız tablo adı + kolon adı/tipi + FK
   referanslarını birleştirir (schema-only); düşük-kardinaliteli kolonların
   örnek/distinct değerlerini (bkz. ROADMAP "Değer Düzeyi Semantik RAG"
   backlog fikri) embed metnine katma bilinçli olarak kapsam dışı bırakıldı.
   *İlgili Dosya:* `backend/app/schema/reindex_planner.py` (`build_table_embedding_text`)
5. **Batch-size tuning değişmedi.** `reindex_embeddings`, `embedder.
   build_index`'i yalnız `to_embed`+eksik-vektörlü `to_keep` tablolarının
   alt-şeması üzerinde çağırır (istek sayısı azalır) ama `build_index`'in
   kendi iç batching/rate-limit davranışı (NVIDIA NIM embedding API'sine
   kaç tablo/istek gönderildiği) dokunulmadı — 28.8 yalnız *hangi* tabloların
   embed edildiğini daralttı, *nasıl* embed edildiğini değiştirmedi.
   *İlgili Dosya:* `backend/app/schema_embedding.py` (`build_index`)
6. **NARROWED (final-review fix, 28.8 sonrası) — `force=True` + eşzamanlı
   tablo kaldırma, o zorlanmış rebuild'in kendi `reindex_embeddings` çağrısında
   kaldırılan tablonun Qdrant point'ini tahliye ETMEZ; artık aynı rebuild'in
   sonunda prune ile temizleniyor.** `SchemaManager.load_schema`'da `force_refresh=
   True` iken cache-okuma bloğu (`if not force_refresh and os.path.exists(...)`)
   tamamen atlanır, dolayısıyla `old_embeddings_for_reindex` hep `None`
   kalır; `reindex_embeddings` bu durumda `force=True` ile çağrılır ve
   `old_fp={}`/`old_tables={}` ile başlar → `plan_reindex`'in `to_delete`'i
   (eski fingerprint kümesi ile yeni tablo kümesinin farkı) hep **boş**
   çıkar — kaldırılan bir tablo varsa bile, o çağrının kendisi eski point'i
   silmez. **Düzeltme (final-review fix wave):** aynı rebuild bloğunda
   `reindex_embeddings` çağrısından hemen sonra, aynı `_rag` (`RAGManager`)
   örneğiyle `_rag.prune_schema_ddl_points(set(base_schema["tables"].keys()))`
   çağrılıyor — bu, taze (re-)build edilmiş şemadaki tablo kümesine göre
   `schema_ddl` koleksiyonunu tarayıp hem orphan (artık var olmayan tablo)
   hem de stale-id (28.8 öncesi `hash()` tabanlı) point'leri temizler. Not:
   ~~"bir sonraki **force-olmayan** `load_schema` çağrısı drift'i `to_delete`'e
   yakalar" iddiası YANLIŞTI~~ — force rebuild sonrası kaldırılan tablo
   `fingerprints`'te hiç yer almadığı için hiçbir sonraki `plan_reindex`
   onu `to_delete`'e koymaz; bu path'e güvenilemezdi. Gerçek iyileşme yolları
   yalnızca: (a) yukarıdaki prune-on-rebuild (her rebuild'de otomatik) ve
   (b) `POST /api/debug/schema/reindex` (talep üzerine prune eder). Cache-hit
   yolunda (rebuild olmayan `load_schema` çağrıları) prune ÇALIŞMAZ — orphan,
   bir sonraki rebuild'e (herhangi bir sebeple, force veya değil) veya elle
   tetiklenen `POST /reindex`'e kadar Qdrant'ta kalabilir. Düşük etkili
   (orphan point aramaya/isabet etmeye katkı sağlamaz, yalnızca Qdrant'ta
   kullanılmayan yer kaplar) ama sessizce bırakılmadı — burada işaretlendi.
   *İlgili Dosya:* `backend/app/schema_manager.py` (`load_schema`, `old_embeddings_for_reindex`, prune-on-rebuild çağrısı), `backend/app/schema_reindex.py` (`reindex_embeddings`), `backend/app/rag_manager.py` (`prune_schema_ddl_points`)

## §17. Sprint 28.9 (Semantic / Result Cache) devirleri — AÇIK

`app/cache/result_cache_key.py` (saf: `normalize_query`/`compute_result_cache_key`)
+ `sql_cache` tablosu + `app/result_cache.py` adaptor + `SchemaManager.
get_cached_schema_signature` + `run_pipeline`'ın `_cache_lookup` entegrasyonu
+ `GET /api/debug/cache/stats`/`POST /api/debug/cache/clear`, üretilen SQL'i
tamamen aynı (dialect + `schema_signature` + normalize edilmiş natural-language
sorgu) istekler için writer-critic LLM döngüsünü atlayan **deterministik exact
result cache**'i teslim etti; aşağıdakiler tasarım spec'inde bilinçli olarak
kapsam dışı bırakıldı (sessiz düşürme yok). **Bununla Phase 9 (Large Schema
Production Scale) kapanır** — sıradaki Phase 10 (29.0 PostgreSQL Docker
Integration Adapter).

1. **Semantik/embedding-benzerlik cache ertelendi (precision riski).** 28.9
   yalnızca **exact-match** anahtar kullanır (`compute_result_cache_key` —
   normalize edilmiş sorgu + dialect + schema_signature birebir aynı olmalı).
   Anlamca eşdeğer ama farklı ifade edilmiş sorgular ("son 30 günün siparişleri"
   vs "geçen ay verilen siparişler") cache miss olur — LLM her seferinde
   yeniden üretir. Embedding-benzerlik tabanlı bir yaklaşım (ROADMAP backlog
   "Semantik Önbellekleme") isabet oranını artırır ama yanlış-pozitif riski
   taşır (anlamca *yakın* ama SQL-semantiği *farklı* iki sorgu aynı SQL'i
   döndürebilir) — bilinçli olarak bu sprint'in kapsamı dışında bırakıldı;
   güvenlik/doğruluk trade-off'u ayrı bir tasarım kararı gerektirir.
   *İlgili Dosya:* `backend/app/cache/result_cache_key.py`
2. **Execution/result-set (satır-seviyesi) cache yok.** 28.9 yalnızca
   **üretilen SQL metnini** cache'ler; sorgunun DB üzerinde çalıştırılmasıyla
   dönen satırları (result set) cache'lemek kapsam dışı — bu, gerçek DB
   execution/adapter katmanı (Phase 10, 29.x) gerektirir ve veri tazeliği
   (staleness) sorununu SQL-cache'ten çok daha ciddi şekilde gündeme getirir.
   *İlgili Dosya:* Phase 10 · 29.0 (henüz mevcut değil)
3. **TTL/boyut-tabanlı otomatik eviction yok.** `sql_cache` tablosu sınırsız
   büyür; tek temizlik yolu elle çağrılan `POST /api/debug/cache/clear`
   (tüm tabloyu boşaltır — seçici/kısmi silme yok). Zaman-aşımlı (TTL) veya
   LRU/boyut-tavanlı otomatik eviction bilinçli olarak kapsam dışı bırakıldı.
   *İlgili Dosya:* `backend/app/result_cache.py` (`clear_cache`)
4. **Prompt-template/model değişikliğinde otomatik invalidation yok.**
   `compute_result_cache_key`'in girdileri yalnız `version`/`dialect`/
   `schema_signature`/normalize edilmiş sorgu — LLM modeli, prompt template'i
   veya writer-critic mantığı değişse bile cache anahtarı **değişmez**; eski
   cache'lenmiş SQL sunulmaya devam eder. Bu **bilinçli bir tasarım kararı**:
   anahtar yalnız *şema tazeliğini* (freshness) garanti eder — cache'lenmiş
   SQL, `schema_signature` değişmediği sürece hâlâ **geçerli** bir SQL'dir
   (üretildiği zamanki şemaya göre; hit yine de `validate_sql` ile yeniden
   doğrulanır). Model/prompt değişikliğinde yalnızca "muhtemelen artık daha
   iyi üretilebilir" bir SQL'i eskisiyle değiştirmemek — yanlışlık riski
   değil, iyileştirme fırsatı kayıp riski. Değişikliğe duyarlı invalidation
   (ör. `RESULT_CACHE_KEY_VERSION` bump veya model-fingerprint) ileride
   `POST /cache/clear` ile elle veya bir sonraki `RESULT_CACHE_KEY_VERSION`
   artışıyla ele alınabilir.
   *İlgili Dosya:* `backend/app/cache/result_cache_key.py` (`RESULT_CACHE_KEY_VERSION`)
5. **Cache-hit-rate agregasyonu/dedike metrics-dashboard paneli yok.**
   `run_pipeline` sonuçta ham `cache_hit: bool` alanını + trace metadata'da
   aynı bayrağı emit eder, ama bunu zaman-pencereli hit-rate/toplam
   tasarruf gibi bir agregat metriğe çeviren bir bileşen (27.6 `metrics`/27.7
   `dashboard` desenine benzer) bu sprint'te eklenmedi — dedike bir "cache
   performance" paneli ileriye ertelendi.
   *İlgili Dosya:* `backend/app/sql_pipeline.py` (`cache_hit` alanı), 27.6/27.7 (`app/dashboard.py`/`app/metrics.py`) potansiyel genişletme noktası
6. **AÇIK (devam) — frontend `maxNodesLimit` kalıcı çözümü yok.** Bkz. §2 ve
   §12 kalem 12/§16'daki tekrarlanan not; 28.9 backend-only bir sprint —
   frontend D3 graph UI performans limiti farklı bir (frontend) katmanda,
   bu sprint'in kapsamı dışında AÇIK kalmaya devam eder.
   *İlgili Dosya:* frontend (`maxNodesLimit`, bkz. §2)
7. **Cache anahtarı yalnız `schema_signature`'a bağlı — `business_rules`/
   synonym-ignore kuralları/RAG retrieval bağlamı değişikliklerini
   YAKALAMAZ.** `compute_result_cache_key` girdileri `version`/`dialect`/
   `schema_signature`/normalize edilmiş sorgu ile sınırlı; AQR içindeki
   `business_rules`, synonym/ignore-rule konfigürasyonu ya da RAG'ın
   retrieval bağlamı (örnek/kural önerileri) değişse bile — şema
   değişmediği sürece — cache anahtarı **aynı kalır** ve eski üretilmiş SQL
   sunulmaya devam eder. Bu, kalem 4'teki "yalnızca şema tazeliği garanti
   edilir" tasarım kararının doğal bir uzantısıdır (dürüst açıklama):
   cache **taze değildir** iş kuralı/RAG bağlamı açısından, yalnız
   **güvenlidir** (`validate_sql` ile her hit yeniden doğrulanır — şemaya
   göre geçersiz bir SQL asla döndürülmez). İş kuralı/RAG-bağlam-duyarlı
   invalidation kapsam dışı bırakıldı.
   *İlgili Dosya:* `backend/app/cache/result_cache_key.py` (`compute_result_cache_key`)
8. **Revizyon isteği (`previous_sql` set) cache'i TAMAMEN bypass eder —
   kasıtlı tasarım.** `_cache_lookup`, `previous_sql` doluysa (strip sonrası
   boş değilse) imza/anahtar hesaplamadan ÖNCE `(None, None, None, False)`
   döner — ne cache okunur ne yazılır. Final review'de yakalanan gerçek bir
   UX regresyonunu (aynı doğal-dil metniyle gönderilen bir "bu SQL'i
   revize et" isteği, cache anahtarı `previous_sql`'i içermediği için
   revizyonu sessizce yok sayıp eski cache'lenmiş SQL'i döndürüyordu) 28.9
   final-review düzeltme dalgasında giderdi. Revizyon istekleri, tanımı
   gereği cache'lenemez kabul edilir; `previous_sql`'i anahtara dahil edip
   cache'lemeyi genişletmek yerine bypass tercih edildi (daha basit, hatasız).
   *İlgili Dosya:* `backend/app/sql_pipeline.py` (`_cache_lookup`, `run_pipeline`)

## §18. Sprint 29.0 (PostgreSQL Docker Integration Adapter) devirleri — AÇIK

`app/evaluation/postgres_connection_resolver.py` (saf `resolve_local_docker_connection`)
+ `app/evaluation/postgres_schema_adapter.py` (contract-first `information_schema`
introspection, `build_database_schema_from_introspection` saf çekirdek, composite FK
`referential_constraints`+`position_in_unique_constraint` ile ordinal-eşleştirmeli
doğru) + repo kökü `docker-compose.yml` + deterministik
`backend/tests/fixtures/postgres/seed.sql` + gated entegrasyon testleri + CI seed
adımı, Phase 10'un (Real Database Adapter Layer) **ilk** sprint'ini teslim etti —
25.8'in *contract stub + yalnızca local Docker smoke* sınırını **korur** (production
execution hâlâ yok), yalnızca **şema okuma** katmanını gerçekleştirir. Aşağıdakiler
tasarım spec'inde bilinçli olarak kapsam dışı bırakıldı (sessiz düşürme yok).

1. **Production request pipeline'ına wiring yok.** `SQLPostgresSchemaAdapterContract`
   hiçbir orchestrator/`sql_pipeline.py`/`SchemaManager`'a bağlanmadı — adapter
   inert/standalone bir modül olarak kalır, canlı istek akışında **hiç çağrılmaz**.
   Gerçek wiring Phase 11'e (30.2 Connection Registry API, 30.3 Schema Sync API)
   ertelendi — bu iki API, hangi connection'ın hangi tenant/workspace için
   kullanılacağını çözecek katmanı sağlamadan adapter'ı canlıya bağlamak erken
   olurdu.
   *İlgili Dosya:* `backend/app/evaluation/postgres_schema_adapter.py`
2. **Legacy `SchemaManager._extract_postgres_metadata` bu güvenli contract'a
   taşınmadı.** Üretimde PostgreSQL şeması hâlâ eski, bu sprint'in dokunmadığı
   `_extract_postgres_metadata` yoluyla çekiliyor; büyük/kırıcı bir refactor
   olacağından legacy yol olduğu gibi bırakıldı — iki bağımsız PostgreSQL
   introspection yolu (legacy + 29.0'ın yenisi) şimdilik **yan yana** duruyor.
   *İlgili Dosya:* `backend/app/schema_manager.py` (`_extract_postgres_metadata`)
3. **Yalnızca local-Docker connection; uzak/production connection yok.**
   `resolve_local_docker_connection` yalnızca `localhost`/`127.0.0.1` host'larını
   kabul eder (25.8'in aynı sınırı) — remote/production bir PostgreSQL'e karşı
   introspection bu sprint'in kapsamı dışında; gerçek connection registry/secret
   yönetimi olmadan uzak bağlantıyı açmak güvenlik riski taşırdı.
   *İlgili Dosya:* `backend/app/evaluation/postgres_connection_resolver.py`
4. **Yalnız `public` şema BASE TABLE; view/materialized view/non-public şema
   yok.** `information_schema` sorgusu `table_schema = 'public'` ve
   `table_type = 'BASE TABLE'` ile filtrelenir — view'lar, materialized view'lar
   ve `public` dışındaki şema'lar (ör. çok-şemalı bir kurumsal DB) introspect
   edilmez; schema-only/tek-şema tasarım kararı.
   *İlgili Dosya:* `backend/app/evaluation/postgres_schema_adapter.py` (`_read_information_schema`)
5. **Kolon zenginleştirme yok.** Üretilen `DatabaseSchema` yalnız isim/tip/
   nullable/PK/FK taşır; `pg_description` yorum/açıklama metni veya örnek
   (sample) değerler embed/prompt'a katılmaz — schema-only kalır (28.8'in
   `TECH-DEBT §16` madde 4'teki embed-text zenginleştirme kapsam dışılığıyla
   tutarlı).
   *İlgili Dosya:* `backend/app/evaluation/postgres_schema_adapter.py`
6. **Connection Registry / çoklu bağlantı yönetimi yok.** 29.0 tek, doğrudan
   enjekte edilen bir connection nesnesiyle çalışır; birden fazla PostgreSQL
   instance'ını (tenant/workspace başına) kayıt altına alıp seçen bir registry
   katmanı yok — bu, Phase 11 · 30.2 Connection Registry API'ye ait.
   *İlgili Dosya:* Phase 11 · 30.2 (henüz mevcut değil)
7. **29.1 execution wiring'i henüz yapılmadı.** 29.0 yalnızca şema *okur*;
   üretilen `DatabaseSchema`'yı gerçek SQL execution'a (25.8'in read-only adapter'ı
   ile birleştirip production-grade bir akışa) bağlamak Sprint 29.1
   (PostgreSQL Read-Only Execution) kapsamına bırakıldı.
   *İlgili Dosya:* Sprint 29.1 — **ÇÖZÜLDÜ**, bkz. §19.

## §19. Sprint 29.1 (PostgreSQL Read-Only Execution) devirleri — AÇIK

Yeni `PostgresDatabaseExecutionAdapter` (`backend/app/evaluation/
postgres_execution_adapter.py`), dialect-agnostic paylaşılan execution
sözleşmesini (`app/evaluation/multi_database_execution.py`,
`SQLDatabaseExecutionAdapter`) uygulayan sprint — local-Docker-only, read-only,
driver-izole, yan-etkisiz (persistence yok). 29.0'ın
`resolve_local_docker_connection`'ı ile bir local-Docker connection'ı çözer,
gerçek `SELECT`'i 25.8'in `SQLPostgresAdapterContract`'ına delege eder, ham
sonucu saf `normalize_postgres_execution_result` ile paylaşılan
`SQLDatabaseExecutionResult`'a normalize eder (dict satırlar kolon adlarından
kurulur; arity uyuşmazlığında pozisyonel `col_<i>` fallback'i + uyarı). 25.8'e
geriye-uyumlu ekleme: `SQLPostgresAdapterExecutionResult.columns` (`cur.
description`'dan yakalanır) — dict satırların gerçek kolon adı taşımasını
sağlar. Bağlantı çözümlenemediğinde (resolver `None`) adapter asla raise
etmez — boş `SQLDatabaseExecutionResult` + `execution_error` döner (Docker'sız
CI safe-skip + runtime'ın boş sonuçla çalışmasına izin verir). Import-time
driver-izolasyonu subprocess testiyle kilitlendi (`psycopg2`/`asyncpg`/
`sqlalchemy` import edilmez). Docker'sız safe-skip olan gated entegrasyon
testleri (gerçek `SELECT` → adlandırılmış dict satırlar, çok-tablolu `JOIN`,
`max_rows` truncation, `statement_timeout`). Bununla 29.0'ın ertelediği
"gerçek execution" teslim edilir; 29.0'ın şema-okuma sınırı DEĞİŞMEDİ.
Aşağıdakiler tasarım spec'inde bilinçli olarak kapsam dışı bırakıldı (sessiz
düşürme yok).

1. **Canlı HTTP request pipeline wiring yok.** `PostgresDatabaseExecutionAdapter`
   production `sql_pipeline.py`/`/api/jobs` akışına bağlanmadı; standalone/inert
   kalır, canlı istekte çağrılmaz. → Phase 11 · 30.2 Connection Registry API /
   30.4 Query Run API.
   *İlgili Dosya:* `backend/app/evaluation/postgres_execution_adapter.py`
2. **Connection Registry / uzak & production connection yok.** Yalnız 29.0
   resolver'ın local-Docker connection'ı kullanılır; çoklu-bağlantı/tenant
   seçimi yok. → Phase 11 · 30.2.
   *İlgili Dosya:* Phase 11 · 30.2 (henüz mevcut değil)
3. **26.3 Query Risk Classifier + 26.4 Sensitive Table/Column gate wiring
   yok.** Execution öncesi yalnız 25.8'in 26.2 read-only enforcement gate'i
   uygulanır; risk/sensitive-tablo gate'leri bilinçli olarak bağlanmadı. →
   ileri sprint.
   *İlgili Dosya:* `backend/app/evaluation/postgres_execution_adapter.py`
4. **EXPLAIN-only mode yok.** Adapter yalnız `READ_ONLY` mode kabul eder,
   `EXPLAIN_ONLY` reddedilir. → 29.2 PostgreSQL EXPLAIN-Only Mode — **ÇÖZÜLDÜ**,
   bkz. §20.
   *İlgili Dosya:* `backend/app/evaluation/postgres_execution_adapter.py`
5. **Oracle/MySQL/SQL Server execution adapter'ları yok.** → 29.3–29.6.
   *İlgili Dosya:* Phase 10 · 29.3+
6. **Execution trace/audit persistence yok.** 25.6 execution-trace üretimi
   opsiyonel/bağlanmadı; hiçbir store'a yazılmaz. → 30.4 Query Run API.
   *İlgili Dosya:* yok / gelecekte 30.4
7. **Merkezî/canlı execution router registry yok.** Adapter router'a
   takılabilir (`SQLDatabaseExecutionRouter`) ama canlı bir registry'ye
   kaydedilmedi. → 30.x.
   *İlgili Dosya:* `backend/app/evaluation/multi_database_execution.py`
8. **Import-time network-client isolation assert edilmedi** (yalnız
   DB-driver isolation edildi). `app.evaluation.__init__`'in eager re-export'u
   `schema_contract → pydantic`'i çeker, o da benign `asyncio`/`socket` yükler
   — gerçek driver/ağ sızıntısı değil, ama network forbidden-list ile test bu
   yüzden yazılmadı.
   *İlgili Dosya:* `backend/tests/evaluation/test_postgres_execution_adapter_integration.py`
   yakınındaki isolation testi; `backend/app/evaluation/__init__.py`

## §20. Sprint 29.2 (PostgreSQL EXPLAIN-Only Mode) devirleri — AÇIK

29.1'in yalnız `READ_ONLY` kabul edip `EXPLAIN_ONLY`'yi reddettiği yerden devam
edip, PostgreSQL için gerçek EXPLAIN(-only) execution path'ini ekleyen sprint —
local-Docker-only, read-only, driver-izole, standalone/inert (canlı pipeline'a
wire edilmedi). İki katman: **Katman 1** (`backend/app/evaluation/
postgres_adapter.py`) `execution_mode="explain_only"` iken doğrulanmış iç
SELECT'in önüne `EXPLAIN <sql>` (opt-in `EXPLAIN (ANALYZE) <sql>`) ekleyip koşar
(`SQLPostgresAdapterConfig.explain_analyze: bool = False` + saf
`_build_explain_sql`); 25.8'in read-only gate'i iç SELECT üzerinde değişmedi,
`sql_sha256` her zaman orijinal SQL'den. **Katman 2** (`backend/app/evaluation/
postgres_execution_adapter.py`) `EXPLAIN_ONLY` kabul eder, `capabilities()`'e
eklenir, `_to_pg_config` shared→25.8 config eşler; plan satırları `"QUERY PLAN"`
dict-row'ları olarak döner (kontrat değişmedi). Shared
`SQLDatabaseExecutionConfig.explain_analyze` geriye-uyumlu eklendi. §19.4
(EXPLAIN-only mode yok) ile bu ÇÖZÜLDÜ. Aşağıdakiler tasarım spec'inde bilinçli
olarak kapsam dışı bırakıldı (sessiz düşürme yok).

1. **Canlı HTTP request pipeline wiring yok.** İki adapter da production
   `sql_pipeline.py`/`/api/jobs` akışına bağlanmadı; standalone/inert kalır,
   canlı istekte çağrılmaz. → Phase 11 · 30.2 Connection Registry API / 30.4
   Query Run API.
   *İlgili Dosya:* `backend/app/evaluation/postgres_execution_adapter.py`
2. **`connection_aware_execution.py` non-READ_ONLY'yi hard-reject ederken adapter
   EXPLAIN_ONLY advertise ediyor.** Bu katman `capabilities()`'in `EXPLAIN_ONLY`
   içerdiğini hesaba katmadan non-`READ_ONLY` modları reddeder. 29.2'de **bug
   yok** (adapter inert, canlı pipeline'a wire değil); 30.x wiring'de bu ikisi
   uzlaştırılacak (EXPLAIN_ONLY mode'unun bu gate'ten geçmesine izin ver).
   *İlgili Dosya:* `backend/app/evaluation/connection_aware_execution.py`
3. **`EXPLAIN (FORMAT JSON)` / yapılandırılmış plan + plan-tabanlı maliyet gate
   yok.** Yalnız düz metin plan (`"QUERY PLAN"` satırları) döner; makine-okunur
   JSON plan ve plan-tabanlı maliyet/analiz gate bilinçli ertelendi. → ileri
   sprint.
   *İlgili Dosya:* `backend/app/evaluation/postgres_adapter.py`
4. **Connection registry / uzak & production connection yok.** Yalnız 29.0
   resolver'ın local-Docker connection'ı kullanılır. → Phase 11 · 30.2.
   *İlgili Dosya:* Phase 11 · 30.2 (henüz mevcut değil)
5. **Oracle/MySQL/SQL Server EXPLAIN path'leri yok.** → 29.3–29.6.
   *İlgili Dosya:* Phase 10 · 29.3+
6. **Merkezî/canlı execution router registry yok.** → 30.x.
   *İlgili Dosya:* `backend/app/evaluation/multi_database_execution.py`
7. **Execution trace/audit persistence yok.** → 30.4 Query Run API.
   *İlgili Dosya:* yok / gelecekte 30.4
8. **Deferred minor'lar (bloklamaz):** integration testinde inline `_JOIN_SQL`
   SQL string duplikasyonu (küçük tekrar).
   *İlgili Dosya:* `backend/tests/evaluation/test_postgres_execution_adapter_integration.py`

## §21. Sprint 29.3 (Oracle Contract Adapter) devirleri — AÇIK

25.9'un Oracle adapter stub'ını, PostgreSQL 29.0→29.1 desenini izleyerek gerçek
bir local-Docker-only, read-only Oracle execution path'ine çeviren sprint —
`oracledb` thin mode, driver-izole, standalone/inert (canlı pipeline'a wire
edilmedi). Üç katman: `oracle_adapter.py` (gerçek execute + `SET TRANSACTION
READ ONLY` + `call_timeout`), `oracle_connection_resolver.py` (env → connection |
None), `oracle_execution_adapter.py` (shared-contract köprü, `(CONNECTION_REF,
READ_ONLY)`, EXPLAIN_ONLY reddi). §19.4/§20 postürü korunur. Aşağıdakiler tasarım
spec'inde bilinçli olarak kapsam dışı bırakıldı (sessiz düşürme yok).

1. **✅ ÇÖZÜLDÜ (29.4).** Gerçek Oracle Docker imajı (`gvenzl/oracle-free:
   23-slim-faststart`) + seed şeması (`backend/tests/fixtures/oracle/seed.sql`,
   5 tablo/18 statement) + ayrı `oracle-integration` CI job'ı
   (`.github/workflows/backend-ci.yml`) eklendi; `oracle`-mark'lı seeded testler
   artık CI'da canlı koşuyor (bkz. `docs/PLANNED-SPRINTS.md` 29.4 satırı).
   *İlgili Dosya:* `docker-compose.yml`, `.github/workflows/backend-ci.yml`,
   `backend/tests/fixtures/oracle/seed.sql`, `backend/app/evaluation/oracle_seed.py`
2. **Oracle schema introspection adapter yok.** `ALL_TAB_COLUMNS`/`ALL_CONSTRAINTS`/
   `ALL_CONS_COLUMNS` → `DatabaseSchema` (Postgres 29.0 `postgres_schema_adapter.py`
   dengi) çıkarılmadı. → ileri sprint.
   *İlgili Dosya:* gelecekte `backend/app/evaluation/oracle_schema_adapter.py`
3. **Oracle EXPLAIN-only mode yok.** Köprü `EXPLAIN_ONLY`'yi reddeder;
   `EXPLAIN PLAN FOR` + `DBMS_XPLAN.DISPLAY` yolu (29.2 PostgreSQL EXPLAIN dengi)
   eklenmedi. → ileri sprint.
   *İlgili Dosya:* `backend/app/evaluation/oracle_adapter.py`,
   `backend/app/evaluation/oracle_execution_adapter.py`
4. **✅ ÇÖZÜLDÜ (29.4).** `tests/evaluation/test_oracle_execution_adapter.py`'ye
   fake-`oracledb` + enjekte edilmiş resolver kullanan Docker'sız bridge→
   low-level unit testi eklendi — `OracleDatabaseExecutionAdapter.execute`'un
   resolver-non-`None` delegasyon yolu artık Docker olmadan da kilitli.
   *İlgili Dosya:* `backend/tests/evaluation/test_oracle_execution_adapter.py`
5. **Connection registry / uzak & production connection / wallet / TNS yok.**
   Yalnız 29.3 resolver'ın local-Docker connection'ı. → Phase 11 · 30.2.
   *İlgili Dosya:* Phase 11 · 30.2 (henüz mevcut değil)
6. **Canlı HTTP pipeline wiring yok / merkezî execution router registry yok.**
   Adapter router'a takılabilir ama canlı bir registry'ye kaydedilmedi; production
   `/api/jobs` akışına bağlanmadı. → 30.2 / 30.4 / 30.x.
   *İlgili Dosya:* `backend/app/evaluation/multi_database_execution.py`
7. **`oracledb` thick mode / Oracle Instant Client yok.** Yalnız thin mode
   (saf-Python). Gerekmedikçe ertelenir.
   *İlgili Dosya:* `backend/app/evaluation/oracle_adapter.py`
8. **Deferred minor'lar (bloklamaz):** `_result()` already-tuple `columns`/
   `warnings`'i `tuple(...)` ile yeniden sarar (zararsız, postgres precedent'i);
   `execute()` check sırasında `fixture_ref` reddi yalnız edge-case'le erişilir
   (base request zaten ikisinin birden truthy olmasını yasaklar — postgres'ten
   miras).
   *İlgili Dosya:* `backend/app/evaluation/oracle_adapter.py`,
   `backend/app/evaluation/oracle_execution_adapter.py`

## §22. Sprint 29.4 (Oracle Docker/Test Harness) devri — ÇÖZÜLDÜ (29.4)

Bu bölüm §21'in kalan (değişmeyen) kalemlerini TEKRARLAMAZ — bkz. §21 (#2/#3/
#5/#6/#7/#8, hâlâ açık). Yalnız 29.4'ün KENDİ verifikasyonunda ortaya çıkan ve
aynı sprint içinde çözülen bir regresyonu kaydeder (arşiv amaçlı — çözülmüş
tuzaklar aranabilir kalsın).

1. **[ÇÖZÜLDÜ] CI golden-gate kontrat testi yeni `oracle-integration` job'ı
   yüzünden FAIL veriyordu.** `tests/test_golden_eval_ci_gate_contract.py::
   test_backend_ci_golden_gate_does_not_use_secrets_or_network_env`,
   `.github/workflows/backend-ci.yml` içeriğini "Run golden eval profile"
   satırından **dosya sonuna kadar** tarayıp bu blokta `env:`/`secrets`
   olmadığını doğruluyordu — testin tarama sınırı tek bir job'a/step'e scope'lu
   DEĞİLDİ. 29.4'ün yeni `oracle-integration` job'ı bu satırdan SONRA eklendiği
   ve kendi (gerçek secret içermeyen, yalnız Oracle local-Docker bağlantı
   ayarları olan) `env:` bloklarını taşıdığı için test yanlış-pozitif FAIL
   veriyordu. Full suite bu yüzden 2689 passed/**1 failed**/31 skipped
   dönüyordu (29.3'ün temiz 2682 passed/28 skipped'inden regresyon).
   **Çözüm:** testin tarama sınırı, "Run golden eval profile" satırından bir
   sonraki üst-seviye `  <job-name>:` anahtarına (2-boşluklu girinti) kadar
   daraltıldı — böylece tarama `backend-tests` job'ının dışına taşmıyor, golden
   step'lerin hermetik olduğu garantisi korunuyor ve yeni `oracle-integration`
   job'ının kendi `env:` blokları taramaya dahil edilmiyor. `oracle-integration`
   job'ı yeniden sıralanmadı, hiçbir assertion gevşetilmedi. Kod DEĞİŞMEDİ
   (yalnız test/CI-dosyası etkileşimi) — 29.3'ün execution modülleri bu
   regresyona dahil değildi. Full suite artık 2690 passed/31 skipped/0 failed.
   *İlgili Dosya:* `backend/tests/test_golden_eval_ci_gate_contract.py`,
   `.github/workflows/backend-ci.yml`

## §23. Sprint 29.5 (MySQL Adapter Contract) devirleri — AÇIK

Oracle 29.3'ün (Contract Adapter) ve 29.4'ün (Docker/Test Harness) ikisini TEK
sprint'te birleştiren, MySQL için gerçek bir local-Docker-only, read-only
execution path'i (`pymysql`, driver-izole) + tam test harness'i (seed şeması +
seed applier + docker-compose servisi + ayrı canlı CI job'ı) ekleyen sprint —
standalone/inert (canlı production pipeline'a wire edilmedi). Üç katman:
`mysql_adapter.py` (gerçek execute + `START TRANSACTION READ ONLY` +
`SET SESSION max_execution_time`), `mysql_connection_resolver.py` (env →
connection | `None`), `mysql_execution_adapter.py` (shared-contract köprü,
`(CONNECTION_REF, READ_ONLY)`, EXPLAIN_ONLY reddi). Aşağıdakiler tasarım
spec'inde (§1) bilinçli olarak kapsam dışı bırakıldı (sessiz düşürme yok).

1. **MySQL schema introspection adapter yok.** `information_schema` →
   `DatabaseSchema` (Postgres 29.0 `postgres_schema_adapter.py` dengi)
   çıkarılmadı. → ileri sprint (Postgres 29.0 dengi).
   *İlgili Dosya:* gelecekte `backend/app/evaluation/mysql_schema_adapter.py`
2. **MySQL EXPLAIN-only mode yok.** Köprü `EXPLAIN_ONLY`'yi reddeder;
   `EXPLAIN <sql>` / `EXPLAIN FORMAT=JSON <sql>` yolu (29.2 PostgreSQL EXPLAIN
   dengi) eklenmedi. → ileri sprint (29.2 dengi).
   *İlgili Dosya:* `backend/app/evaluation/mysql_adapter.py`,
   `backend/app/evaluation/mysql_execution_adapter.py`
3. **Canlı HTTP pipeline wiring yok / merkezî execution router registry yok.**
   Adapter router'a takılabilir ama canlı bir registry'ye kaydedilmedi;
   production `/api/jobs` akışına bağlanmadı. → 30.2 / 30.4 / 30.x.
   *İlgili Dosya:* `backend/app/evaluation/multi_database_execution.py`
4. **Connection registry / uzak & production connection / TLS yok.** Yalnız
   29.5 resolver'ın local-Docker connection'ı (`MYSQL_TEST_*` env). →
   Phase 11 · 30.2 Connection Registry API.
   *İlgili Dosya:* Phase 11 · 30.2 (henüz mevcut değil)
5. **C-tabanlı driver'lar (`mysqlclient` / `mysql-connector-python`) / thick
   mode yok.** Yalnız saf-Python `PyMySQL` (thin, pure-Python). Gerekmedikçe
   ertelenir.
   *İlgili Dosya:* `backend/app/evaluation/mysql_adapter.py`,
   `backend/requirements.txt`

## §24. Sprint 29.6 (SQL Server Adapter Contract) devirleri — AÇIK

MySQL 29.5'in üç-katmanlı desenini SQL Server'a taşıyan, gerçek bir
local-Docker-only, read-only execution path'i (`pymssql`, driver-izole) +
tam test harness'i (seed şeması + seed applier + `db_datareader`-only login
provisioning + docker-compose servisi + ayrı canlı CI job'ı) ekleyen sprint —
standalone/inert (canlı production pipeline'a wire edilmedi). SQL Server'ın
diğer üç dialect'ten temel farkı: read-only bir transaction pre-statement'ı
YOK — read-only, `db_datareader`-only bir **login** ile enforce edilir (bkz.
`mssql_adapter.py` docstring'i). Üç katman: `mssql_adapter.py` (gerçek
execute; pre-statement yok; connect-kwarg query timeout `login_timeout`/
`timeout`), `mssql_connection_resolver.py` (env → connection | `None`),
`mssql_execution_adapter.py` (shared-contract köprü, `(CONNECTION_REF,
READ_ONLY)`, EXPLAIN_ONLY reddi). Aşağıdakiler tasarım spec'inde (§1)
bilinçli olarak kapsam dışı bırakıldı (sessiz düşürme yok).

1. **SQL Server schema introspection adapter yok.** `INFORMATION_SCHEMA`/
   `sys.*` → `DatabaseSchema` (Postgres 29.0 `postgres_schema_adapter.py`
   dengi) çıkarılmadı. → ileri sprint (Postgres 29.0 dengi).
   *İlgili Dosya:* gelecekte `backend/app/evaluation/mssql_schema_adapter.py`
2. **SQL Server EXPLAIN-only / SHOWPLAN yok.** Köprü `EXPLAIN_ONLY`'yi
   reddeder; `SET SHOWPLAN_XML ON` / `SET STATISTICS PROFILE ON` yolu (29.2
   PostgreSQL EXPLAIN dengi) eklenmedi. → ileri sprint (29.2 dengi).
   *İlgili Dosya:* `backend/app/evaluation/mssql_adapter.py`,
   `backend/app/evaluation/mssql_execution_adapter.py`
3. **Canlı HTTP pipeline wiring yok / merkezî execution router registry
   yok.** Adapter router'a takılabilir ama canlı bir registry'ye
   kaydedilmedi; production `/api/jobs` akışına bağlanmadı. → 30.2 / 30.4 /
   30.x.
   *İlgili Dosya:* `backend/app/evaluation/multi_database_execution.py`
4. **Connection registry / uzak & production connection / TLS / Azure AD
   authentication yok.** Yalnız 29.6 resolver'ın local-Docker connection'ı
   (`MSSQL_TEST_*` env, SQL Server login/password auth). → Phase 11 · 30.2
   Connection Registry API.
   *İlgili Dosya:* Phase 11 · 30.2 (henüz mevcut değil)
5. **`pyodbc` / ODBC driver path yok.** Yalnız saf-Python `pymssql` (FreeTDS
   tabanlı, ODBC driver kurulumu gerektirmez). Gerekmedikçe ertelenir.
   *İlgili Dosya:* `backend/app/evaluation/mssql_adapter.py`,
   `backend/requirements.txt`

## §25. Sprint 29.7 (Adapter Conformance Eval Suite) devirleri — AÇIK

29.0–29.6'da dört dialect'e (Postgres/Oracle/MySQL/SQL Server) ayrı ayrı
inşa edilmiş standalone execution adapter'ları tek bir profil kaydı
(`AdapterConformanceProfile` / `CONFORMANCE_PROFILES`,
`backend/app/evaluation/adapter_conformance.py`) altında birleştiren,
Docker-free deterministik bir conformance çekirdeği (5 adapter — sqlite
dahil, connection-based dört dialect + fixture-based sqlite) + konsolide
canlı matrix (4 connection-based dialect, per-param `pytest_marker`, üç
tekrarlı seeded test dosyasını emekli eder) + bir rapor emitter'ı
(`python -m app.evaluation.adapter_conformance report`) ekleyen sprint.
Paylaşılan kontrat dosyası (`multi_database_execution.py`) DEĞİŞMEDİ —
`git diff --stat main..HEAD -- backend/app/evaluation/multi_database_execution.py`
boş. Aşağıdakiler tasarım spec'inde (§7) bilinçli olarak kapsam dışı
bırakıldı (sessiz düşürme yok).

1. **SQLite canlı seeded matrix yok.** SQLite fixture-based olduğu için
   yalnız deterministik çekirdekle (dialect/capabilities/router/inert-graceful/
   EXPLAIN-consistency/result-integrity) kapsanıyor; diğer dört dialect gibi
   Docker-seeded bir canlı battery'si yok. → ileri sprint, gerekirse.
   *İlgili Dosya:* `backend/app/evaluation/adapter_conformance.py`,
   `backend/tests/evaluation/test_adapter_conformance.py`
2. **Rapor emitter'ı CI artifact değil / canlı+kontrat birleşik rapor yok.**
   `report` komutu manuel bir gözlemlenebilirlik aracı olarak kalıyor; canlı
   pass/skip verisi JSON'a bilinçli olarak dahil edilmedi (Docker gerektirir).
   CI'da artifact olarak yayınlanmıyor. → ileri sprint (gözlemlenebilirlik
   ailesi, 27.x tarzı).
   *İlgili Dosya:* `backend/app/evaluation/adapter_conformance.py`
3. **Conformance sert bir gate değil.** Ayrı bir gate CLI'ı / CI gate step'i
   yok (26.x/27.10 golden/regression-gate paritesi); mevcut dialect-başına
   pytest job'ları (postgres/oracle/mysql/sqlserver-integration) dolaylı
   olarak gate görevi görüyor. → ileri sprint, istenirse.
   *İlgili Dosya:* CI workflow dosyaları, `backend/app/evaluation/adapter_conformance.py`
4. **NL2SQL doğruluk conformance'ı yok.** Bu suite yalnız execution-contract
   conformance'ıdır (adapter'ın kontrata uyumu); NL→SQL üretim doğruluğu
   kapsam dışı (26.x/27.10 accuracy regression gate ailesinin işi). →
   kapsam dışı, karıştırılmasın.
   *İlgili Dosya:* yok (bilinçli kapsam ayrımı)

## §26. Sprint 30.0 (Public Query API Contract) devirleri — AÇIK

30.0 kesişen sözleşme konvansiyonunu (kanonik `ApiResponse` envelope + `/api/v1`
versiyon + offset pagination + mevcut hata sözleşmesinin re-export'u) tek-kaynak
modül (`backend/app/api/contract.py`) + 29.7 tarzı conformance guard
(`backend/tests/api/test_public_api_contract_conformance.py`) olarak kurdu;
mevcut 20+ `/api/*` endpoint grandfathered (DEĞİŞMEDİ). Aşağıdakiler tasarım
spec'inde (§7) bilinçli olarak kapsam dışı bırakıldı (sessiz düşürme yok).

1. **Legacy endpoint migrasyonu yok.** 20+ mevcut `/api/*` endpoint hâlâ kendi
   ad-hoc `*EnvelopeResponse` şekillerinde; `/api/v1` + kanonik `data` envelope'a
   taşınmadı (kırıcı — frontend/testler etkilenir). → her 30.x kendi yüzeyini
   taşır ya da ayrı bir migrasyon sprint'i.
   *İlgili Dosya:* `backend/app/api/schemas.py`, `backend/app/main.py`, `backend/app/api/*_api.py`
2. **Legacy `/api/*` deprecation/sunset yok.** Versiyonsuz yollar kaldırılmadı;
   client-migration hikayesi gerekir. → migrasyon sprint'i sonrası.
   *İlgili Dosya:* `backend/app/main.py`
3. **Route-miss 404 kanonik değil.** Bilinmeyen bir path'e giden 404 Starlette'in
   default handler'ından geçer ve `{"detail": "..."}` şeklini korur (kanonik
   `{error:{code,message,details}}` yalnız gerçekten `HTTPException` fırlatan
   yollarda üretilir). 30.0 mevcut hata handler'larına dokunmadı (spec §7); bir
   route-not-found handler'ı eklemek ileri işi. → ileri sprint.
   *İlgili Dosya:* `backend/app/api/errors.py`, `backend/app/main.py`
4. **Cursor pagination + sayfa-üstü `total` yok.** Yalnız offset + sayfa-içi
   `count` (`PageMeta`); büyük result-set'ler için cursor tabanlı sayfalama ve
   toplam sayaç ertelendi. → ileri sprint, gerekirse.
   *İlgili Dosya:* `backend/app/api/contract.py`
5. **`app/errors/` domain taksonomisi HTTP `code`'una eşlenmedi.** HTTP katmanı
   status→code map'ini (`app/api/errors.py::map_status_to_code`) korur; 27.2'nin
   zengin taksonomisi (`app/errors/{categories,codes,registry}.py`) HTTP hata
   `code` alanına bağlanmadı. → ileri sprint.
   *İlgili Dosya:* `backend/app/api/errors.py`, `backend/app/errors/`
6. **AuthN / rate-limiting / OpenAPI publishing / somut `POST /api/v1/query` yok.**
   Meta endpoint public (auth 30.8'in işi); rate-limit/quota/request-signing,
   OpenAPI doc publishing/SDK üretimi ve somut query iş-endpoint'i bu sözleşmenin
   üstüne sonraki sprint'lerde inşa edilecek.
   *İlgili Dosya:* `backend/app/api/v1_meta.py` (sözleşme temeli)

## §27. Sprint 30.1 (Workspace API) devirleri — AÇIK

30.1 workspace'i **standalone** bir kaynak olarak ekledi (`/api/v1/workspaces` CRUD,
30.0 kanonik envelope'una uyan İLK route ailesi); mevcut global tablolar (jobs/
feedback/query_traces/sql_cache) retro-scope EDİLMEDİ. Bilinçli kapsam dışı
(sessiz düşürme yok).

1. **Global tabloların workspace'e scope edilmesi yok.** jobs/feedback/
   query_traces/sql_cache hâlâ global; `workspace_id` FK'leri eklenmedi
   (kırıcı; ileri sprint). → migrasyon sprint'i.
   *İlgili Dosya:* `backend/app/database.py`
2. **Connection/schema/history workspace'e bağlanmadı.** 30.2+ kendi kaynaklarını
   kurarken `workspace_id` referansını ekleyecek.
   *İlgili Dosya:* `backend/app/api/workspaces.py`
3. **Workspace membership / rol / per-workspace izin yok.** AuthN (30.8) gerektirir.
   *İlgili Dosya:* yok (30.8 bağımlılığı)
4. **Slug mutasyonu, soft-delete/arşivleme, workspace-seviyesi ayar/kota, name
   uniqueness yok.** Yalnız slug unique; slug 30.1'de değiştirilemez (`update_workspace`
   yalnız name/description whitelist'i).
   *İlgili Dosya:* `backend/app/workspace_repository.py`
5. **Cursor pagination / sayfa-üstü `total` yok.** 30.0'ın offset-only `PageMeta`'sı
   devralındı.
   *İlgili Dosya:* `backend/app/api/contract.py`
6. **Delete cascade semantiği yok.** Henüz workspace'e referans veren alt-kaynak
   yok; delete basit satır silme. → alt-kaynaklar (30.2+) eklendiğinde ele alınır.
   *İlgili Dosya:* `backend/app/workspace_repository.py`

## §28. Sprint 30.2 (Connection Registry API) devirleri — AÇIK

30.2 persistent connection registry'yi (`/api/v1/connections` CRUD) ekledi; Phase 7
domain modelini (`SQLConnectionProfile`) validasyon için yeniden kullanır,
**secret-by-reference** (ham secret asla saklanmaz/dönülmez). Standalone/inert.
Bilinçli kapsam dışı (sessiz düşürme yok).

1. **Canlı connection testi / health-check / secret çözümü / rotation yok.**
   Registry inert; bağlantı açma / `secret_ref` çözme 29.x resolver'lar / ileri
   pipeline wiring'in işi. → 30.4 / ileri.
   *İlgili Dosya:* `backend/app/connection_repository.py`, `backend/app/evaluation/*_connection_resolver.py`
2. **Execution pipeline'a wiring yok.** Registry üretim sorgu yolunu beslemiyor.
   → 30.4 Query Run.
   *İlgili Dosya:* `backend/app/api/connections.py`
3. **Non-READ_ONLY access mode yok** (domain yalnız READ_ONLY zorlar).
   *İlgili Dosya:* `backend/app/evaluation/connection_abstraction.py`
4. **Per-workspace RBAC / connection sahipliği / paylaşım yok** (AuthN 30.8).
   *İlgili Dosya:* yok (30.8 bağımlılığı)
5. **`connection_ref` mutasyonu, soft-delete, workspace-delete cascade yok.**
   `workspace_id` nullable FK ama workspace silinince ona bağlı connection'ların
   `workspace_id`'si **dangling** kalabilir (30.2 cascade/temizlik uygulamaz;
   30.1 §27.6'nın somutlaştığı ilk yer). → ileri sprint.
   *İlgili Dosya:* `backend/app/connection_repository.py`, `backend/app/workspace_repository.py`
6. **IAM secret detayları, TLS/sertifika, connection pooling, cursor pagination
   + sayfa-üstü `total` yok.** 30.0'ın offset-only `PageMeta`'sı devralındı.
   *İlgili Dosya:* `backend/app/api/connections.py`, `backend/app/api/contract.py`
