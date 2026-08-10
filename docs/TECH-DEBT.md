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
6. **AÇIK (dar edge-case, executor review'den) — `force=True` + eşzamanlı
   tablo kaldırma, o zorlanmış rebuild'de kaldırılan tablonun Qdrant
   point'ini tahliye ETMEZ.** `SchemaManager.load_schema`'da `force_refresh=
   True` iken cache-okuma bloğu (`if not force_refresh and os.path.exists(...)`)
   tamamen atlanır, dolayısıyla `old_embeddings_for_reindex` hep `None`
   kalır; `reindex_embeddings` bu durumda `force=True` ile çağrılır ve
   `old_fp={}`/`old_tables={}` ile başlar → `plan_reindex`'in `to_delete`'i
   (eski fingerprint kümesi ile yeni tablo kümesinin farkı) hep **boş**
   çıkar — kaldırılan bir tablo varsa bile. Sonuç: force-refresh sırasında
   DB'den artık gelmeyen bir tablonun eski `schema_ddl` Qdrant point'i
   **silinmez** (orphan kalır). Self-heals: bir sonraki `POST /api/debug/
   schema/reindex` çağrısı `RAGManager.prune_schema_ddl_points` ile gerçek
   Qdrant durumunu (cache fingerprint'inden bağımsız) tarayıp orphan/stale-id
   point'leri temizler; ya da bir sonraki **force-olmayan** `load_schema`
   çağrısı (gerçek cache'i okuyarak) drift'i doğru şekilde `to_delete`'e
   yakalar. Düşük etkili (orphan point aramaya/isabet etmeye katkı sağlamaz,
   yalnızca Qdrant'ta kullanılmayan yer kaplar) ama sessizce bırakılmadı —
   burada işaretlendi.
   *İlgili Dosya:* `backend/app/schema_manager.py` (`load_schema`, `old_embeddings_for_reindex`), `backend/app/schema_reindex.py` (`reindex_embeddings`)
