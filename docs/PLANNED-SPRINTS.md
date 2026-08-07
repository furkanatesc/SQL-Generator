# Planlanan Sprintler (Phase 7–15 · Sprint 25.8 → 34.7)

Bu dosya **ileriye dönük sprint planıdır** — henüz yapılmamış işler.
Tamamlanan işler için `SPRINT-PR-LOG.md`, üst düzey durum için `ROADMAP.md`.
Plan **Phase → Sprint → PR** ekseninde ilerler (sürüm/`v` etiketi kullanılmaz).

> **Çakışma netleştirmesi (Postgres/Oracle adapter):** Adapter işi iki seviyede
> planlıdır ve rolleri **bilinçli olarak ayrılmıştır**:
> - **Sprint 25.x** = *contract stub + yalnızca local Docker smoke* (sözleşme
>   doğru mu, import güvenli mi; gerçek production execution **yok**).
> - **Phase 10 (29.x)** = *production-grade gerçek execution* (gerçek driver,
>   read-only/EXPLAIN, connection registry ile).
> Yani 25.8/25.9 "iskele", 29.x "gerçek implementasyon"dur; tekrar değildir.

> **Feedback / öğrenen sistem notu:** `27.3 User Feedback Capture` feedback'i
> *toplar* (✅ tamam, aşağıda); bunu *tüketen* adım `27.9 Feedback Review → Rule
> Suggestion`'dır (planlı, `get_feedback_for_job`'u okuyup kural önerir). Daha
> ileri "öğrenen sistem" adımları (value index, trace mining, rule promotion)
> hâlâ plan dışıdır ve aşağıdaki "Önerilen Ek Sprintler" bölümünde aday olarak
> değerlendiriliyor.

---

