# Changelog

Bu projedeki tüm önemli değişiklikler bu dosyada belgelenir.

Format [Keep a Changelog](https://keepachangelog.com/tr/1.0.0/) temel alınır.
Tamamlanan işlerin sprint/PR detayı için `docs/SPRINT-PR-LOG.md`, geçici
çözümler için `docs/TECH-DEBT.md`, ileriye dönük plan için `ROADMAP.md` ve
`docs/PLANNED-SPRINTS.md` dosyalarına bakın.

> ℹ️ **Sürüm etiketi notu:** v1.0.0 `9907cd3` (#81) commit'ine annotated git
> tag olarak **uygulandı** (2026-06-18). Geçmiş kayıt: RC doğrulama dokümanında
> atıf yapılan eski `2f9e7e6` commit'i repoda yoktu; gerçek RC kanıt commit'i
> `5ce60ae` (#80) ile düzeltildi ve oradaki "%96.5 accuracy / 500 query" gibi
> metrikler **UNVERIFIED** olarak işaretlendi (gerçek bir CI çalışmasıyla
> yeniden bağlanmalıdır).

---

## [Unreleased] — Sprint 20–25 · retrieval / prompting / execution hattı (2026-06-05 → günümüz)

v1 baseline'ı sonrası retrieval, prompting ve execution-accuracy altyapısının
sözleşme (contract) odaklı geliştirilmesi. Bu fazdaki çıktıların çoğu hâlâ
contract/stub seviyesindedir; durum için `ROADMAP.md`'deki tabloya bakın.

### Added
- **Şema sözleşmesi ve ilişki motoru** (Sprint 20): şema sözleşmesi ve cross-db
  tutarlılık testleri, explicit FK sözleşmesi, örtük (implicit) ilişki tespiti
  sağlamlaştırması, graph traversal ve şema serileştirme (#82–#87).
- **Retrieval / context selection** (Sprint 21): şema context seçiminin
  sağlamlaştırılması, context selector entegrasyonu, şema özetleme sözleşmesi,
  embedding pipeline güvenilirliği, top-k retrieval sözleşmesi, context ranking,
  token budget yöneticisi (#88–#98).
- **Intent ve prompt planlama** (Sprint 22): intent extraction sözleşmesi,
  intent→context köprüsü, prompt planlama/rendering sözleşmeleri, SQL üretimi
  girdi derlemesi, SQL generation provider sınırı (#99–#104).
- **Prompt builder v2** (Sprint 23): few-shot örnek seçimi (deterministik ve
  dinamik), yapılandırılmış çıktı (structured output) üretimi, self-check
  üretimi (#105–#109).
- **Execution accuracy altyapısı** (Sprint 24–25): Golden Dataset V2 sözleşmesi
  ve loader, `SQLExecutionAccuracyHarness` + comparator, failure analytics
  sözleşmesi, eval gate aggregator, regression dashboard sözleşmesi, çoklu
  veritabanı execution sözleşmesi, connection abstraction katmanı,
  connection-aware execution planner ve orchestrator (#110–#121).
- **PostgreSQL read-only adapter — local Docker** (Sprint 25.8): 25.7 contract
  stub'ı, *yalnızca local Docker'a* karşı gerçek read-only `SELECT` çalıştırabilen
  kontrollü bir adapter'a dönüştürüldü — SELECT-only/tek-statement gate, read-only
  transaction + `statement_timeout`, `max_rows` truncation, credential-safe sanitize
  edilmiş hatalar, lazy driver import. live/remote/production capability'leri
  hard-False; hiçbir bağlantı orchestrator'a wire edilmediğinden default davranış
  inert kalır. Integration testleri Docker yoksa safe-skip; CI'a `postgres:16`
  servisi eklendi (#125).
- **Oracle adapter contract stub** (Sprint 25.9): Oracle adapter'ın *gerçek
  implementasyonu yok*; yalnızca ileride uyacağı sözleşme kilitlendi.
  `SQLOracleAdapterCapability` tüm execution flag'lerini (`live`/`driver`/
  `network`/`read_only`/`local_docker`/`remote`/`production`/`oracle`) `False`'a
  zorlar; contract dataclass'ları immutable; adapter deterministik biçimde geçersiz
  girdide `REJECTED`, diğer her durumda `NOT_IMPLEMENTED` döner; result yalnızca
  `sql_sha256` taşır (ham SQL / connection ref / DSN / credential sızdırmaz).
  cx_Oracle / oracledb / SQLAlchemy / JDBC / socket / DSN-TNS-wallet / env-secret
  kullanımı yasaktır ve testlerle kilitlidir. Bununla **Phase 6 (adapter stub'ları)
  kapanır**.
- **SQL Permission Policy Contract** (Sprint 26.0 · Phase 7 başlangıcı):
  backend'in ilk güvenlik/governance sözleşmesi (`backend/app/security/`). Bir SQL
  çalışmadan önce "bu action izinli mi / deny mi / approval mı, neden?" sorusuna
  deterministik cevap veren `SQLPermissionPolicyContract.evaluate()` →
  `ALLOW` / `DENY` / `REQUIRES_APPROVAL` + audit reason code. **Fail-closed**:
  bilinmeyen action/resource, eksik subject/resource, konfigüre edilmemiş policy →
  hep `DENY` (belirsizlikte asla allow yok). Immutable request/result, deny-overrides
  rule precedence, JSON-safe deterministic `to_dict()`. Result hiçbir secret/raw SQL/
  connection string/PII taşımaz (`context` sonuca aktarılmaz). Enforcement engine,
  tenant boundary, RBAC ve AuthN bu sprintte **yok** (26.1–26.11).
- **Tenant / Workspace Boundary Contract** (Sprint 26.1 · Phase 7):
  `backend/app/security/tenant_workspace_boundary.py`. 26.0 "action izinli mi?"
  sorusunu cevaplarken, 26.1 daha kaba olan "bu karar hangi tenant/workspace
  sınırı içinde geçerli?" boyutunu ekler — cross-tenant leakage'a karşı.
  `TenantWorkspaceBoundaryContract.validate()` → `ALLOW` / `DENY` + audit reason
  code. **Fail-closed**: eksik tenant, eksik workspace, tenant mismatch, workspace
  mismatch → hep `DENY` (sınır belirsizse allow yok). Tenant kontrolü workspace'ten
  önce gelir (workspace id'leri tenant'lar arası çakışsa bile cross-tenant geçiş yok).
  Immutable request/result, JSON-safe deterministic `to_dict()`; request'te
  `context` alanı yok, deny'de tenant/workspace echo edilmez (secret/raw SQL/PII
  taşımaz). RBAC/AuthN/AuthZ, persistence, API/UI ve 26.0 ile composition bu
  sprintte **yok**.
- **Read-Only Enforcement Hardening** (Sprint 26.2 · Phase 7):
  `backend/app/security/sql_read_only_enforcement.py`. "Bu SQL gerçekten read-only
  mi?" sorusunu dağınık string check'lerden çıkarıp tek, deterministik,
  contract-first enforcement katmanına bağlar (güvenlik üçgeninin SQL ayağı:
  permission policy / tenant boundary / read-only). `SQLReadOnlyEnforcementContract.
  enforce()` → `ALLOW` / `DENY` + audit reason code (`read_only_select`,
  `empty_sql`, `multi_statement`, `non_select_statement`, `forbidden_keyword`,
  `unsafe_procedure`, `unsafe_data_movement`, `invalid_sql_type`). **Fail-closed**:
  tek-statement SELECT (veya read-only `WITH … SELECT`) dışında her şey DENY.
  Sınıflandırmadan önce SQL **lex edilir** (`_sanitize`): yorumlar sökülür, string
  literal'ler ve çift-tırnaklı identifier'lar maskelenir — sadece *çalıştırılabilir
  kod* taranır. Böylece `SELECT comment FROM t` (kolon adı), `SELECT * FROM "merge"`
  (tırnaklı identifier) ve `SELECT '… DROP …'` (literal) artık yanlış reddedilmez;
  buna karşılık gerçek konumdaki `;` / write verb'ü (klasik `'' ; DROP TABLE t; --`
  injection kuyruğu dâhil) hâlâ yakalanır. `SELECT … INTO` ve CTE içi
  `INSERT/UPDATE/DELETE` her yerde taranır; DDL/`COPY`/`MERGE`/procedure yalnızca
  statement-başı verb olarak. Result **ham SQL taşımaz** — yalnızca `sql_sha256` +
  leading keyword (`normalized_prefix`), JSON-safe `to_dict()`. **Bilinen sınır
  (string katmanı):** fonksiyonla ifade edilen yazma (`SELECT setval(...)`,
  `SELECT lo_export(...)`) write verb'ü içermediğinden ALLOW olur; bunun savunması
  adapter'ın DB-seviyesi read-only session'ıdır (gerçek allowlist/parser 26.3+).
  **PostgreSQL ve Oracle** adapter'larının `validate_read_only_select` gate'i artık
  bu ortak contract'a **delege** eder (cross-adapter divergence kapandı; iki adapter
  aynı SQL'de aynı kararı verir, testle kilitli). Risk classifier (26.3), sensitive/PII policy, audit, approval,
  yeni adapter, gerçek production execution, API/UI ve tenant/RBAC/AuthN bu sprintte **yok**.
- **Query Risk Classifier** (Sprint 26.3 · Phase 7):
  `backend/app/security/sql_query_risk_classifier.py`. Bir SQL sorgusunun *statik*
  (çalıştırmadan) risk seviyesini deterministik sınıflar — **gate değil, sinyal
  üreticisidir** (allow/deny vermez; downstream 26.7 approval / 26.9 limit / audit
  tüketir). `SQLQueryRiskClassifier.classify()` → `risk_level`
  `LOW`/`MEDIUM`/`HIGH`/`CRITICAL` + tetiklenen `signals` (deterministik sıralı,
  deduped): `select_star`, `no_where_filter`, `no_row_limit`, `cartesian_join`,
  `high_join_count`, `side_effecting_function`, `unbounded_result`,
  `invalid_or_unparseable`. **Belirsizlikte yukarı yuvarlar** (fail-closed'un risk
  hâli): boş / non-string / comment-only / non-read → `CRITICAL`. `risk_level` =
  tetiklenen sinyallerin **max** severity'si; hiç yoksa `LOW`. 26.2 ile
  **kompozisyon**: 26.2'nin bilinen sınırı olan fonksiyonla yazma
  (`SELECT setval(...)` / `lo_export` / `pg_terminate_backend` / `dblink` /
  `pg_sleep` …) artık `side_effecting_function` → `CRITICAL` olarak **görünür**
  kılınır (engellenmez) — denylist dosya-okuma/keyfi-SQL/introspection ailelerini de
  kapsar (`pg_read_file`, `pg_ls_*`, `query_to_xml`, `dblink*`, `txid_*`, snapshot).
  Read gate sadece leading keyword'e bakmaz: CTE ardına gizlenen write / `SELECT …
  INTO` / multi-statement, 26.2 read-only contract'ıyla **kompozisyon** sayesinde
  `invalid_or_unparseable` → CRITICAL olur. Heuristic'ler ortak `_sql_text` sanitize'ı
  üzerinde çalışır (literal/yorum içindeki keyword/fonksiyon sinyal tetiklemez).
  Result **ham SQL taşımaz** — `sql_sha256` + leading keyword; JSON-safe `to_dict()`.
  **Bilinen sınır:** parser olmadığından nesting-kör — subquery içi `WHERE`/`LIMIT`
  dış-scan sinyallerini bastırabilir, comma-join cartesian kuralı kırılgandır
  (gerçek çözüm parser/`pg_proc` → sonraki sprint). **Refactor:**
  26.2 ve 26.3 ortak `app/security/_sql_text.py` (sanitize/normalize/leading-keyword)
  helper'ına bağlandı (read-only davranışı değişmedi, testle doğrulandı). **Bilinen
  sınır:** `side_effecting_function` küratörlü/eksiksiz-olmayan bir *denylist*'tir;
  listede olmayan yazan fonksiyon işaretlenmez (gerçek çözüm allowlist / `pg_proc`
  metadata → sonraki sprint). Gerçek parser/EXPLAIN, execution, sensitive/PII
  policy, audit, approval, API/UI, tenant/RBAC/AuthN bu sprintte **yok**.
- **Observability: Canlı Uçtan Uca Trace (Sprint 27.1w)**: 27.0/27.1'in saf
  `EndToEndTrace` sözleşmesi canlı pipeline'a örüldü — HTTP `X-Request-ID`
  arka plan job'ına taşınır (yoksa `req_` önekiyle üretilir), her stage
  `perf_counter` ile ölçülür ve `run_pipeline` çıkışında legacy trace'in
  YANINA `trace_type="end_to_end"` kaydı (7 sabit span: INTENT/RETRIEVAL/
  PROMPT/GENERATION/VALIDATION/SECURITY/EXECUTION; koşmayan stage SKIPPED,
  EXECUTION Faz-1'de hep SKIPPED) emit edilir. `run_pipeline` üç stage
  metoduna ayrıldı (davranış birebir korunur). Trace emisyon hatası pipeline
  sonucunu asla etkilemez; SQL payload'a asla ham girmez (yalnız sha256).
  27.1'den devreden 3 Minor builder düzeltmesi kapatıldı. **Bilinen sınır:**
  ikili emit yalnızca `save_legacy` metodu expose eden trace store'larda
  çalışır (`SQLGenerationPipeline._capture_trace_on_exit`, `_save_trace_safely`
  ile aynı feature-detect dispatch'ini kullanır); production'daki
  `SQLiteTraceStore` ikisini de desteklediğinden tam ikili emit alır, eski
  tekil-`save()` store'lar yalnızca legacy trace görür, e2e kaydı almaz. Yeni
  saf modül: `backend/app/trace/live_trace_assembly.py`. Spec:
  `docs/superpowers/specs/2026-07-06-sprint-27.1w-live-trace-wiring-design.md`.
- **Error Taxonomy v2 (Sprint 27.2):** Hata sınıflandırması artık tek bir
  production kaynağında: `backend/app/errors/` (`ErrorCode` 26 kod,
  `ErrorCategory` 7 kategori, `ErrorDescriptor` registry). Öncesinde taksonominin
  tek resmî tanımı bir test dosyasındaydı ve pipeline'ın gerçekte emit ettiği bir
  koddan (`schema_context_selection_exception`) habersizdi.
- `run_pipeline` sonucu artık `error_code` taşıyor (`ErrorCode | None`).
- **Job/API `error_code` alanı** (Sprint 27.2.1): pipeline'ın ürettiği taksonomi
  kodu artık `jobs.error_code` kolonuna persist ediliyor, `GET /api/jobs/{id}`
  yanıtında dönüyor ve frontend `Job` interface'inde taşınıyor. Beklenmeyen
  (INTERNAL) hatalarda kod `NULL` kalır. `update_job_status` bu sırada dinamik
  SET-clause'a refactor edildi (davranış korundu).
- **User Feedback Capture** (Sprint 27.3): bir SQL üretimine (`job`) dair
  kullanıcı feedback'ini toplayan backend yüzeyi — `backend/app/feedback/`
  (saf `FeedbackVerdict`/`FeedbackCategory` taksonomisi), append-only
  `feedback` tablosu ve `POST /api/jobs/{job_id}/feedback` endpoint'i.
  Öğrenen sistemin tohumu: `27.9` (Feedback Review → Rule Suggestion)
  bunu `get_feedback_for_job` ile tüketecek. Bilinçli olarak backend-only:
  HTTP GET listeleme/admin görünümü (`30.6`), frontend UI (`31.7`) ve
  `rating` alanı bu sprintte kapsam dışı.
- **Query Replay System** (Sprint 27.4): gecmis bir `job`, bugunun kodu ve
  semasiyla **deterministik** olarak yeniden kosturulup (LLM'e gidilmez) o gunku
  `end_to_end` trace baseline'iyla karsilastirilabiliyor. Yeni saf paket
  `backend/app/replay/` verdict taksonomisini ve boyut delta'larini
  (`retrieval`/`validation`/`security`) tasir; `POST /api/debug/jobs/{job_id}/replay`
  sonucu 200 envelope ile dondurur (API key + `debug_endpoints_enabled` gerekir).
  Replay **yan etkisizdir**: hicbir tabloya yazilmaz, yeni trace emit edilmez.
  Dogrulama zinciri `SQLGenerationPipeline.validate_sql` seam'ine ayiklandi;
  uretim davranisi degismedi. Bilincli kapsam disi: LLM'li tam re-run, replay
  kaliciligi, toplu replay, frontend UI ve 27.1w oncesi joblar icin legacy
  baseline fallback'i.

**Bilinen sınır:** Sprint 27.2 öncesi kaydedilmiş trace satırları v1 kod adlarını
taşır ve `?error_type=` filtresiyle eşleşmez; geliştirme veritabanı migrate edilmedi.

### Changed
- **KIRICI:** v1 hata string'lerinin bir kısmı yeniden adlandırıldı:
  `schema_pruning_error` → `schema_pruning_failed`, `schema_pruning_exception` →
  `schema_pruning_crashed`, `schema_context_selection_exception` →
  `schema_context_selection_crashed`, `sql_generation_failed` →
  `sql_generation_exhausted`, `validation_error` → `semantic_validation_failed`,
  `execution_error` → `execution_failed`.
- **KIRICI:** `unsafe_sql` üç ayrı koda bölündü —
  `unsafe_dangerous_function`, `unsafe_dml_keyword`, `unsafe_sandbox_rejected`.
  Öncesinde üç farklı güvenlik reddi tek kodda birleşiyordu ve ayrım yalnızca
  tipsiz bir `details.reason` string'inde yaşıyordu.
- **KIRICI:** `semantic_validation` artık bir error type DEĞİL, yalnız bir stage.
- Execution taksonomisi (`sql_execution_errors.py`) aynı registry'ye katıldı;
  `type` ve `code` alanları artık ortak bir kelime dağarcığı paylaşıyor.
- `classify_sql_error` kontrol sırası düzeltildi: parse/syntax kontrolü artık
  column/table'dan önce. Öncesinde içinde "column" geçen her parse hatası
  `missing_column` oluyordu ve `syntax_error` pratikte ulaşılamazdı.
- `live_trace_assembly` artık kod listesi tutmuyor; INPUT/RETRIEVAL setleri
  registry kategori sorgusundan türetiliyor.
- **Arka plan: Canlı Şema Sinapsı (Faz 1)** (2026-07-02 · ara iş, sprint dışı):
  `SpaceSpiderweb.vue`'daki jenerik geodesic wireframe tünel, gerçek veritabanı
  şemasından beslenen sinaptik ağ katmanıyla değiştirildi — node'lar bağlantılı
  tablolar (`graphSelection.selectGraphData` yeniden kullanımı, üst sınır 150),
  hatlar gerçek FK ilişkileri; sinaps hatları boyunca kesintisiz tek sinyal
  darbesi (cyan; biri biter bitmez yenisi başka bir noktadan başlar), en
  bağlantılı ~%10 tablo amber hub. Yerleşim
  deterministik (tablo-adı hash seed'li force layout — her açılışta aynı
  takımyıldız); şema yoksa YA DA şema isteği 6 sn içinde yanıtlanmazsa prosedürel fallback ağ (arka plan asla boş kalmaz). Yıldız katmanı ve kara delik
  warp senkronu korunur (uniform sözleşmesi devralındı). `prefers-reduced-motion`
  → darbeler kapalı. Faz 2 kancası `fireSignal(tableNames)` expose edildi (canlı
  sorgu tetiklemesi ileride). Saf modüller TDD ile: `frontend/src/utils/
  {seededRandom,synapseNetwork,synapseLayout,synapsePulse}.ts` +
  `frontend/tests/*.test.ts`. Spec: `docs/superpowers/specs/
  2026-07-02-living-schema-synapse-background-design.md`.

### Fixed
- **Şema ilişki graph'ı görünürlük düzeltmesi** (2026-07-02 · ara fix, sprint
  dışı): `SchemaManager.vue`'daki D3 graph'ı top-N hub seçimini *izole tablolar
  dahil tüm tablolar* üzerinden yapıp yalnızca iki ucu da seçimde kalan
  edge'leri çizdiğinden, varsayılan `maxNodesLimit=5` ile örnek şemada 93
  ilişkinin yalnızca **3'ü** görünüyordu; "limitsiz" seçeneği ise 2175 tablonun
  2073'ü izole olmasına rağmen hepsini render edip tarayıcıyı donduruyordu
  (`docs/TECH-DEBT.md` #2'nin kökeni). Seçim mantığı saf
  `frontend/src/utils/graphSelection.ts` modülüne çıkarıldı: izole tablolar hiç
  çizilmez, limit yalnızca bağlantılı tablolar arasında uygulanır, varsayılan
  `0 = tüm bağlantılı tablolar` oldu (örnek şemada 102 tablo + **93/93**
  ilişki). Graph paneline render istatistiği rozeti eklendi; edge objeleri D3
  `forceLink` mutasyonuna karşı kopyalanıyor; ilişki hiç yoksa boş-durum mesajı
  artık doğru tetikleniyor. Test: `frontend/tests/graphSelection.test.ts`
  (8 test, `node --experimental-strip-types`). Kalan borç (çok büyük *bağlantılı*
  graph'lar için WebGL/virtualized render) `docs/TECH-DEBT.md` #2'de.
- **`api.ts` hata mesajı çıkarımı** (Sprint 27.2.1): frontend backend'in
  envelope'unda olmayan `errData.detail` alanını okuduğu için RAG search,
  business-rule ve SQL-history indeksleme hatalarında gerçek mesaj sessizce
  düşüyor, kullanıcı hep hardcoded fallback görüyordu. Yeni
  `extractApiErrorMessage` helper'ı `{"error":{"message"}}` envelope'unu okuyor.

### Known limitations
- **PostgreSQL adapter yalnızca local Docker'da çalışır** (`backend/app/evaluation/postgres_adapter.py`):
  Sprint 25.8 ile read-only `SELECT` execution **yalnızca local Docker** ortamında
  açıldı; live/remote/production capability'leri hâlâ hard-False'tur ve hiçbir
  bağlantı orchestrator'a wire edilmediği için varsayılan davranış `NOT_IMPLEMENTED`
  olarak inert kalır. Production-grade gerçek execution Phase 10 (29.1)'de.
- **Oracle adapter henüz hiçbir sorgu çalıştırmaz** (`backend/app/evaluation/oracle_adapter.py`):
  Sprint 25.9 yalnızca sözleşme stub'ıdır; gerçek Oracle execution (driver, DSN/TNS,
  wallet, read-only/EXPLAIN) Phase 10'da (29.3 adapter, 29.4 Docker/test harness).
- Feedback-loop / öğrenen sistem çıktıları (Trace Mining, Pending Rules,
  Value Index, Feedback UI) henüz yok; minimal ilk adımı (`27.9 Feedback Review →
  Rule Suggestion`) Phase 8 planına eklendi (`docs/PLANNED-SPRINTS.md`).

---

## [1.0.0] — 2026-06-05 · Controlled Production Baseline

Patlamayan, debug edilebilen ve ölçülebilen ilk production baseline'ı.
Hedef "çok akıllı sistem" değil; her kararı izlenebilir güvenli sistemdi
(eski tasarım notu: `docs/archive/v1-production-plan.md`).

### Added
- **Release hazırlığı** (Sprint 16–19): production runbook ve smoke gate, V1
  release candidate gate, RC doğrulama kanıtı ve release readiness ilanı
  (#78–#81).
- **Observability** (Sprint 18): request logging, request correlation,
  performance telemetry, readiness/startup diagnostics, startup config
  doğrulama gate'i (#73–#77).
- **API yüzeyi dondurma** (Sprint 17): API surface envanteri + OpenAPI snapshot,
  hata yanıtı ve response envelope şeması dondurma, API key/debug erişim
  sözleşmesi, HTTP status semantiği, sözleşme yeniden üretim araçları (#68–#72).
- **Runtime altyapısı** (Sprint 16): `pydantic-settings` ile merkezî runtime
  ayarları, güvenli health diagnostics, startup validation warnings, backend
  Docker baseline + container runtime smoke testi, ortam değişkeni sözleşmesi,
  release verification checklist (#59–#67).
- **Trace ve debug** (Sprint 14–15): `TraceStore` arayüzü + `InMemoryTraceStore`
  ve `SQLiteTraceStore`, debug trace API endpoint'leri (strict DTO, validation,
  credential redaction); Golden NL2SQL Eval Harness, kolon-düzeyi eval
  kontrolleri, eval failure reporting (#52–#58).
- **Read-only SQL execution guard'ları** (Sprint 12): read-only execution
  sandbox, query timeout, row limit guard, sonuç şekli doğrulama ve execution
  hata taksonomisi (#47–#50).
- **API sözleşmeleri** (Sprint 11): standart API hata yanıtı, pagination/query
  parametre sözleşmesi, job filter/sort sözleşmeleri (#42–#46).
- **Graph pruning mimarisi**: kabul testleriyle kilitlenen graph budama
  mimarisi; `GraphBackend` arayüzü ve `NetworkXGraphBackend` (#51).

### Changed
- Şema budama (graph traversal/hub/budget) mantığı `schema_pruner`'dan ayrı
  `schema_graph/` backend modüllerine taşındı (Sprint 2 refactor).

### Fixed
- SQL guardrail'ı: tehlikeli komut fonksiyonlarının reddi, guardrail hatasında
  üretilen SQL'in sanitize edilmesi, pipeline guardrail hatasında fail-fast
  davranışı (#12–#16).

---

## [0.x] — Temel altyapı (2026-05-20 → 2026-05-25) · Sprint 2–4

### Added
- İlk konsol/pipeline iskeleti: schema lexicon, trace store ve SQL validator;
  TextNormalizer, tokenizer ve generic token yönetimi, gerçek RAG skor eşiği ve
  tracing, CandidateStore + sinyal toplama, hibrit synonym repository, mini
  golden query ve regression testleri (Patch 0–5).
- Graph modülü ayrıştırması: `schema_graph/backend.py`,
  `schema_graph/networkx_backend.py`, traversal policy (Sprint 2).
- LLM provider sınırı: provider arayüz sözleşmesi, SQL generation request/response
  sözleşmesi, deterministik fake provider seam, manuel NVIDIA provider adaptörü
  (#4–#7).
- SQL dialect doğrulama sözleşmesi ve read-only guardrail sözleşmeleri (#9–#13).
- CI'da smoke eval; eval sözleşmelerinin kilitlenmesi (#1–#3).

---

[Unreleased]: https://github.com/furkanatesc/SQL-Generator/compare/main...HEAD
