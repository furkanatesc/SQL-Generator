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

## [Unreleased] — Sprint 20 → 27.10 · retrieval/prompting/execution + Phase 7 Security & Governance + Phase 8 Observability (2026-06-05 → günümüz)

v1 baseline'ı sonrası retrieval, prompting ve execution-accuracy altyapısının
sözleşme (contract) odaklı geliştirilmesi (Sprint 20–25, çoğu contract/stub
seviyesinde), ardından **Phase 7 (Security & Governance, 26.0–26.11)** güvenlik
contract'ları ve **Phase 8 (Observability & Debuggability, 27.0–27.10)** — canlı
trace, hata taksonomisi, feedback, replay, debug bundle, metrics, dashboard
gerçek debug-gated endpoint'leriyle ve **per-release accuracy regression gate**
ile kapanır. Durum için `ROADMAP.md`'deki tabloya bakın.

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
- **Sensitive Table / Column Policy** (Sprint 26.4): beyan-tabanlı (declaration-driven)
  hassas tablo/kolon gate'i — `evaluate()` → ALLOW/DENY/REQUIRES_APPROVAL + eşleşen
  tablo/kolon ve hassasiyet seviyesi sinyali. Hibrit: explicit beyan = sound, SQL'den
  tablo/kolon çıkarımı = best-effort. Immutable, secret-free.
  `backend/app/security/sql_sensitive_data_policy.py`.
- **PII / PHI Detection Contract** (Sprint 26.5): heuristik PII/PHI **detector**
  (sinyal, gate değil) — kategori + PII/PHI veri-sınıfı + confidence. 3 katman:
  declared = sound; identifier-isim + literal-değer/Luhn = best-effort. Secret-free
  (ham değer sızmaz). `backend/app/security/sql_pii_phi_detection.py`.
- **Audit Event Contract** (Sprint 26.6): deterministik, secret-free audit kaydı +
  tamper-evident SHA-256 hash-chain. 26.0–26.5 sonuçlarını tek immutable `AuditEvent`'e
  normalize eden 6 builder; `verify_chain` mutation/reorder/insert/delete yakalar
  (integrity-evident; non-repudiation Phase 13). `backend/app/security/audit_event.py`.
- **Approval Workflow Contract** (Sprint 26.7): saf deterministik approval state machine
  (I/O & clock yok, time/id caller-supplied, frozen). PENDING + terminal durumlar;
  fail-closed quorum N-of-M + SoD (requester≠approver) + duplicate-vote guard +
  single-reject veto + terminal immutability; audit interlock.
  `backend/app/security/approval_workflow.py`.
- **Prompt-Injection / NL Abuse Defense** (Sprint 26.8): Phase 7'nin **doğal dili**
  (SQL değil) inceleyen ilk contract'ı — kaynak-duyarlı detector (6 `InjectionCategory`,
  DIRECT/INDIRECT kaynak, confidence + ALLOW/REVIEW/BLOCK disposition), NFKC normalize +
  **Türkçe-güvenli** obfuscation sinyali (homoglyph yalnız Cyrillic/Greek). Audit
  interlock. OWASP LLM01:2025. `backend/app/security/prompt_injection_defense.py`.
- **Result-Set Privacy & Row/Size Limits** (Sprint 26.9): **post-execution** sonuç
  kümesi üzerinde hibrit — limit **GATE** (ALLOW/TRUNCATE/DENY: `max_rows`/`max_bytes`/
  `max_columns` + `truncate_allowed`) + advisory PII/PHI privacy **sinyali** (26.5
  value-scan reuse). Audit interlock. `backend/app/security/result_set_privacy_limits.py`.
- **Connection Credential Vault** (Sprint 26.10): saf, secret-free governance contract —
  bir call context'in bir connection `secret_ref`'i **resolve** edip edemeyeceğine karar
  veren gate + ham-secret sızıntısı advisory sinyali. Ham parola/connection-string/token
  asla tutulmaz/saklanmaz/çözülmez; yalnız *referans* + *karar*. 6 boyut deterministik
  öncelik, audit interlock, PEP 562 lazy export (driver-isolation korunur).
  `backend/app/security/connection_credential_vault.py`.