## Sprint 25 — Kalan adımlar (Multi-DB / Adapter Stubs)
| Sprint | İş | Durum |
|---|---|---|
| 25.6 | Execution Trace / Audit Contract | ✅ Tamam (#121) |
| 25.7 | PostgreSQL Adapter Contract **Stub** | ✅ Tamam (`NOT_IMPLEMENTED`) |
| 25.8 | PostgreSQL Read-Only Adapter — **Local Docker Only** | ✅ Tamam (#125) · *yalnızca local Docker read-only SELECT; production execution Phase 10/29.1'de* |
| 25.9 | Oracle Adapter Contract **Stub** | ✅ Tamam · *tüm execution flag'leri False; gerçek adapter 29.3, Docker/test harness 29.4'te* |

> ✅ **Phase 6 (Multi-DB / Adapter Stubs) kapandı.** Sıradaki ana faz:
> **Phase 7 — Security & Governance** (26.0 SQL Permission Policy Contract). Adapter
> geliştirmeye Phase 10'a (29.x) kadar dönülmüyor.

---

## Phase 7 — Security & Governance
**Amaç:** Production security, tenant boundary, permission policy, read-only
enforcement, query risk classification, sensitive table/column policy ve audit
governance.

| Sprint | İş | Durum |
|---|---|---|
| 26.0 | SQL Permission Policy Contract | ✅ Tamam · *default-deny karar sözleşmesi; enforcement değil* |
| 26.1 | Tenant / Workspace Boundary Contract | ✅ Tamam · *fail-closed tenant/workspace isolation contract; enforcement/persistence değil* |
| 26.2 | Read-Only Enforcement Hardening | ✅ Tamam · *merkezi fail-closed read-only SELECT enforcement contract; postgres adapter gate'i buna delege* |
| 26.3 | Query Risk Classifier | ✅ Tamam · *statik deterministik risk sınıflandırıcı (LOW→CRITICAL); gate değil, sadece sinyal* |
| 26.4 | Sensitive Table / Column Policy | ✅ Tamam · *beyan-tabanlı hassas tablo/kolon gate'i (ALLOW/DENY/REQUIRES_APPROVAL) + matched/seviye sinyali; hibrit referans (explicit=sound, SQL extraction=best-effort)* |
| 26.5 | PII / PHI Detection Contract | ✅ Tamam · *heuristik PII/PHI detector (sinyal, gate değil): kategori + PII/PHI veri-sınıfı + güven; 3 katman (declared=sound, identifier-isim + literal-değer/Luhn=best-effort); secret-free sonuç* |
| 26.6 | Audit Event Contract | ✅ Tamam · *deterministik, secret-free audit kaydı + tamper-evident SHA-256 hash-chain; 26.0–26.5 sonuçlarını tek immutable AuditEvent'e normalize eden 6 builder (OWASP-style kategoriler, NIST SP 800-92 6-soru çekirdeği); zaman/ID caller-supplied; verify_chain mutation/reorder/insert/delete yakalar (integrity-evident, non-repudiation Phase 13)* |
| 26.7 | Approval Workflow Contract | ✅ Tamam · *saf deterministik approval state machine (I/O & clock yok, time/id caller-supplied, frozen dataclass, secret-free); PENDING + terminal (APPROVED/REJECTED/EXPIRED/CANCELLED) durumları; fail-closed from_permission (N=1) / from_sensitive (CONFIDENTIAL→1, RESTRICTED→2); approve/reject quorum N-of-M + SoD (requester≠approver) + duplicate-vote guard + single-reject veto + terminal immutability; caller-driven expire; audit interlock (AuditCategory.APPROVAL + from_approval)* |
| 26.8 | Prompt-Injection / NL Abuse Defense | ✅ Tamam · *kaynak-duyarlı (source-aware) prompt-injection detector (sinyal, gate değil; secret-free); altı örüntü ailesi (instruction override, role hijack, delimiter/system-prompt spoof, exfiltration, encoded payload, tool/agent abuse) + per-segment tespit; NFKC normalizasyonu + Türkçe-güvenli obfuscation sinyali; Detector.evaluate + kaynak-duyarlı disposition policy; audit interlock (AuditCategory.PROMPT_INJECTION + from_prompt_injection)* |
| 26.9 | Result-Set Privacy & Row/Size Limits | ✅ Tamam · *post-execution sonuç kümesi üzerinde ilk contract; hibrit limit GATE (ALLOW/TRUNCATE/DENY — max_rows/max_bytes/max_columns + truncate_allowed) + advisory kolon-seviyesi PII/PHI privacy sinyali (26.5 value-scan reuse); audit interlock (RESULT_SET_PRIVACY + from_result_set); PHI yolu belgeli-inert (yalnız PII üretilir)* |
| 26.10 | Connection Credential Vault (server-side) | ✅ Tamam · *saf, deterministik, secret-free, I/O-free governance contract: secret_ref resolve gate + ham-secret sızıntı advisory sinyali; 6 boyutlu deterministik öncelik (leak→auth_mode→provider→environment→tenant→purpose→ALLOW), 7 reason code; ham secret'ı asla tutmaz/çözmez (referans+karar); audit interlock (CONNECTION_CREDENTIAL + from_credential_vault); PEP 562 lazy export ile driver-isolation korunur* |
| 26.11 | Policy / Security Eval | ✅ Tamam · *saf, deterministik, secret-free, I/O-free meta-evaluation harness 26.0–26.10 contract'ları üzerinde (app.evaluation'da yaşar → app.security driver-free kalır); normalize SecurityEvalOutcome + 11 per-contract projector (enum-purity invariant: yalnız enum .value) + 22 in-code blessed golden case (gerçek contract çağrısı) + exact-match drift gate + enum-introspection coverage (universe − declared exclusions) + PASS/WARN/FAIL aggregator (SQLEvalGate'i aynalar; case mismatch→FAIL, coverage gap→WARN); audit interlock/JSON loader bilinçli kapsam-dışı; driver-isolation invariant doğrulandı* |

> ⚠️ Phase 14 (SaaS) ile örtüşme: tenant boundary (26.1 ↔ 33.0), RBAC/permission
> (26.0 ↔ 33.2), audit (26.6 ↔ 33.6). Phase 7 = **backend sözleşme/politika
> katmanı**, Phase 14 = **SaaS/UI katmanı** olarak ayrılmalıdır.

> ✅ **Phase 7 (Security & Governance) kapandı** (26.0–26.11 tamam). Sıradaki ana
> faz: **Phase 8 — Observability & Debuggability** (27.x).

---

## Phase 8 — Observability & Debuggability
**Amaç:** Production'da "neden bu SQL üretildi?", "neden fail oldu?", "hangi
context seçildi?", "hangi policy blocked etti?" sorularına cevap verebilmek.

| Sprint | İş |
|---|---|
| 27.0 | End-to-End Trace Contract | ✅ Tamam · *saf, deterministik, secret-free, I/O-free EndToEndTrace sözleşmesi — pipeline per-stage çıktılarını tek request_id altında ilişkilendirir. Typed envelope (EndToEndTrace) + ordered TraceSpan tuple (hibrit: stage başına typed detail + generic attributes escape hatch); enums + frozen records + cross-field __post_init__ invariant'lar + JSON-safe to_payload; derive_terminal precedence (execution blocked/rejected > ilk ERROR span > COMPLETED) + build_end_to_end_trace assembler; duck-typed build_execution_span + build_security_span (getattr off Any; empty/None→SKIPPED) → app.trace.* dışına import yok, driver-isolation korunur. Secret-free: yalnız sql_sha256 + reason/symbol string + redacted error payload'a ulaşır. Kalan stage builder'ları + live wiring → 27.1. SDD (5 görev + 2 pre-merge minor fix, her biri TDD + task review; opus whole-branch review merge-ready, 0 Critical/Important). Full suite 1998 passed/9 skipped. `backend/app/trace/end_to_end_trace{,_builders}.py`* |
| 27.1 | Remaining Stage Span Builders | ✅ Tamam · *kalan 5 stage'in (INTENT/RETRIEVAL/PROMPT/GENERATION/VALIDATION) saf, duck-typed, secret-free span builder'ları + typed `*SpanDetail` record'ları — 27.0'ın builder setini tamamlar (27.0 EXECUTION+SECURITY göndermişti). Builder'lar attr'ları `getattr` ile `Any` üzerinden okur; empty/`None`→SKIPPED; `derive_terminal`/`build_end_to_end_trace`/`to_payload` değişmedi. Driver-isolation testle kilitli (`app.trace.*` importu hiçbir `app.evaluation`/DB driver yüklemez). SDD (6 görev, her biri TDD + task review; opus whole-branch review merge-ready, 0 Critical/0 Important, 3 Minor → 27.1w'ye devredildi). Full suite 2024 passed/9 skipped. Canlı telçekimi bilinçli olarak 27.1w'ye ertelendi. `backend/app/trace/end_to_end_trace{,_builders}.py`. Spec: `docs/superpowers/specs/2026-07-01-sprint-27.1-remaining-stage-span-builders-design.md`* |
| 27.1w | **Live Trace Wiring** | ✅ Tamam · *27.0/27.1'in saf `EndToEndTrace` sözleşmesi canlı pipeline'a örüldü (27.1'den bilinçli ertelenmişti). `request_id` plumbing (HTTP `X-Request-ID` → `process_job_pipeline` → `run_pipeline`; yoksa `req_` önekiyle mint); her stage `perf_counter` ile ölçülür; `_capture_trace_on_exit`'te legacy `NL2SQLTrace`'in YANINA `trace_type="end_to_end"` dual-emit; `run_pipeline` üç stage metoduna ayrıldı (`_stage_intent`/`_stage_retrieval`/`_stage_writer_critic`) — davranış birebir korundu (kanıt: branch genelinde tüm test dosyaları `+N/-0`, hiçbir mevcut assert değişmedi). Yeni saf modül `backend/app/trace/live_trace_assembly.py` (yalnız `app.trace.*` + stdlib; purity artık testle guard'lı). 27.1'den devreden 3 Minor kapatıldı. Emisyon hatası pipeline sonucunu asla etkilemez (tek `try/except`, legacy save öncesinde ve koşulsuz); ham SQL payload'a girmez (yalnız sha256). **Bilinen sınır (kasıtlı, CHANGELOG'da yazılı):** dual-emit yalnız `save_legacy` expose eden store'larda çalışır — prod `SQLiteTraceStore` tam emit alır, eski tekil-`save()` store'lar yalnız legacy görür. SDD (8 görev, her biri TDD + sonnet task review; opus whole-branch review "merge after fixes" → Task 8 fix'leri yapıldı, 0 Critical/0 Important). Whole-branch review, task review'ların yapısal olarak göremediği gerçek bir bug yakaladı: intent/security timing'leri ölçülüp düşürülüyordu — kök neden planın kendi içinde çelişmesiydi (düzyazı kuralı satır 187 vs. referans kodu). Full suite 2055 passed/9 skipped. Kalan borç: TECH-DEBT §3 (SKIPPED span'lerde `duration_ms` düşüyor; semantik karar bekliyor). Spec: `docs/superpowers/specs/2026-07-06-sprint-27.1w-live-trace-wiring-design.md`* |
| 27.2 | Error Taxonomy v2 | ✅ Tamam · *hata taksonomisi tek registry'de toplandi: saf `backend/app/errors/` yaprak paketi (`StrEnum` `ErrorCode`/`ErrorCategory` + `DESCRIPTORS`/`describe`/`category_of`, purity testli). Kategori (hatanin dogasi) ile stage (nerede yakalandigi) eksenleri ayrildi; `run_pipeline` sonucuna `error_code` eklendi ama bilincli olarak pipeline katmaninda duruldu — is/API/frontend sinir gecisi 27.2.1'e ertelendi. (PR #136)* |
| 27.3 | User Feedback Capture | ✅ Tamam · *append-only backend feedback yüzeyi: `backend/app/feedback/` (saf `FeedbackVerdict`/`FeedbackCategory` taksonomisi) + `feedback` tablosu + `POST /api/jobs/{job_id}/feedback`. Bilinçli olarak backend-only: HTTP GET listeleme/admin (`30.6`), frontend UI (`31.7`) ve `rating` alanı kapsam dışı. `27.9` bunu `get_feedback_for_job` ile tüketecek. (PR #139)* |
| 27.4 | Query Replay System | ✅ Tamam · *gecmis bir job'i bugunun kodu ve semasiyla deterministik olarak yeniden kosar (LLM YOK) ve o gunku `end_to_end` trace baseline'iyla karsilastirir. Saf yaprak paket `backend/app/replay/` (ReplayVerdict + frozen delta record'lari + saf `compare_replay`/`extract_baseline`) + `sql_pipeline.validate_sql` seam refactor'u (dogrulama zinciri LLM retry dongusunden ayiklandi; davranis korundu, mevcut test dosyalari +N/-0) + kirli adaptor `app/replay_service.py` + `POST /api/debug/jobs/{job_id}/replay` (debug bayragiyla gated, 200 envelope). Replay YAN ETKISIZ: hicbir sey yazilmaz, trace emit edilmez. Bilincli kapsam disi: LLM'li tam re-run, replay kaliciligi, toplu replay, frontend UI (Phase 12), 27.1w oncesi joblar icin legacy baseline fallback'i (→ `baseline_unavailable`). (PR #141)* |
| 27.5 | Debug Bundle Export | ✅ Tamam · *bir job'in tum debug baglamini (o gunku `end_to_end` trace + REDAKTE SQL/attempts/validation_errors + 27.4 replay'i INLINE kosarak + secilen sema ozeti + surum metadata) tek bir JSON envelope'da toplayan, hata raporuna eklenebilir, YAN ETKISIZ export. Saf yaprak paket `backend/app/debug_bundle/` (allow-list projektorler + saf `compose_bundle` + frozen record'lar) + kirli adaptor `app/bundle_service.py` (iki trace turu + inline replay) + `GET /api/debug/jobs/{job_id}/bundle` (debug bayragiyla gated, 200 envelope). Sema+meta+job allow-list ile; trace/sql mevcut redaksiyon gecisleriyle. Iki trace ayrimi: end_to_end secret-free (hash-only) -> trace+schema; debug trace -> redakte sql. Bilincli kapsam disi: ZIP/Markdown format, bundle kaliciligi, toplu export, tam DDL snapshot, frontend UI (Phase 12). (PR #143)* |
| 27.6 | Metrics Contract | ✅ Tamam · *bir zaman penceresindeki `end_to_end` trace'leri toplayan versiyonlu metrik raporu: hacim&sonuc (terminal_status dagilimi + success_rate=completed/total), hata taksonomisi (by_code + by_category, bilinmeyen kod -> 'unknown' kovasi, 27.2 registry), latency (nearest-rank p50/p95/p99, None atlanir), asama kirilim (stage->span status). Saf yaprak paket `backend/app/metrics/` (app.errors izinli; frozen record'lar + saf `compute_metrics`) + kirli adaptor `app/metrics_service.py` (RAW store, bounded fetch + `truncated` bayragi) + `GET /api/debug/metrics` (debug bayragiyla gated, 200 envelope). Metrikler hassas DEGIL -> redaksiyon yok. Bos pencere -> 200 sifirlarla. Bilincli kapsam disi: cost/LLM usage (27.8), zaman-serisi/bucketing (27.7), metrik kaliciligi, scan_cap query'den, frontend UI (Phase 12). (PR #144)* |
| 27.7 | Admin Observability Dashboard Backend | ✅ Tamam · *27.6 metrik snapshot'ini zaman-serisi bucketing + top hatalar + feedback ozeti + son aktivite ile tek kompozit JSON'da birlestiren, yan etkisiz `GET /api/debug/dashboard`. Saf yaprak paket `backend/app/dashboard/` (frozen contract + saf section builder'lar + `compose_dashboard`; **27.6 `compute_metrics`'i reuse eder** — span'leri yeniden okumaz, 27.6'nin duzeltilmis aggregate'ini tuketir; purity: yalniz stdlib + `app.errors` + `app.metrics`, `app.trace.*` YASAK, taze-alt-surec guard'li) + kirli adaptor `app/dashboard_service.py` (**tek** trace fetch → metrics+timeseries+recent ayni veriyi paylasir + `database.list_feedback`) + `GET /api/debug/dashboard?created_after=&created_before=&dialect=&bucket=hour|day&top_n=&recent_limit=` (API key + `debug_endpoints_enabled` ile gated, 200 envelope). Determinist: `datetime.now()` ASLA — yalnizca var olan damgalar floor'lanir; nearest-rank p95; sirali sozlukler. Sessiz kesme yok: trace `truncated` + `timeseries_truncated`. Bos pencere → 200 bos bolumlerle. Dashboard verisi hassas DEGIL → redaksiyon yok. Opus whole-branch review = SHIP (0 Critical/0 Important-bloke; 1 Important + 4 Minor → TECH-DEBT §8). Full suite 2323 passed/9 skipped. **Bilincli kapsam disi:** cost/LLM usage (27.8), feedback→rule (27.9), zaman-serisi zero-fill (bos bucket'lar atlanir), `scan_cap`/percentile'in DB-side tam-populasyon hesabi (TECH-DEBT §8), frontend UI (Phase 12). (PR #145)* |
| 27.8 | Cost & LLM Usage Telemetry | ✅ Tamam · *bir zaman penceresindeki `end_to_end` trace'lerin GENERATION span'lerinden LLM kullanimini (request/token/latency/finish_reason) toplayan ve konfigure edilebilir fiyat tablosuyla tahmini maliyet ureten, yan etkisiz `GET /api/debug/llm-usage`. Veri zaten GENERATION span `detail`'inde (27.1w) → yeni enstrumantasyon YOK, yalnizca aggregation+fiyatlandirma. Saf yaprak paket `backend/app/llm_usage/` (contract+`pricing`+`compute`; purity **yalniz stdlib**, `app.trace.*`/`app.errors` asla, taze-alt-surec guard) + kirli adaptor `app/llm_usage_service.py` (tek trace fetch + `get_config('llm_pricing')`) + `GET /api/debug/llm-usage?created_after=&created_before=&bucket=hour|day` (debug-gated, 200 envelope). Bolumler: totals + model/provider kirilimi + latency (nearest-rank p50/p95/p99) + finish_reason dagilimi + zaman-serisi. Maliyet=token×per-1M fiyat; fiyatsiz model→cost null + `models_missing_price` + `unpriced_request_count` (sessiz bosluk yok). Determinist; `truncated`+`timeseries_truncated`; bos pencere→200. Opus whole-branch review = SHIP (0 bloke; 27.6 span-tuzagi yok; 1 Minor → TECH-DEBT §9). Full suite 2354 passed/9 skipped. **Kapsam disi:** retry per-attempt token yakalama (trace tek GENERATION span, TECH-DEBT §9), model/provider query filtresi, dashboard entegrasyonu, zero-fill, persistence, gercek NIM faturalandirmasi, frontend UI (Phase 12). (PR #146)* |
| 27.9 | Feedback Review → Rule Suggestion | ✅ Tamam · *kullanici feedback'ini (27.3/27.7 `list_feedback`) aday {natural_query→SQL} kural onerisine ceviren, YAN ETKISIZ `GET /api/debug/rule-suggestions`. Iki kind: correction (`incorrect`+dolu `corrected_sql`) / confirmation (`correct`+dolu job `result_sql`); ineligible sebep onceligi missing_job > missing_natural_query > missing_sql. Saf yaprak paket `backend/app/rule_suggestions/` (`contract.py` frozen record'lar + SIRALI `to_payload`; `compute.py` saf `classify_item`+`compute_rule_suggestions` — dedup `(natural_query, suggested_sql, kind)`, support-count ranking, by_kind/by_category kirilimlari; purity **yalniz stdlib**, `app.feedback`/`app.trace.*` asla, taze-alt-surec guard'li) + kirli adaptor `app/rule_suggestions_service.py` (`list_feedback`+`get_job` korelasyonu, job-cache, `scan_cap=10000`) + `GET /api/debug/rule-suggestions?created_after=&created_before=` (API key + `debug_endpoints_enabled` ile gated, 200 envelope). Bilinçli olarak yalnizca ONERIR: insan `POST /api/rag/index/sql-history` ile ayrica onaylar/indeksler; redaksiyon YOK (amaç ham SQL'i onaya sunmak). Full suite 2378 passed/9 skipped. **Bilinçli kapsam dışı:** onay/persistence-state (onaylanan öneri idempotent düşmez), LLM/semantik genelleme + synonym türetme (yalnız literal eşleşme), `scan_cap` üstü DB-side tam-populasyon, frontend UI (Phase 12). (PR #147)* |
| 27.10 | Per-Release Accuracy Regression Gate | ✅ Tamam · *mevcut deterministik golden eval raporunu (`app.eval.run_eval --profile golden`) tüketen, YAN ETKİSİZ CLI/CI regresyon gate'i — debug endpoint DEĞİL. Saf yaprak paket `evals/regression_gate.py` (`compare_regression` + baseline helper'ları; per-case sıfır-tolerans birincil + aggregate ikincil karşılaştırma, common (baseline∩current) kesişimi üzerinde; reason önceliği per-case > aggregate > bootstrap; drift bilgi amaçlı, regresyon değil) + kirli CLI `evals/regression_gate_cli.py` (`--update-baseline` bayrağı + exit 0/1/2) + seeded append-only `evals/baselines/history.json` (`v1.0.0`) + `backend-ci.yml`'e regresyon-gate adımı. Boş/yok baseline → bootstrap yeşil (exit 0). **Bilinçli kapsam dışı:** gerçek-LLM accuracy (deterministik sahte pipeline üzerinde çalışır; gerçek model doğruluğu değil, subsystem C execution harness'ı), debug endpoint (yalnız CLI/CI), git-tag'in runtime'da okunması (sürüm etiketi operatör tarafından `--version` ile verilir), CI'da baseline'ın otomatik güncellenmesi (`--update-baseline` elle çağrılır), frontend. PR `#148`.*
| 27.11 | Tech-Debt Cleanup (bakım) | ✅ Tamam · *faz ilerletmeyen bakım sprinti — davranış korunur, yalnız test-bütünlüğü/invariant/sağlamlık iyileşir (contract snapshot `git diff` boş). 7 kalem ÇÖZÜLDÜ: §5.1 errors+feedback purity guard'ları taze-alt-sürece taşındı (subprocess), §5.2 `expected_routes` artık OpenAPI snapshot'ından türetilir (tek kaynak snapshot), §3 5 stage builder'ı (intent/retrieval/prompt/generation/validation) SKIPPED dalında ölçülen `duration_ms`'i taşıyor (option a, SECURITY precedent'i), §9.3 null-model generation `models_missing_price`'a `"unknown"` olarak uzlaşır, §8.2 `feedback_truncated` bayrağı eklendi, §8.4(b) `bucket_timeseries` non-datetime `created_at`'i atlar, §1 `nvidia_embedding_provider.py` `dimension` default 1024→2048 hizalandı + stale FEATURE.md/RAG doküman notu düzeltildi (o dokümanlar zaten yok). Diğer TECH-DEBT kalemleri (§2, §4.3–4.9, §5.3/5.4, §6, §7, §8.1/8.3, §9.1/9.2, §10, §11) AÇIK. PR `#149`.*

---

## Phase 9 — Large Schema Production Scale
**Amaç:** 2000 tabloya yaklaşan enterprise database'lerde schema selection, join
path control, missing FK inference ve graph performance problemlerini
production-grade çözmek.

| Sprint | İş |
|---|---|
| 28.0 | Large Schema Benchmark Suite | ✅ Tamam · *yeni `backend/benchmarks/` paketi (dev/CI aracı, `evals/`'in kardeşi) — production'a hiçbir `app/` değişikliği yok, davranış korunur. Saf çekirdek: seeded sentetik şema üreteci (`schema_generator.py`, 100/500/1000/2000 tablo ölçekleri, `random.Random(seed)` ile determinist), frozen metrik sözleşmesi (`bench_contract.py`: `BenchmarkMetric`/`BenchmarkReport`), 4 REUSED prodüksiyon hedefi için girdi/çıktı-türevli determinist metrik çıkarıcılar (`bench_metrics.py`: `from_legacy_schema` validator, `find_join_paths`, `detect_implicit_relationships`, `select_schema_context`), ve 27.10 desenini izleyen `compare_benchmark` (`bench_compare.py`). Kirli kenar: `bench_runner.py` (enjekte edilen clock ile ölçer; `wall_ms` yalnızca bilgi amaçlı, ASLA gate'lenmez) + `bench_cli.py` (`--gate`/`--update-baseline`, exit `0`/`1`/`2`). Seeded committed baseline `baselines/history.json` (1 kayıt, 4 hedef × 4 ölçek = 16 metrik). Determinist complexity metrikleri exact-match gate'lenebilir; wall-clock yalnızca bilgi amaçlı (determinizm korunur). Yeni source-scan purity guard testi (`backend/tests/benchmarks/test_benchmarks_purity.py`) dört saf modülün clock/datetime/unseeded-random içermediğini kilitler. **Bilinçli kapsam dışı (→ 28.1+, TECH-DEBT §12):** iç patlama sayaçları (`dfs_visits`/`fuzzy_comparisons` — prodüksiyon hot path'lerine enstrümantasyon gerektirir), CI perf-gate kablolaması, NetworkX/`schema_graph` pruner benchmark'ı, embedding/RAG retrieval benchmark'ı (→ 28.8). Bununla **Phase 9 (Large Schema Production Scale) başlar**. (PR #150)* |
| 28.1 | Schema Graph Performance Profiling | ✅ Tamam · *opsiyonel sıfır-ek-yük `ProfileProbe` (`app/schema/profiling.py`) — `find_join_paths`/`detect_implicit_relationships`/`select_schema_context`'e iplenmiş; davranış korunur (`probe=None` byte-for-byte aynı, mevcut `tests/schema` yeşil `+N/-0`). Benchmark v2: determinist iç sayaçlar (`dfs_visit`, `adjacency_edge`, `path_recorded`, `pair_iteration`, `fuzzy_comparison`, `rule3_scan`, `table_scan`, `column_scan`, `related_expansion`) her hedefin determinist metriklerine birleşir. Üreteç near-miss kolonlar kazandı (Rule-2 fuzzy artık egzersiz ediliyor). Yeni 5. `graph_backend` hedefi `NetworkXGraphBackend`'i (build + pagerank + shortest_path) `to_legacy_dict` reuse'iyle egzersiz eder — çıktı-türevli tam-sayı metrikler (`graph_nodes`/`graph_edges`/`sp_*`) + `wall_ms`; pagerank float GATE'LENMEZ. Baseline `large_schema_benchmark_v2`'ye yükseldi (gate'lenen ölçekler 100/500/1000, 15 metrik; 2000 manuel referans). Yeni CI perf-gate adımı (`bench_cli --gate --scales 100,500,1000`). Prodüksiyon davranış değişikliği YOK (probe opsiyonel/guard'lı). **TECH-DEBT §12 ÇÖZÜLDÜ:** iç patlama sayaçları (`dfs_visit`/`fuzzy_comparison` vb.), CI perf-gate kablolaması, NetworkX/graph-backend benchmark'ı. **AÇIK kalanlar:** embedding/RAG retrieval benchmark'ı (→ 28.8), `GraphPruner` candidate/policy derin entegrasyonu + pruner iç probe'u; yeni: `scipy` kurulu değil → `personalized_pagerank` `{}`'e düşer (yakalanır, gate etkilenmez) — gerçek pagerank profilleme için `scipy` eklenmesi düşünülebilir; `bench_contract.py`/`bench_cli.py` docstring/help metinleri hâlâ 4-way/scale-2000 diyor (kozmetik doc-sync borcu). (PR #151)* |
| 28.2 | Join Path Explosion Control | ✅ Tamam · *`find_join_paths`'in kombinatoryal DFS patlamasını İKİ katmanla sınırlayan ve yeni `JoinPathSearchResult` sözleşmesini döndüren (tek-API kırılımı; 13 çağrı noktası `.paths`'e taşındı) sprint. **Katman 1 — çıktı-koruyan branch-and-bound (hızlı yol):** ters-BFS `hop` mesafeleri (`_hop_distances`) admissible A*-benzeri bir derinlik sınırı verir, artı kept-set dominance pruning (optimistic tamamlama prefiksinde kesin `>`); ÇIKTI BYTE-FOR-BYTE KORUNUR — pruning yalnızca ziyareti keser, brute-force denklik testiyle guard'lı. **Katman 2 — determinist güvenlik kemeri:** `node_budget` (keyword-only, `DEFAULT_JOIN_PATH_NODE_BUDGET = 200_000`); taşmada DFS determinist şekilde durur ve `budget_truncated=True` işaretler. `select_schema_context` yeni `join_search_truncated: bool = False` alanı kazandı (çift üzerinde OR'lanır) + opsiyonel `node_budget` passthrough — non-breaking (defaultlu alan). Benchmark v3 (`large_schema_benchmark_v3`, gate'lenen ölçekler 100/500/1000) join_paths hedefinde ölçülen düşüş: `dfs_visit` 205→5 / 747→6 / 2653→6; `adjacency_edge` (probe) 368→19 / 1452→186 / 5264→375; yeni `branches_pruned` 15/180/369. Çıktı-türevli metrikler DEĞİŞMEDİ (`paths_found_total`=2, `path_recorded`=2, `pairs_with_path`=2 tüm ölçeklerde) — çıktı korumasının kanıtı. Gate'lenen ölçeklerde `join_budget_truncated` yok; CI perf-gate yeşil. **Bilinçli kapsam dışı (TECH-DEBT §12):** ağırlıklı/maliyet-tabanlı path scoring + hub-penalty (`graph_traversal.py`'deki "future work" yorumu AÇIK kalır — 28.2 yalnızca enumerasyonu sınırlar, scoring'i değil), `GraphPruner` candidate/policy derin entegrasyonu (§12.5 hâlâ AÇIK), empirik/adaptif budget tuning (sabit 200_000 kullanılır), frontend `maxNodesLimit` kalıcı çözümü (§2, Phase 12). (PR #152)* |
| 28.3 | Table Selection Cost Model | ✅ Tamam · *`select_schema_context`'in hardcoded additive relevance skoru + düz top-K'sini config-driven bir **benefit-vs-cost budget modeliyle** değiştiren sprint. Yeni saf `app/schema/table_selection_cost.py`: frozen `TableSelectionCostModel` (named relevance ağırlıkları = eski magic number'lar + cost ağırlıkları `w_base`/`w_col`/`w_fk` + `cost_budget`), `table_cost() = w_base + w_col*columns + w_fk*fks`, `fk_counts()` (source-side), toleranslı `from_config()` (27.8 `llm_pricing` deseni). `select_schema_context` enjekte edilen `cost_model=DEFAULT_COST_MODEL` kazandı (saf yaprak kalır; `probe`/`node_budget` korunur). Benefit artık model ağırlıklarıyla skorlanır (kalan magic number yok). Seçim: exact-match focus tabloları önce garanti edilir, kalanlar `cost_budget` altında benefit-density (`benefit/cost`) greedy ile eklenir (skip-and-continue), `max_tables` ikincil sert tavan. Şeffaflık: `SelectedTable.cost`, `SchemaContextSelection.total_cost`/`cost_budget`/`budget_exhausted`. Kirli config yükü `sql_pipeline.py`'de: config anahtarı `table_selection_cost_model` → `from_config` → enjekte; yoksa `DEFAULT_COST_MODEL`. Muhafazakâr varsayılan `cost_budget=30.0` golden şema üzerinde kalibre edildi (ölçülen max `total_cost`=25.0); golden eval yeşil, fixture kürasyonu GEREKMEDİ. Benchmark v4 (`large_schema_benchmark_v4`): `context_selection` cost modelini yansıtır (scale 100 `selected_tables_total` 67→61); **`join_paths` metrikleri v3'e göre DEĞİŞMEDİ** (`dfs_visit` 5/6/6, `branches_pruned` 15/180/369). Gate yeşil. **Bilinçli kapsam dışı:** ilişki-güven-ağırlıklı komşu benefit'i (→ 28.4; 28.3 düz 20/10'u cost modeline taşıdı), token-tabanlı gerçek maliyet (serialize footprint) — kolon-sayısı proxy'si kullanılır, gerçek 0/1-knapsack optimalliği (deterministik greedy kullanılır), frontend `maxNodesLimit` kalıcı çözümü (§2, Phase 12). PR `#153`.* |
| 28.3.1 | Tech-Debt Cleanup (bakım) | ✅ Tamam · *faz ilerletmeyen bakım sprinti (27.11 desenini izler) — `docs/TECH-DEBT.md`'de biriken, 4 bundle'a gruplanmış 10 kalem ÇÖZÜLDÜ: **A** §5.3 canlı SECURITY span outcome'ı artık 27.2 error registry'sinden türetiliyor (`_security_outcome`: kategori→`denied`/`error` vs `flagged`/`warning`; `_SECURITY_STAGES` seçimi korunur) + 2 pre-existing test kayıtlı-olmayan sahte koddan gerçek koda düzeltildi; §8.1 `list_feedback` pencere sınırları `_normalize_feedback_boundary` ile naive-UTC'ye normalize edildi (dashboard feedback/trace bölümleri artık aynı pencereyi yansıtır); §8.4(a) debug gate route-level `Depends`'e taşındı (debug kapalıyken geçersiz `bucket` artık 404) + §8.4(c) `TimeseriesBucket` docstring notu. **B** §6.1 `_latest_debug_trace` artık `TraceQuery(trace_type="nl2sql", limit=1)` ile doğrudan sorguluyor (limit=5 pencere-kaçırma → bundle `sql` null riski kapandı). **C** §12.16 selector fallback rejimi `budget_exhausted=False` set ediyor (çelişkili `budget_exhausted=True`+`fallback_used=True` kombinasyonu kalktı, güvenlik ağı davranışı korunur); §12.17 yeni uçtan-uca pipeline wiring testi `table_selection_cost_model` config override'ının seçim sonucunu fiilen değiştirdiğini kanıtlıyor. **D** §12.6 `personalized_pagerank` scipy eksikliğini `(ImportError, ModuleNotFoundError)` olarak ayrı yakalayıp DEBUG logluyor (scipy bağımlılığı eklenmedi); §11.3 regression-gate `--version` artık `^v?\d+\.\d+(\.\d+)?$` ile doğrulanıyor (uyumsuz değer `exit 2`); §12.7 VERIFY-CLOSE — kod değişikliği yok, `bench_contract.py`/`bench_cli.py` zaten 28.1–28.3 dalgalarında senkronlanmıştı (5 hedef, "4-way"/`2000` metni yok, `--scales` yardımı `100,500,1000`). Full suite ve CI perf-gate (`--gate --scales 100,500,1000`) yeşil. **Yapısal borçlar bilinçli AÇIK bırakıldı** (sessiz düşürme yok): `scan_cap`→DB-aggregation kökü (§7.1/§8.3/§9.2/§10.3), retry-token eksik-sayımı (§9.1), onay-state persistence (§10.1), semantik dedup (§10.2), gerçek-accuracy/case-granülarite (§11.1/§11.2/§11.4/§11.5), Phase 9/12 kalemleri (§12.4/5/9/10/11/12/13/14/15). PR `#154`.* |
| 28.4 | Relationship Confidence Scoring | ✅ Tamam · *`TableSelectionCostModel`'in düz `explicit_neighbor`/`implicit_neighbor` (20.0/10.0) ağırlıklarını tek bir `neighbor_base: float = 20.0` ile birleştiren ve komşu benefit'ini **çarpımsal** hale getiren sprint (`neighbor_benefit(rel_confidence, model) = neighbor_base × (conf if conf is not None else 1.0)`). `select_schema_context`'te EXPLICIT/CUSTOM/IMPLICIT komşu genişletmesi artık `neighbor_base × effective_confidence` ile skorlanır (explicit/custom ilişki `confidence=None` → 1.0, implicit ilişki 0.60–0.90 aralığında); `IMPLICIT_FUZZY` komşular yeni `include_fuzzy_neighbors: bool = False` ile **opt-in** (varsayılan kapalı) — güven tek güven sinyali, tip-ağırlık çifte-sayımı yok. `probe`/`node_budget`/`cost_budget`/seçim/join-path/fallback davranışı DEĞİŞMEDİ. Muhafazakâr `neighbor_base=20.0` mevcut fixture'larda **davranış-koruyucu** (golden şemanın 6 kenarı hepsi explicit conf=None → `20×1.0=20` = eski `explicit_neighbor`); golden eval yeşil, fixture kürasyonu **gerekmedi**. **Benchmark: versiyon bump GEREKMEDİ** — `context_selection` metrikleri committed **v4** baseline'ıyla byte-identical (sentetik şema yalnız explicit-FK içeriyor → komşu benefit'i etkilenmedi); gate yeşil (exit 0). `join_paths`/`implicit_fk` dokunulmadı. Full suite 2490 passed/9 skipped. PR `#155`.* |
| 28.5 | Missing Foreign Key Inference v2 | ✅ Tamam · *`detect_implicit_relationships`'i (`app/schema/implicit_relationships.py`) PK-aware hale getiren sprint. Yeni saf `resolve_target_key(table) -> str \| None`: tek-kolonlu deklare PK (`ColumnSchema.primary_key`/`TableSchema.primary_key_columns`) → o kolon; composite PK (2+ deklare kolon) → `None`; deklare PK yoksa `"id"` sonra `"<singular_table>_id"` konvansiyon fallback'i; hiçbiri yoksa `None`. Rule 1 (`singular_table_id_pattern`, conf 0.90) ve Rule 2 (`fuzzy_prefix_to_table_match`, IMPLICIT_FUZZY conf 0.75/0.65) artık hardcoded `"id"` yerine `resolve_target_key(tgt)`'i hedefler → **recall**: `id` olmayan PK'li tablolarda artık ilişki yakalanıyor. Rule 3 (`exact_non_generic_column_match`, conf 0.60) artık YALNIZ kaynak kolon adı hedefin çözülmüş anahtarına eşitse tetikleniyor → **precision**: PK olmayan bir kolona rastgele isim-eşleşmesiyle kurulan spurious FK kenarları düşüyor. Confidence değerleri ve `reason` string'leri KORUNDU (benchmark `derive_implicit_fk_metrics` bucketing etkilenmedi); `raw["target_key"]` yeni alan eklendi. Production (`schema_manager.py`) çıkarımı iyileşir; schema-only ve deterministik kalır. **Benchmark v5** (`large_schema_benchmark_v5`): `implicit_fk` hedefinde `rule3_exact` 461/13024/56449 → **0** (scale 100/500/1000) — v1 on binlerce spurious non-key kenar çıkarıyordu; `implicit_rels_found` artık yalnız rule1+rule2 (92/730/1472). Diğer implicit_fk sayaçları (`fuzzy_comparison`/`pair_iteration`/`rule3_scan`/vb.) DEĞİŞMEDİ. **`join_paths`/`context_selection`/`graph_backend` v4'e göre BYTE-IDENTICAL** (select_schema_context/find_join_paths explicit FK üzerinde çalışır, implicit-detection çıktısını tüketmez — coupling yok). Gate yeşil (exit 0). **Bilinçli kapsam dışı** (TECH-DEBT §13): type-uyumluluk sinyali/gate, config-driven eşikler (confidence/fuzzy-ratio/generic-liste hardcoded kalır), unique-ama-PK-olmayan hedefler (PK-only tasarım), composite-PK FK çıkarımı (tek-kolon PK'ye odaklanılır), veri örneklemesi/value-overlap/cardinality (schema-only kalır). Full suite 2501 passed/9 skipped. PR `#156`.* |
| 28.6 | Schema Cache Invalidation |
| 28.7 | Incremental Schema Sync |
| 28.8 | Embedding / RAG Re-Index Pipeline |
| 28.9 | Semantic / Result Cache |

> Not: Bu faz, frontend'deki `maxNodesLimit=5` geçici çözümünün (bkz.
> `docs/TECH-DEBT.md`) kalıcı çözümünü de kapsamalıdır.

---

## Phase 10 — Real Database Adapter Layer
**Amaç:** Contract-first yaklaşımı bozmadan **gerçek** database adapter'larını
güvenli şekilde eklemek. *(25.x stub'larının production karşılığı.)*

| Sprint | İş |
|---|---|
| 29.0 | PostgreSQL Docker Integration Adapter |
| 29.1 | PostgreSQL Read-Only Execution *(25.8 stub'ının gerçeği)* |
| 29.2 | PostgreSQL EXPLAIN-Only Mode |
| 29.3 | Oracle Contract Adapter *(25.9 stub'ının gerçeği)* |
| 29.4 | Oracle Docker/Test Harness Strategy |
| 29.5 | MySQL Adapter Contract |
| 29.6 | SQL Server Adapter Contract |
| 29.7 | Adapter Conformance Eval Suite |

---

## Phase 11 — API / Backend Productization
**Amaç:** Internal backend'i product-grade public/backend API yüzeyine
dönüştürmek.

| Sprint | İş |
|---|---|
| 30.0 | Public Query API Contract |
| 30.1 | Workspace API |
| 30.2 | Connection Registry API |
| 30.3 | Schema Sync API |
| 30.4 | Query Run API |
| 30.5 | Query History API |
| 30.6 | Feedback API |
| 30.7 | Admin API |
| 30.8 | Authentication (AuthN: login / SSO / API keys / sessions) |

---

## Phase 12 — UI / UX Production Layer
**Amaç:** Kullanıcının doğal dil sorgu yazdığı, schema graph gördüğü, SQL
açıklamasını ve execution sonucunu takip ettiği production UI katmanını
olgunlaştırmak.

| Sprint | İş |
|---|---|
| 31.0 | Query Composer UX |
| 31.1 | Schema Explorer UX |
| 31.2 | Relationship Graph UX |
| 31.3 | SQL Explanation Panel |
| 31.4 | Execution Result Viewer |
| 31.5 | Error / Warning UX |
| 31.6 | Query History UX |
| 31.7 | Feedback UX |
| 31.8 | Connection Onboarding / Schema Import UX |

---

## Phase 13 — Deployment / Cloud / Ops
**Amaç:** Production deployment, env config, secrets, migration, queue, health
check, backup/restore ve logging altyapısını kurmak.

| Sprint | İş |
|---|---|
| 32.0 | Production Docker Compose |
| 32.1 | Environment Config Contract |
| 32.2 | Secrets Management |
| 32.3 | Database Migration Strategy |
| 32.4 | Background Job Worker |
| 32.5 | Queue System |
| 32.6 | Rate Limiting |
| 32.7 | Health Checks |
| 32.8 | Backup / Restore |
| 32.9 | Logging Pipeline |
| 32.10 | LLM Provider Resilience & Failover |
| 32.11 | CI/CD Release Pipeline + Staging |
| 32.12 | API Load / Concurrency Testing |

---

## Phase 14 — SaaS / Multi-Tenant Readiness
**Amaç:** Organization, workspace, user roles, RBAC, billing, usage metering ve
admin console ile SaaS readiness sağlamak.

| Sprint | İş |
|---|---|
| 33.0 | Organization / Workspace Model |
| 33.1 | User Roles |
| 33.2 | RBAC |
| 33.3 | Billing Boundary |
| 33.4 | Usage Metering |
| 33.5 | Plan Limits |
| 33.6 | Audit Log UI |
| 33.7 | Admin Console |

> ⚠️ Phase 7 ile örtüşme için yukarıdaki nota bakın.

---

## Phase 15 — Desktop Readiness
**Amaç:** Mac ve Windows desktop versiyonları için local connection vault, local
schema cache, offline mode, packaging, signing ve auto-update mimarisini
hazırlamak.

| Sprint | İş |
|---|---|
| 34.0 | Desktop Architecture Decision |
| 34.1 | Local Connection Vault |
| 34.2 | Local Schema Cache |
| 34.3 | Offline Mode |
| 34.4 | Electron Packaging |
| 34.5 | macOS Signing / Notarization |
| 34.6 | Windows Installer |
| 34.7 | Auto Update |

---

## Kalite incelemesinde eklenen sprintler (2026-06-18)

Aşağıdaki 15 sprint bir kalite/gap incelemesi sonucu yukarıdaki fazlara
**eklenmiştir** (gerekçeler PR #124):

- **Sürekli değerlendirme (en kritik):** `27.10` Per-Release Accuracy Regression
  Gate, `29.7` Adapter Conformance Eval, `26.11` Policy/Security Eval — Sprint
  21–25'te kurulan eval harness'ını sürdürür (yoksa yeni adapter/policy/API
  eklendikçe doğruluk sessizce geriler).
- **Güvenlik:** `26.8` Prompt-Injection/NL Abuse Defense, `26.9` Result-Set
  Privacy & Limits (dönen satır verisindeki PII + satır/boyut tavanı),
  `26.10` Connection Credential Vault (server-side).
- **Maliyet & dayanıklılık:** `27.8` Cost & LLM Usage Telemetry,
  `32.10` LLM Provider Resilience & Failover (NIM ~40 RPM).
- **Performans:** `28.8` Embedding/RAG Re-Index Pipeline, `28.9` Semantic/Result
  Cache.
- **Ürün:** `30.8` Authentication (AuthN — RBAC'ın eksik tamamlayıcısı),
  `31.8` Connection Onboarding/Schema Import UX, `32.11` CI/CD + Staging,
  `32.12` API Load/Concurrency Testing.
- **Feedback'i tüketme:** `27.9` Feedback Review → Rule Suggestion — `27.3`'ün
  topladığı feedback'i (manuel onaylı) kurala çevirir; öğrenen sistemin minimal
  tohumu.