- **Policy / Security Eval** (Sprint 26.11 · Phase 7 sonu): 26.0–26.10 güvenlik
  contract'ları üzerinde saf, secret-free **meta-evaluation harness**
  (`backend/app/evaluation/` — `app.security` driver-free kalır). 11 projector +
  enum-purity invariant, 22 blessed golden case, coverage introspection, PASS/WARN/FAIL
  gate. **Phase 7 (Security & Governance) burada kapanır.** *(26.4–26.11 local
  squash-merge'ler → main; son commit `69d86c3`)*
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
- **Debug Bundle Export** (Sprint 27.5): bir `job`'ın tüm debug bağlamını (o günkü
  `end_to_end` trace + REDAKTE SQL/attempts/validation_errors + 27.4 replay'i **inline**
  koşturarak + seçilen şema özeti + sürüm metadata) tek JSON envelope'da toplayan, hata
  raporuna eklenebilir, **yan etkisiz** export. `GET /api/debug/jobs/{job_id}/bundle`
  (API key + `debug_endpoints_enabled` ile gated). İki trace ayrımı: `end_to_end`
  secret-free (hash-only) → trace+schema bölümleri; debug trace → redakte SQL bölümü.
  Saf `backend/app/debug_bundle/` + `bundle_service.py`. (PR #143)
- **Metrics Contract** (Sprint 27.6): bir zaman penceresindeki `end_to_end` trace'leri
  toplayan **versiyonlu** metrik raporu — hacim&sonuç (`terminal_status` dağılımı +
  `success_rate`), hata taksonomisi (`by_code`/`by_category`, bilinmeyen→`unknown`),
  latency (**nearest-rank** p50/p95/p99), stage kırılımı. `GET /api/debug/metrics`
  (debug-gated, 200 envelope). Metrikler hassas değil → redaksiyon yok; boş pencere →
  200 + sıfırlar. Saf `backend/app/metrics/` (`app.errors` izinli) + `metrics_service.py`
  (bounded fetch + `truncated`). (PR #144)
- **Admin Observability Dashboard Backend** (Sprint 27.7): 27.6 metrik snapshot'ini
  **zaman-serisi bucketing** (hour/day floor, nearest-rank p95, en-yeni-N cap) + **top
  hatalar** + **feedback özeti** + **son aktivite** ile tek kompozit JSON'da birleştiren,
  **yan etkisiz** `GET /api/debug/dashboard` (debug-gated, 200 envelope). Saf
  `backend/app/dashboard/` **27.6 `compute_metrics`'i reuse eder** (span'leri yeniden
  okumaz; purity: yalnız stdlib + `app.errors` + `app.metrics`, `app.trace.*` yasak) +
  `dashboard_service.py` (**tek** trace fetch → metrics+timeseries+recent + yeni
  `database.list_feedback`). Determinist (`datetime.now()` yok — var olan damgalar
  floor'lanır); sessiz kesme yok (`truncated`/`timeseries_truncated`). (PR #145)
- **Cost & LLM Usage Telemetry** (Sprint 27.8): bir zaman penceresindeki `end_to_end`
  trace'lerin **GENERATION span**'lerinden LLM kullanımını (request sayısı, prompt/
  completion/total token, latency, finish_reason) toplayan ve **konfigüre edilebilir
  fiyat tablosuyla** tahmini maliyet üreten, **yan etkisiz** `GET /api/debug/llm-usage`
  (debug-gated, 200 envelope). Yeni pipeline enstrümantasyonu YOK — kullanım verisi
  27.1w'den beri GENERATION span `detail`'inde (`provider_id/model_id/finish_reason/
  prompt_tokens/completion_tokens/total_tokens` + `duration_ms`) zaten yakalanıyor. Saf
  yaprak paket `backend/app/llm_usage/` (`contract` + toleranslı `pricing` + `compute`;
  purity **yalnız stdlib** — `app.trace.*`/`app.errors` asla) + adaptör
  `app/llm_usage_service.py` (tek trace fetch + fiyat tablosu `get_config('llm_pricing')`
  JSON'undan; geçersiz → boş tablo). Yanıt: totals + model/provider kırılımı + latency
  (nearest-rank p50/p95/p99) + finish_reason dağılımı + zaman-serisi. Maliyet =
  `token × per-1M fiyat`; fiyatsız model → cost `null` + `models_missing_price` +
  `unpriced_request_count` (sessiz boşluk yok). Kullanım/maliyet hassas değil →
  redaksiyon yok. Determinist; `truncated`/`timeseries_truncated`; boş pencere → 200.
  **Bilinen sınır (TECH-DEBT §9):** trace tek GENERATION span taşıdığından retry'lı
  işlerde token/maliyet eksik-sayımı. (PR #146)
- **Feedback Review → Rule Suggestion** (Sprint 27.9): kullanıcı feedback'ini (27.3
  `feedback` tablosu + 27.7 `list_feedback`) aday `{natural_query → SQL}` kural/örnek
  önerisine çeviren, **yan etkisiz** `GET /api/debug/rule-suggestions` (debug-gated,
  200 envelope). İki kind: correction (`verdict=incorrect` + dolu `corrected_sql`) /
  confirmation (`verdict=correct` + dolu job `result_sql`); ineligible sebep önceliği
  `missing_job > missing_natural_query > missing_sql`. Saf yaprak paket
  `backend/app/rule_suggestions/` (frozen contract + SIRALI `to_payload`; saf
  `classify_item`/`compute_rule_suggestions` — dedup `(natural_query, suggested_sql,
  kind)`, support-count ranking, `by_kind`/`by_category` kırılımları; purity **yalnız
  stdlib**, `app.feedback`/`app.trace.*` asla) + adaptör `app/rule_suggestions_service.py`
  (`list_feedback`+`get_job` korelasyonu, job-cache, `scan_cap=10000`). Bilinçli olarak
  yalnızca **ÖNERİR**: insan `POST /api/rag/index/sql-history` ile ayrıca onaylar/
  indeksler; redaksiyon YOK (amaç ham SQL'i onaya sunmak). Bilinçli kapsam dışı:
  onay/persistence-state (idempotency yok), LLM/semantik genelleme + synonym türetme
  (yalnız literal eşleşme), `scan_cap` üstü DB-side tam-populasyon, frontend UI. (PR #147)
- **Per-Release Accuracy Regression Gate** (Sprint 27.10 · Phase 8 sonu): mevcut
  deterministik golden eval raporunu (`app.eval.run_eval --profile golden`)
  tüketen, **yan etkisiz** CLI/CI regresyon gate'i — debug endpoint **değil**.
  Saf yaprak paket `evals/regression_gate.py` (`compare_regression` + baseline
  helper'ları) + kirli CLI `evals/regression_gate_cli.py` (gate çalıştırma +
  `--update-baseline`, exit `0`/`1`/`2`) + seeded append-only
  `evals/baselines/history.json` (`v1.0.0`) + `backend-ci.yml`'e yeni regresyon-gate
  adımı. Karşılaştırma `baseline ∩ current` (ortak case) kümesi üzerinde: per-case
  **sıfır-tolerans** birincil (herhangi bir ortak case geçerken düşerse regresyon) +
  aggregate pass-rate ikincil; reason önceliği per-case > aggregate > bootstrap;
  drift (case kümesi değişimi) **bilgi amaçlıdır**, regresyon sayılmaz. Boş/yok
  baseline → **bootstrap yeşil** (exit 0 — ilk sürüm için karşılaştıracak bir şey
  yok). Full suite 2400 passed/9 skipped. **Bilinçli kapsam dışı:** gerçek-LLM
  accuracy (deterministik sahte pipeline üzerinde çalışır → kod-kaynaklı
  regresyonu yakalar, model doğruluğunu değil; subsystem C execution harness'ı
  ayrı kalem), debug endpoint, sürüm etiketinin git-tag'den runtime'da otomatik
  okunması (`--version` operatör tarafından elle verilir), CI'da baseline'ın
  otomatik güncellenmesi (`--update-baseline` release'te elle çağrılmalı),
  frontend UI. **Bununla Phase 8 (Observability & Debuggability) kapanır.**
  (PR #148)
- **Large Schema Benchmark Suite** (Sprint 28.0 · Phase 9 başlangıcı): yeni
  `backend/benchmarks/` paketi (dev/CI aracı, `evals/`'in kardeşi) — hiçbir
  `app/` dosyası değişmedi, davranış korunur. Saf çekirdek: seeded sentetik
  şema üreteci (`schema_generator.py`, `random.Random(seed)` ile
  100/500/1000/2000 tablo ölçekleri), frozen metrik sözleşmesi
  (`bench_contract.py`), 4 REUSED prodüksiyon hedefi için girdi/çıktı-türevli
  determinist metrik çıkarıcılar (`bench_metrics.py`: `from_legacy_schema`
  validator, `find_join_paths`, `detect_implicit_relationships`,
  `select_schema_context`) ve 27.10 desenini izleyen `compare_benchmark`
  (`bench_compare.py`). Kirli kenar: `bench_runner.py` (enjekte edilen clock
  ile ölçer; `wall_ms` yalnızca **bilgi amaçlı**, asla gate'lenmez) +
  `bench_cli.py` (`--gate`/`--update-baseline`, exit `0`/`1`/`2`). Seeded
  committed baseline `baselines/history.json` (1 kayıt, 4 hedef × 4 ölçek = 16
  metrik). Yeni source-scan purity guard testi
  (`backend/tests/benchmarks/test_benchmarks_purity.py`) dört saf modülün
  clock/datetime/unseeded-random içermediğini kilitler. **Bilinçli kapsam
  dışı (→ 28.1+, `docs/TECH-DEBT.md` §12):** iç patlama sayaçları
  (`dfs_visits`/`fuzzy_comparisons`), CI perf-gate kablolaması,
  NetworkX/`schema_graph` pruner benchmark'ı, embedding/RAG retrieval
  benchmark'ı (→ 28.8), frontend UI. **Bununla Phase 9 (Large Schema
  Production Scale) başlar.** (PR #150)
- **Schema Graph Performance Profiling** (Sprint 28.1): opsiyonel sıfır-ek-yük
  `ProfileProbe` (`backend/app/schema/profiling.py`) üç prodüksiyon seam'ine
  (`find_join_paths`, `detect_implicit_relationships`, `select_schema_context`)
  iplendi — davranış korunur, `probe=None` byte-for-byte aynı çıktı üretir,
  mevcut `tests/schema` yeşil kalır (`+N/-0`). Benchmark v2: determinist iç
  patlama sayaçları (`dfs_visit`, `adjacency_edge`, `path_recorded`,
  `pair_iteration`, `fuzzy_comparison`, `rule3_scan`, `table_scan`,
  `column_scan`, `related_expansion`) her hedefin determinist metriklerine
  birleşir. Şema üreteci near-miss kolonlar kazandı (Rule-2 fuzzy artık
  egzersiz ediliyor). Yeni **5. hedef** `graph_backend`:
  `NetworkXGraphBackend`'i (build + pagerank + shortest_path)
  `to_legacy_dict` reuse'iyle egzersiz eder — çıktı-türevli tam-sayı
  metrikler (`graph_nodes`/`graph_edges`/`sp_*`) + `wall_ms`; pagerank float
  **ASLA gate'lenmez**. Baseline `large_schema_benchmark_v2`'ye yükseldi
  (gate'lenen ölçekler 100/500/1000; 2000 manuel referans). Yeni CI
  perf-gate adımı (`backend-ci.yml`: `bench_cli --gate --scales
  100,500,1000`). **Prodüksiyon davranış değişikliği YOK** (probe
  opsiyonel/guard'lı). **TECH-DEBT §12 ÇÖZÜLDÜ:** iç patlama sayaçları, CI
  perf-gate kablolaması, NetworkX/graph-backend benchmark'ı. **Açık
  kalanlar:** embedding/RAG retrieval benchmark'ı (→ 28.8), `GraphPruner`
  candidate/policy derin entegrasyonu + pruner iç probe'u, `scipy`
  eksikliği (pagerank `{}`'e düşer, gate etkilenmez), `bench_contract.py`/
  `bench_cli.py` docstring/help kozmetik doc-sync borcu. (PR #151)
- **Join Path Explosion Control** (Sprint 28.2): `find_join_paths`'in
  kombinatoryal DFS patlamasını iki katmanla sınırlayan ve yeni
  `JoinPathSearchResult` sözleşmesini döndüren **tek-API kırılımı** (13
  çağrı noktası `.paths`'e taşındı). **Katman 1 — çıktı-koruyan
  branch-and-bound:** ters-BFS `hop` mesafelerinden admissible bir derinlik
  sınırı (`_hop_distances`) + kept-set dominance pruning (optimistic
  tamamlama prefiksinde kesin `>`); **çıktı byte-for-byte korunur** —
  pruning yalnızca ziyareti keser, brute-force denklik testiyle guard'lı.
  **Katman 2 — determinist güvenlik kemeri:** `node_budget` (keyword-only,
  `DEFAULT_JOIN_PATH_NODE_BUDGET = 200_000`); taşmada DFS determinist
  durur ve `budget_truncated=True` işaretler. `select_schema_context` yeni
  `join_search_truncated: bool = False` alanı kazandı (çift üzerinde
  OR'lanır) + opsiyonel `node_budget` passthrough — non-breaking. Benchmark
  v3 (`large_schema_benchmark_v3`, gate'lenen ölçekler 100/500/1000)
  join_paths hedefinde ölçülen düşüş: `dfs_visit` 205→5 / 747→6 / 2653→6;
  `adjacency_edge` (probe) 368→19 / 1452→186 / 5264→375; yeni
  `branches_pruned` 15/180/369. Çıktı-türevli metrikler **değişmedi**
  (`paths_found_total`=2, `path_recorded`=2, `pairs_with_path`=2 tüm
  ölçeklerde) — çıktı korumasının kanıtı. Gate'lenen ölçeklerde
  `join_budget_truncated` yok; CI perf-gate yeşil. **Bilinçli kapsam dışı
  (TECH-DEBT §12):** ağırlıklı/maliyet-tabanlı path scoring + hub-penalty
  (`graph_traversal.py`'deki "future work" yorumu AÇIK kalır — 28.2
  yalnızca enumerasyonu sınırlar, scoring'i değil), `GraphPruner`
  candidate/policy derin entegrasyonu (§12.5 hâlâ AÇIK), empirik/adaptif
  budget tuning (sabit 200_000 kullanılır), frontend `maxNodesLimit`
  kalıcı çözümü (§2, Phase 12). (PR #152)
- **Table Selection Cost Model** (Sprint 28.3): `select_schema_context`'in
  hardcoded additive relevance skoru + düz top-K'sini **config-driven
  benefit-vs-cost budget modeliyle** değiştirdi. Yeni saf
  `app/schema/table_selection_cost.py`: frozen `TableSelectionCostModel`
  (named relevance ağırlıkları = eski magic number'lar + cost ağırlıkları
  `w_base`/`w_col`/`w_fk` + `cost_budget`), `table_cost() = w_base +
  w_col*columns + w_fk*fks`, `fk_counts()` (source-side), toleranslı
  `from_config()` (27.8 `llm_pricing` deseni). `select_schema_context`
  enjekte edilen `cost_model=DEFAULT_COST_MODEL` parametresi kazandı
  (saf yaprak korunur; `probe`/`node_budget` değişmedi). Benefit artık
  model ağırlıklarıyla skorlanır — kalan magic number yok. **Seçim:**
  exact-match focus tabloları önce garanti edilir, kalanlar `cost_budget`
  altında benefit-density (`benefit/cost`) **greedy** ile eklenir
  (skip-and-continue), `max_tables` ikincil sert tavan. **Şeffaflık:**
  `SelectedTable.cost`, `SchemaContextSelection.total_cost`/
  `cost_budget`/`budget_exhausted`. Kirli config yükü `sql_pipeline.py`'de:
  config anahtarı `table_selection_cost_model` → `from_config` → enjekte;
  yoksa `DEFAULT_COST_MODEL`. Muhafazakâr varsayılan `cost_budget=30.0`
  golden şema üzerinde kalibre edildi (ölçülen max `total_cost`=25.0);
  golden eval yeşil, fixture kürasyonu **gerekmedi**. Benchmark v4
  (`large_schema_benchmark_v4`): `context_selection` cost modelini yansıtır
  (scale 100 `selected_tables_total` 67→61); **`join_paths` metrikleri
  v3'e göre değişmedi** (`dfs_visit` 5/6/6, `branches_pruned`
  15/180/369) — cost modelinin join-path katmanını etkilemediğinin kanıtı.
  Gate yeşil. **Bilinçli kapsam dışı:** ilişki-güven-ağırlıklı komşu
  benefit'i (→ 28.4; 28.3 düz `explicit_neighbor`/`implicit_neighbor`
  20/10 ağırlıklarını yalnızca cost modeline taşıdı), token-tabanlı
  gerçek maliyet (serialize footprint) — kolon-sayısı proxy'si kullanılır,
  gerçek 0/1-knapsack optimalliği (deterministik greedy kullanılır),
  frontend `maxNodesLimit` kalıcı çözümü (§2, Phase 12). (PR #153)
- **Relationship Confidence Scoring** (Sprint 28.4): `TableSelectionCostModel`'in
  28.3'te taşıdığı **düz** `explicit_neighbor`/`implicit_neighbor` (20.0/10.0)
  ağırlıklarını tek bir `neighbor_base: float = 20.0` ile birleştirdi; komşu
  benefit'i artık **çarpımsal**: yeni saf `neighbor_benefit(rel_confidence,
  model) = neighbor_base × (conf if conf is not None else 1.0)`.
  `select_schema_context`'teki EXPLICIT/CUSTOM/IMPLICIT komşu genişletmesi
  artık `neighbor_base × effective_confidence` ile skorlanıyor (explicit/
  custom ilişki `confidence=None` → 1.0, implicit ilişki 0.60–0.90
  aralığında ölçülü güven); `IMPLICIT_FUZZY` komşular yeni
  `include_fuzzy_neighbors: bool = False` ile **opt-in** genişliyor
  (varsayılan kapalı). Güven artık tek trust sinyali — reason etiketleri
  tip-tabanlı kalıyor (stabil prefix), tip-ağırlık çifte-sayımı yok.
  `probe`/`node_budget`/`cost_budget`/seçim/join-path/fallback davranışı
  **DEĞİŞMEDİ** — güven yalnızca komşu benefit'ini etkiliyor. Muhafazakâr
  `neighbor_base=20.0` seçimi mevcut fixture'larda **davranış-koruyucu**
  (golden şemanın 6 kenarı hepsi explicit conf=None → `20×1.0=20` = eski
  `explicit_neighbor`); golden eval yeşil, fixture kürasyonu **gerekmedi**.
  **Benchmark: versiyon bump gerekmedi** — `context_selection` metrikleri
  committed `large_schema_benchmark_v4` baseline'ıyla **byte-identical**
  (sentetik şema yalnız explicit-FK içeriyor → komşu benefit'i
  etkilenmedi); gate yeşil (exit 0), `join_paths`/`implicit_fk` metrikleri
  dokunulmadı. **TECH-DEBT §12.13 ÇÖZÜLDÜ.** Full suite 2490 passed/9
  skipped. (PR #155)
- **Missing Foreign Key Inference v2** (Sprint 28.5): `detect_implicit_relationships`'i
  (`app/schema/implicit_relationships.py`) **PK-aware** hale getirdi. Yeni saf
  `resolve_target_key(table) -> str | None`: tek-kolonlu deklare PK
  (`ColumnSchema.primary_key`/`TableSchema.primary_key_columns`) → o kolon;
  composite PK (2+ deklare kolon) → `None`; deklare PK yoksa `"id"` sonra
  `"<singular_table>_id"` konvansiyon fallback'i; hiçbiri yoksa `None`. Rule 1
  (`singular_table_id_pattern`, conf 0.90) ve Rule 2 (`fuzzy_prefix_to_table_match`,
  IMPLICIT_FUZZY conf 0.75/0.65) artık hardcoded `"id"` yerine
  `resolve_target_key(tgt)`'i hedefliyor — **recall**: `id` olmayan PK'li
  tablolarda ilişki artık yakalanıyor. Rule 3 (`exact_non_generic_column_match`,
  conf 0.60) artık YALNIZ kaynak kolon adı hedefin çözülmüş anahtarına eşitse
  tetikleniyor — **precision**: PK olmayan bir kolona rastgele isim-eşleşmesiyle
  kurulan spurious FK kenarları düştü. Confidence değerleri ve `reason`
  string'leri **korundu** (benchmark `derive_implicit_fk_metrics` bucketing
  etkilenmedi); `raw["target_key"]` yeni alan eklendi. Production
  (`schema_manager.py`) çıkarımı iyileşir; schema-only ve deterministik kalır.
  **Benchmark v5** (`large_schema_benchmark_v5`): `implicit_fk` hedefinde
  `rule3_exact` 461/13024/56449 → **0** (scale 100/500/1000) — v1 on binlerce
  spurious non-key kenar çıkarıyordu; `implicit_rels_found` artık yalnız
  rule1+rule2 (92/730/1472). **`join_paths`/`context_selection`/`graph_backend`
  v4'e göre BYTE-IDENTICAL** (`select_schema_context`/`find_join_paths` explicit
  FK üzerinde çalışır, implicit-detection çıktısını tüketmez — coupling yok).
  Gate yeşil (exit 0). **Bilinçli kapsam dışı** (TECH-DEBT §13):
  type-uyumluluk sinyali/gate, config-driven eşikler (confidence/fuzzy-ratio/
  generic-liste hardcoded kalır), unique-ama-PK-olmayan hedefler (PK-only
  tasarım), composite-PK FK çıkarımı (tek-kolon PK'ye odaklanılır), veri
  örneklemesi/value-overlap/cardinality (schema-only kalır). Full suite 2501
  passed/9 skipped. (PR #156)
- **Schema Cache Invalidation** (Sprint 28.6): `SchemaManager.load_schema`'nın
  eski `db_type`-only okuma predikatını içeriğe duyarlı bir fingerprint'le
  değiştirdi. Yeni saf `app/schema_cache_fingerprint.py`:
  `SCHEMA_CACHE_VERSION = "v1"` + `compute_cache_fingerprint(*, db_type,
  hidden_tables_raw, hidden_columns_raw, embedding_model,
  cache_version=SCHEMA_CACHE_VERSION) -> str` — girdileri `\x1f` ayracıyla
  birleştirip (None → `""`) sha256 alır; stdlib-only, deterministik.
  `load_schema` artık lock içinde en başta güncel fingerprint'i hesaplıyor
  (embedding model ucuz okunuyor, build tetiklenmiyor), cache'teki
  `cache_fingerprint`'le karşılaştırıyor; uyuşmazlık/eksiklikte yeniden
  çıkarım yapılıyor. Eski `db_type`-only kontrol yeni fingerprint'e dahil
  (subsumed). Yazma payload'ı yeni `cache_fingerprint` alanını kazandı.
  Lock/cache-stampede/deepcopy/RAG-indexleme/ilişki-dressing **DEĞİŞMEDİ**.
  **Etki:** `hidden_tables`/`hidden_columns` config drift'i ve
  embedding-model değişikliği artık cache'i otomatik invalidate ediyor;
  fingerprint'siz eski bir cache bir kez yeniden çıkarılıp fingerprint'li
  olarak yeniden yazılıyor; `SCHEMA_CACHE_VERSION` bump'ı tüm cache'leri
  invalidate ediyor. Self-contained — yeni bir DB sorgusu YOK. **Bilinçli
  kapsam dışı** (TECH-DEBT §14): ham DB şema drift'i (tablo/kolon
  değişikliği — self-contained fingerprint bunu yakalamaz; 28.7 Incremental
  Schema Sync ile örtüşebilir), TTL/zaman-tabanlı invalidation, explicit
  invalidation endpoint/event, granüler embedding-only invalidation.
  **Benchmark etkilenmedi** (`from_legacy_schema` sentetik şemalar
  üzerinde çalışır, `SchemaManager.load_schema`'yı egzersiz etmez) — gate
  yeşil, versiyon bump gerekmedi. Full suite 2509 passed/9 skipped.
  (PR #157)
- **Incremental Schema Sync** (Sprint 28.7): 28.6'nın notunda bırakılan
  "ham DB şema drift'i self-contained fingerprint'le yakalanmaz" sınırını
  giderdi. Yeni saf `app/schema/schema_signature.py`:
  `SCHEMA_SIGNATURE_VERSION = "v1"` + `normalize_structure(schema)`
  (dialect-agnostic, sıra-bağımsız kanonik yapı) + `compute_schema_signature`
  (sha256) + `diff_structures(old, new) -> StructuralDrift` (added/removed
  tables, added/removed/changed columns, added/removed FKs). `SchemaManager`
  yeni `_current_normalized_structure()`/`_current_schema_signature()`
  helper'larını kazandı; cache payload'ı yeni `schema_signature` alanını
  taşıyor. `load_schema`'da yeni **opt-in** yapısal drift kontrolü: config
  `auto_schema_drift_check` **varsayılan KAPALI** — kapalıyken 28.6 davranışı
  **byte-for-byte korunur**; açıldığında güncel signature cache'tekiyle
  karşılaştırılır, uyuşmazlıkta tam yeniden çıkarım + yeniden embedding
  tetiklenir. Yeni debug-gated router `app/api/schema_sync_api.py`:
  yan-etkisiz `GET /api/debug/schema/drift` (cache okur + taze signature
  hesaplar, ASLA `load_schema` çağırmaz) ve drift-aware
  `POST /api/debug/schema/sync?force=` (yalnız drift varsa veya `force=true`
  ise `force_refresh=True` ile yeniden inşa eder). **Benchmark etkilenmedi**
  (28.7 benchmark hedeflerine de `load_schema`'nın egzersiz edilen yoluna da
  dokunmuyor) — versiyon bump gerekmedi. **Bilinçli kapsam dışı** (TECH-DEBT
  §15): true per-table incremental re-extract/merge (drift'te hâlâ TAM
  yeniden çıkarım), granüler embedding-only re-index (→ 28.8), TTL/zaman-
  tabanlı invalidation (§14.2 hâlâ açık), ultra-ucuz tek-sorgulu drift
  sinyali kullanılmadı (extract-reuse tercih edildi), yalnızca yapısal drift
  (satır/veri-seviyesi drift yok), sync rebuild'i tüm-cache'dir, kısmi değil.
  TECH-DEBT §14.1/§14.3 **ÇÖZÜLDÜ**. Full suite 2537 passed/9 skipped.
  (PR #158)
- **Embedding / RAG Re-Index Pipeline** (Sprint 28.8): 28.7'nin notunda
  bırakılan "drift'te tüm cache (`schema`+`embeddings`) yeniden yazılıyor"
  sınırını embedding tarafında giderdi. Yeni saf `app/schema/reindex_planner.py`:
  `build_table_embedding_text` (embed edilen metnin tek doğruluk kaynağı),
  `compute_embedding_fingerprint(text, model)` (model-aware sha256),
  `stable_point_id(name)` (deterministik, restart-bağımsız Qdrant id) ve
  `plan_reindex(old_fingerprints, new_schema, model) -> ReindexPlan`
  (`to_embed`/`to_keep`/`to_delete` diff'i). `SchemaEmbeddingIndex.
  _generate_table_fingerprint` artık `build_table_embedding_text`'i delege
  ediyor (çıktı byte-identical). **Kök düzeltme:** `rag_manager.py`'deki
  `index_ddl`/`index_schema_batch` eskiden `int(hash(table_name) % 10**8)`
  ile point id üretiyordu — Python'un `hash()`'i `PYTHONHASHSEED`'e bağlı ve
  **süreç-başına farklı**dır; her restart aynı tabloya farklı bir Qdrant
  point id verip eskisini orphan bırakabiliyordu. Artık `stable_point_id`
  kullanılıyor (`business_rules`/`sql_history` koleksiyonları bilinçli
  olarak `hash()`'te bırakıldı, TECH-DEBT §16). Yeni
  `delete_schema_points`/`audit_schema_ddl_points`/`prune_schema_ddl_points`
  (`schema_ddl` koleksiyonuna özel, best-effort). Yeni `app/schema_reindex.py`:
  `reindex_embeddings(...)` — yalnız yeni/değişen tabloları embed eder,
  değişmeyenlerin vektörünü cache'ten reuse eder, kaldırılanları Qdrant'tan
  tahliye eder; aynı model+şema için tam `build_index`'e **çıktı-eşdeğerdir**.
  `SchemaManager.load_schema`'nın rebuild dalı artık bu executor'ı çağırıyor
  (cache `embeddings` yeni `fingerprints` alanını kazandı); `force_refresh=True`
  → tam yeniden-embed (28.6/28.7 davranışı korunur). Yeni debug-gated
  `GET /api/debug/schema/reindex-status` (yan etkisiz — fresh/stale/new/
  to_delete/orphaned_qdrant raporlar) + `POST /api/debug/schema/reindex?force=`
  (yalnız cache'li şema üzerinde embedding-only re-index — DB re-extract YOK).
  **Benchmark etkilenmedi** (28.8 dört benchmark hedefine de dokunmuyor) —
  versiyon bump gerekmedi, gate yeşil (exit 0). TECH-DEBT §14.4/§15.2
  **ÇÖZÜLDÜ**. Full suite 2569 passed/9 skipped. **Bilinçli kapsam dışı**
  (TECH-DEBT §16): `business_rules`/`sql_history` hâlâ non-deterministic
  `hash()` id / granüler re-index yok, embedding-model değişikliğinde otomatik
  kısa-devre yok (yalnız `POST /reindex` DB re-extract'ten kaçınır), Qdrant
  collection/vector_size migration, embed-text zenginleştirme (örnek
  değerler), batch-size tuning değişmedi. Dar bir edge-case NARROWED (final-review
  fix wave): `force=True` + eşzamanlı tablo kaldırma o zorlanmış rebuild'in kendi
  `reindex_embeddings` çağrısında kaldırılan tablonun Qdrant point'ini tahliye
  ETMEZ; aynı rebuild bloğunda hemen ardından çağrılan
  `RAGManager.prune_schema_ddl_points` ile aynı rebuild içinde temizleniyor
  (orphan + 28.8-öncesi `hash()`-id legacy point'ler birlikte). "Bir sonraki
  force-olmayan `load_schema` drift'i yakalar" iddiası YANLIŞTI ve kaldırıldı —
  kaldırılan tablo `fingerprints`'te hiç yer almadığından hiçbir sonraki
  `plan_reindex` onu `to_delete`'e koymaz; gerçek iyileşme yolları yalnızca
  prune-on-rebuild (yukarıda, her rebuild'de otomatik) ve `POST /api/debug/
  schema/reindex` (talep üzerine). (PR #159)
- **Semantic / Result Cache** (Sprint 28.9 · Phase 9'un SON sprint'i): üretilen
  SQL'i tamamen aynı (dialect + `schema_signature` + normalize edilmiş
  natural-language sorgu) istekler için writer-critic LLM döngüsünü atlayarak
  döndüren **deterministik exact result cache**. Yeni saf
  `app/cache/result_cache_key.py`: `RESULT_CACHE_KEY_VERSION = "v1"` +
  `normalize_query` (casefold + whitespace-collapse) +
  `compute_result_cache_key(natural_query, dialect, schema_signature) -> str`
  (sha256, stdlib-only, deterministik); `schema_signature`'a (28.7) bağlanma
  yapısal şema drift'inde anahtarı otomatik değiştirir. Yeni `sql_cache`
  SQLite tablosu (`database.init_db` migration; **RAW NL query kolonu YOK —
  secret-free**) + `app/result_cache.py` adaptor: `is_result_cache_enabled`
  (varsayılan **AÇIK**), `get_cached_sql`/`put_cached_sql`/`bump_hit`/
  `clear_cache`/`cache_stats`. Yeni `SchemaManager.get_cached_schema_signature()`
  — ucuz cache-dosyası okuması (DB extract YOK). `run_pipeline`'a yeni
  `_cache_lookup`: retrieval sonrası/writer-critic öncesi exact-key lookup;
  **hit'te cache'lenmiş SQL `validate_sql` ile YENİDEN doğrulanır — güvenlik
  zinciri ASLA bypass edilmez** (geçersiz hit sessizce tam üretime düşer);
  geçerli hit'te LLM döngüsü **ATLANIR**; miss+başarıda yeni SQL yazılır.
  Sonuçta yeni `cache_hit: bool` sonuç alanı + legacy trace metadata'sında
  aynı bayrak. Cache yalnız hem config açık hem gerçek `schema_signature`
  varsa aktif. Yeni debug-gated `GET /api/debug/cache/stats`
  (`entries`/`total_hits`) + `POST /api/debug/cache/clear` (silinen kayıt
  sayısı). Config `sql_result_cache_enabled` varsayılan **AÇIK**.
  **Benchmark etkilenmedi** (28.9 dört benchmark hedefine de dokunmuyor) —
  versiyon bump gerekmedi, gate yeşil (exit 0). **Bilinçli kapsam dışı**
  (TECH-DEBT §17): semantik/embedding-benzerlik cache (precision riski),
  execution/result-set (satır) cache (→ Phase 10), TTL/boyut-tabanlı otomatik
  eviction (yalnız `POST /clear`), prompt-template/model değişikliğinde
  invalidation (anahtar yalnız `schema_signature`'a bağlı — freshness-only),
  cache-hit-rate agregasyonu/dashboard paneli (yalnız `cache_hit` bayrağı),
  frontend `maxNodesLimit=5` kalıcı çözümü (farklı — frontend — katman, AÇIK
  kalır). Full suite 2609 passed/9 skipped. **Bununla Phase 9 (Large Schema
  Production Scale) kapanır.** (PR #160)
- **PostgreSQL Docker Integration Adapter** (Sprint 29.0 · Phase 10'un ilk
  sprint'i, **Phase 10 başlar**): 25.7/25.8'in *contract stub + yalnızca local
  Docker smoke*'unun üzerine gerçek `information_schema` introspection'ı ekleyen
  sprint — 25.8 sınırı (yalnızca local Docker, production execution yok) bilinçli
  olarak **korunur**, bu sprint yalnızca *şema okuma* katmanını gerçekleştirir.
  Repo kökünde yeni `docker-compose.yml`: CI ile parite (`postgres:16-alpine`,
  `sqlgen`/`sqlgen`/`sqlgen_test`, `5432:5432`, `pg_isready` healthcheck) + seed
  dosyası init-script olarak mount. Yeni deterministik
  `backend/tests/fixtures/postgres/seed.sql`: `customers`/`orders`/`order_items`
  (tek-kolon PK/FK) + `product_variants`/`variant_stock` (composite/çok-kolonlu
  PK/FK, idempotent `DROP TABLE IF EXISTS CASCADE`). Yeni saf
  `app/evaluation/postgres_connection_resolver.py`:
  `resolve_local_docker_connection(env) -> SQLPostgresLocalDockerConnection \|
  None` — `POSTGRES_TEST_*` env değişkenlerini okur (localhost/5432/sqlgen_test
  varsayılanlarıyla), **ASLA raise etmez** (uzak host/geçersiz port/boş alan →
  `None`), DB driver/socket importu yok; bağlantı kurulan **tek** yeniden
  kullanılabilir yer — 25.8'in entegrasyon test dosyasının
  `_make_test_connection`'ı artık buna delege ediyor (davranış korunur, aynı
  `SQLPostgresLocalDockerConnection` tipini döner). Yeni contract-first
  `app/evaluation/postgres_schema_adapter.py`: `SQLPostgresSchemaAdapterContract.
  introspect()` **yeni, güvenli** bir bağlantı üzerinden (mevcut execution
  adapter'ı paylaşmaz — local-docker-only, read-only, lazy `psycopg2` import,
  `_sanitize_schema_error` ile credential-free hata mesajları, `connection=None`
  → inert `NOT_IMPLEMENTED`) PostgreSQL `information_schema`'sını (tablo/kolon/PK/
  FK, yalnız `public` şema BASE TABLE) okur; saf çekirdek
  `build_database_schema_from_introspection(...)` deterministik (tablo/kolon
  sıralı) bir `DatabaseSchema` üretir, FK ilişkileri `RelationshipType.EXPLICIT`
  ve doğru yön (source=child, target=parent) taşır. **Composite (çok-kolonlu) FK
  introspection'ı kapsam içi** — Task 3 review'ı orijinal FK sorgusunun
  `constraint_name`-only join'inin çok-kolonlu FK'lerde sessizce YANLIŞ
  (cross-product) ilişki ürettiğini yakaladı; düzeltme
  `referential_constraints` + `position_in_unique_constraint` ile ordinal-eşleş-
  tirmeli bir sorguya geçti (child kolon N, aynı ordinal'deki referenced kolonla
  eşleşir) — composite FK'ler artık doğru eşleniyor (bkz. tasarım spec'inin
  2026-08-11 karar notu: "kapsam dışı" iken review-driven olarak kapsam içine
  alındı). Docker olmadan safe-skip olan, CI'da (Docker service zaten mevcut)
  fiilen koşan gated entegrasyon testleri: seeded tabloların introspection'ı
  (PK/kolon tipleri + FK yön/tip + composite-FK'nin doğru 2 kenar ürettiğinin —
  4 değil — regresyon guard'ı) + determinizm + credential-leak testi (yapısal
  içerik serileştirilir, `database_name` hariç tutulur çünkü seed'in kendi
  `sqlgen`/`sqlgen_test` değerleri gerçek dump'ta legitimate görünür) + 25.8
  execution adapter'ı üzerinden gerçek çok-tablolu `JOIN`. CI'a
  (`backend-ci.yml`) "Seed PostgreSQL integration schema" adımı eklendi
  (`psql -f seed.sql`, "Install dependencies" ile "Run tests" arasında).
  **Production request pipeline'ına HİÇ WIRE EDİLMEDİ** — adapter inert/
  standalone kalır; legacy `SchemaManager._extract_postgres_metadata` dokunul-
  madan duruyor. **Benchmark etkilenmedi** (29.0 dört benchmark hedefine de
  dokunmuyor) — versiyon bump gerekmedi, gate yeşil (exit 0). **Bilinçli
  kapsam dışı** (TECH-DEBT §18, sessiz düşürme yok): production pipeline'ına
  wiring (→ Phase 11 · 30.2 Connection Registry / 30.3 Schema Sync API),
  legacy `_extract_postgres_metadata`'nın bu güvenli contract'a taşınması,
  uzak/production connection (yalnız local-docker), `public` dışı şema/view/
  materialized view, kolon zenginleştirme (comment/açıklama/örnek değerler —
  schema-only), connection registry/çoklu bağlantı yönetimi (→ 30.2), gerçek
  execution wiring (→ 29.1 PostgreSQL Read-Only Execution). Full suite 2629
  passed/16 skipped. (PR TBD)

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
- **Tech-Debt Cleanup** (Sprint 27.11 · Phase 8 sonrası bakım, faz ilerletmez):
  `docs/TECH-DEBT.md`'de biriken 7 kalem çözüldü — davranış korunur, yalnız
  test-bütünlüğü/invariant/sağlamlık iyileşir (contract snapshot değişmedi).
  **§5.1** `errors`/`feedback` purity guard'ları (`backend/tests/errors/
  test_errors_package_purity.py`, `backend/tests/feedback/
  test_feedback_package_purity.py`) taze-alt-sürece (`subprocess`) taşındı —
  aynı-süreçte ölçen guard'ların sızıntıyı `sys.modules` cache'i yüzünden
  maskeleyebildiği 27.4 bulgusuyla aynı kök neden, `rule_suggestions` guard'ıyla
  aynı desen. **§5.2** `backend/tests/test_api_surface.py`'deki `expected_routes`
  artık elle bakımı yapılan bir literal değil, OpenAPI snapshot'ından türetiliyor
  — yeni endpoint eklenince sessiz drift riski kapandı. **§3**
  `backend/app/trace/end_to_end_trace_builders.py`'deki 5 stage builder'ı
  (intent/retrieval/prompt/generation/validation) artık SKIPPED dalında da
  kendilerine verilen ölçülen `duration_ms`'i taşıyor (SECURITY span'inde
  zaten uygulanan precedent'le tutarlı). **§9.3**
  `backend/app/llm_usage/compute.py`'de `model_id=None` olan generation artık
  `models_missing_price`'a `"unknown"` olarak uzlaşıyor —
  `unpriced_request_count` (request-seviyesi) ile `models_missing_price`
  (model-seviyesi) arasındaki tutarsızlık kapandı. **§8.2**
  `feedback_truncated` bayrağı eklendi (`backend/app/dashboard_service.py`,
  `backend/app/dashboard/contract.py`) — feedback ekseni artık trace/timeseries
  ile aynı "sessiz kesme yok" invariant'ını taşıyor. **§8.4(b)**
  `backend/app/dashboard/compose.py::bucket_timeseries` non-datetime
  `created_at`'i atlıyor (caller guard'ı eklendi). **§1**
  `backend/app/retrieval/nvidia_embedding_provider.py`'deki `dimension`
  parametresinin varsayılanı 1024→2048 olarak `rag_manager.py`'deki gerçek
  vektör boyutuyla hizalandı; ayrıca stale `FEATURE.md`/RAG doküman notu
  düzeltildi (bu dokümanlar zaten yok, `README` zaten koddaki değerlerle
  uyumlu). Full suite 2410 passed/9 skipped. Diğer TECH-DEBT kalemleri (§2,
  §4.3–4.9, §5.3/5.4, §6, §7, §8.1/8.3, §9.1/9.2, §10, §11) bilinçli olarak
  AÇIK bırakıldı (sessiz düşürme yok). (PR #149)
- **Tech-Debt Cleanup** (Sprint 28.3.1 · Phase 9 içi bakım, faz ilerletmez,
  27.11 desenini izler): `docs/TECH-DEBT.md`'de biriken 10 kalem 4 bundle
  altında çözüldü — davranış korunur, yalnız test-bütünlüğü/invariant/
  sağlamlık iyileşir. **Bundle A (§5.3/§8.1/§8.4a/§8.4c):** `live_trace_
  assembly`'deki canlı SECURITY span outcome'ı artık STAGE adı yerine 27.2
  error registry'sinden türetiliyor (`_security_outcome`: kodun kategorisi
  SECURITY ise `denied`/`error`, değilse `flagged`/`warning`; `_SECURITY_
  STAGES` seçimi ve pinning testi korunur) — ayrıca kayıtlı olmayan sahte bir
  koda dayanan 2 pre-existing test düzeltildi; `database.list_feedback`
  pencere sınırları `_normalize_feedback_boundary` ile naive-UTC'ye normalize
  edildi (dashboard feedback/trace bölümleri artık aynı zaman penceresini
  yansıtır); dashboard debug gate'i route-level `Depends(ensure_debug_
  enabled)`'e taşındı (debug kapalıyken geçersiz `bucket` artık 404, endpoint
  varlığı sızmıyor) + `TimeseriesBucket` docstring'ine `error_count`/
  `metrics.errors` fark notu eklendi. **Bundle B (§6.1):** `bundle_service.
  _latest_debug_trace` artık `TraceQuery(trace_type="nl2sql", job_id=…,
  limit=1)` ile doğrudan sorguluyor — eski `limit=5` penceresinin bir job'a
  ait `end_to_end` trace sayısı 5'i geçtiğinde asıl debug trace'i kaçırıp
  bundle'ın `sql` bölümünü `null` döndürme riski kapandı. **Bundle C
  (§12.16/§12.17):** `select_schema_context`'in bounded fallback rejimi artık
  `budget_exhausted=False` set ediyor (fallback bir bütçe-dalı değil, bounded
  bir güvenlik ağıdır) — önceki çelişkili `budget_exhausted=True` +
  `fallback_used=True` kombinasyonu kalktı, fallback davranışının kendisi
  değişmedi; yeni bir uçtan-uca test
  (`test_wiring_end_to_end_config_override_changes_selection`) `configs`
  üzerinden verilen bir `table_selection_cost_model` override'ının gerçek bir
  pipeline çalıştırmasında seçim sonucunu fiilen değiştirdiğini kanıtlıyor
  (önceki test yalnızca parse/`from_config` çağrısını doğruluyordu). **Bundle
  D (§12.6/§11.3/§12.7):** `NetworkXGraphBackend.personalized_pagerank`
  `scipy` eksikliğini `(ImportError, ModuleNotFoundError)` olarak ayrı
  yakalayıp DEBUG seviyesinde logluyor (beklenmeyen diğer hatalar hâlâ
  `logger.error`; `scipy` bağımlılığı bilinçli olarak eklenmedi); regression-
  gate CLI'ın `--version` bayrağı artık `^v?\d+\.\d+(\.\d+)?$` deseniyle
  doğrulanıyor, uyumsuz bir değer baseline'a hiç yazılmadan `exit 2` ile
  reddediliyor; §12.7 stale docstring/help metni kalemi **verify-close**
  edildi (kod değişikliği yok — `bench_contract.py`/`bench_cli.py` zaten
  28.1–28.3 düzeltme dalgalarında senkronlanmıştı: 5 hedefin tamamı listeli,
  "4-way"/`scale: 2000` metni yok, `--scales` yardımı `100,500,1000`
  gösteriyor). Full suite 2483 passed/9 skipped; CI perf-gate
  (`bench_cli --gate --scales 100,500,1000`) exit 0. **Yapısal borçlar
  bilinçli AÇIK bırakıldı** (sessiz düşürme yok): `scan_cap`→DB-aggregation
  kökü (§7.1/§8.3/§9.2/§10.3), retry-token eksik-sayımı (§9.1), onay-state
  persistence (§10.1), semantik dedup (§10.2), gerçek-accuracy/case-
  granülarite (§11.1/§11.2/§11.4/§11.5), Phase 9/12 kalemleri (§12.4/5/9/10/
  11/12/13/14/15). (PR #154)

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
