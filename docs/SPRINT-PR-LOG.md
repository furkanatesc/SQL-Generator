# Sprint & PR Günlüğü (Baştan Sona)

Bu dosya, projenin **tüm geliştirme adımlarını baştan sona** (ilk commit → bugün)
sprint ve PR bazında listeler. `main` branch git geçmişinden üretilmiştir
(177 commit, #1–#121 PR + numarasız erken PR'lar).

- Sürüm/özet görünümü için: `CHANGELOG.md`
- İleriye dönük plan ve "şu an neredeyiz": `ROADMAP.md`
- İleriye dönük (henüz yapılmamış) sprintler: `docs/PLANNED-SPRINTS.md`
- Eski sürüm-tasarım notları (arşiv): `docs/archive/`

> ⚠️ **Numara tutarsızlıkları (faithful):** Gerçek geçmişte sprint numaraları
> yer yer tekrar ediyor (ör. iki ayrı "Sprint 21.0", iki "21.1") ve bazı PR
> numaraları atlanmış/kapatılmış (#8, #23, #32, #36 merge edilmemiş). Aşağıdaki
> tablo geçmişi olduğu gibi yansıtır, düzeltmez.

---

## Faz 0 — Bootstrap & Çekirdek Pipeline · 2026-05-23
| Adım | Açıklama |
|---|---|
| Initial commit | Proje iskeleti |
| Çekirdek | schema lexicon, trace store, SQL validator |
| Patch 0–5.1 | TextNormalizer, tokenizer & generic token yönetimi, RAG skor eşiği + tracing, CandidateStore + sinyal toplama, hibrit synonym repository, mini golden query & regression testleri, test hijyeni |

## Sprint 2 — Graph Module Extraction · 2026-05-23 → 05-24
| PR | Açıklama |
|---|---|
| PR 2.1 | Graph modüllerinin ayrıştırılması (`schema_graph/`) |
| PR 2.2 / 2.2.1 | Token budget + hub detector; path mode, hub reasons, object traces |
| (refactor) | Candidate modelleri `schema_candidates.py`'ye; `GraphPruner` + subgraph seçimi; `SchemaPruner` delegasyonu |
| PR 2.4 | Sprint 2 Final Hardening |

## Sprint 3 — Trace & Debug API · 2026-05-24
| PR | Açıklama |
|---|---|
| PR 3.1 | Trace Model + InMemoryStore |
| PR 3.2 / 3.2.1 | `SQLiteTraceStore` + connection lifecycle sağlamlaştırma |
| PR 3.3 | Debug Trace API endpoint'leri (+ `verify_api_key`) |
| PR 3.4 | Trace capture entegrasyonu |
| PR 3.5 | SQL validation result capture |
| PR 3.6 | SQL guardrails |
| PR 3.7 | Debug trace API filtreleme + pagination |
| (test) | Sprint 3 trace/debug API sözleşmelerinin kilitlenmesi |

## Sprint 4 — Evaluation Harness · 2026-05-24 → 05-25
| PR | Açıklama |
|---|---|
| PR 4.1 / 4.1.1 | Eval harness iskeleti + mini golden dataset; Backend CI workflow |
| PR 4.2 / 4.2.1 | Golden dataset genişletme + SQL feature checks; test DB izolasyonu |
| (eval) | Suite result + stable JSON reporting, smoke/large profilleri, fake pipeline, CLI exit-code semantiği |
| #1–#3 | CI'da smoke eval + log netleştirme + Sprint 4 eval sözleşme kilidi |

## Sprint 5–6 — LLM Provider Seam · 2026-05-25
| PR | Açıklama |
|---|---|
| #4 | Provider interface sözleşmesi |
| #5 | SQL generation request/response sözleşmesi |
| #6 | Deterministik fake provider seam |
| #7 | Manuel NVIDIA provider adaptörü |

## Sprint 7–10 — SQL Dialect & Guardrails · 2026-05-25
| PR | Açıklama |
|---|---|
| #9 | Dialect validation sözleşmesi |
| #10–#11 | CTE read-only + comment injection guardrail sözleşmeleri |
| #12 | Tehlikeli komut fonksiyonlarının reddi |
| #13–#14 | Guardrail denylist regression; pipeline'da unsafe SQL reddi |
| #15–#16 | Guardrail hatasında SQL sanitize; fail-fast |

## Sprint 11 — API & Contract Freeze · 2026-05-25 → 05-27
| PR | Açıklama |
|---|---|
| #17–#22 | Job response shape, pipeline error envelope, job request validation, safe failure, API pipeline integration, error type taxonomy sözleşmeleri |
| #24–#27 | Trace failure/success consistency, attempt metadata debug, redaction/no-secret trace sözleşmeleri |
| #28–#41 | Eval sözleşmeleri: case schema, runner determinism, SQL equivalence normalization, report, release gate, CLI exit code, golden fixture/equivalence/report + CI gate |
| #42–#46 | API request/response schema, pagination, jobs filter/sort sözleşmeleri |

## Sprint 12 — Read-only SQL Execution · 2026-05-27
| PR | Açıklama |
|---|---|
| #47 | Read-only execution sandbox |
| #48 | Query timeout enforcement |
| #49 | Row limit guard |
| #50 | Result shape validation + execution error taxonomy |

## Sprint 13 — Graph Pruning Lock · 2026-06-01
| PR | Açıklama |
|---|---|
| #51 | Graph pruning mimarisinin kabul testleriyle kilitlenmesi |

## Sprint 14 — Trace Contract + Frontend Perf · 2026-06-01
| PR | Açıklama |
|---|---|
| #52 | Trace contract normalization |
| (frontend) | Büyük DB'lerde scroll/hover jitter, paint lag, occlusion culling, ReferenceError düzeltmeleri |
| #53–#55 | `TraceStore`/`InMemoryTraceStore`; `SQLiteTraceStore` kanonik sözleşmeye normalize; debug trace API'nin strict DTO + validation + redaction ile stabilize edilmesi |

## Sprint 15 — Golden NL2SQL Eval · 2026-06-03
| PR | Açıklama |
|---|---|
| #56 | Golden NL2SQL Eval Harness |
| #57 | Kolon-düzeyi eval kontrolleri |
| #58 | Eval failure reporting & check visibility |

## Sprint 16 — Runtime / Health / Docker / Release-Verify · 2026-06-03
| PR | Açıklama |
|---|---|
| #59 | `pydantic-settings` ile merkezî runtime ayarları |
| #60 | Güvenli health diagnostics endpoint |
| #61 | Startup validation warnings |
| #62–#63 | Backend Docker baseline + container runtime smoke testi |
| #64–#65 | Production runbook, ortam değişkeni sözleşmesi, deployment acceptance checklist |
| #67 | Release verification checklist |

## Sprint 17 — API Surface Freeze · 2026-06-03 → 06-04
| PR | Açıklama |
|---|---|
| #68 | API surface envanteri + OpenAPI snapshot |
| #69 | Error responses + response envelope şeması dondurma |
| #70 | API key / debug erişim sözleşmesi |
| #71 | HTTP status semantiği dondurma |
| #72 | Sözleşme yeniden üretim araçları + reviewer guardrail |

## Sprint 18 — Observability · 2026-06-04
| PR | Açıklama |
|---|---|
| #73 | Request logging |
| #74 | Request correlation |
| #75 | Performance telemetry |
| #76 | Readiness + startup diagnostics |

## Sprint 19 — Startup Config Gate · 2026-06-05
| PR | Açıklama |
|---|---|
| #77 | Startup configuration validation gate |

## 🚩 v1 Release Gate · 2026-06-05
| PR | Açıklama |
|---|---|
| #78 | Production release runbook + smoke gate |
| #79 | V1 release candidate gate |
| #80 | V1 RC verification evidence (`5ce60ae`) |
| #81 | V1 release readiness ilanı |

> ⚠️ `v1.0.0` git tag'i **atılmadı**; `docs/product-v1-rc-verification.md`
> içindeki metrikler doğrulanamıyor (bkz. CHANGELOG uyarısı).

## Sprint 20 — Schema Contract & Relations · 2026-06-05 → 06-10
| PR | Açıklama |
|---|---|
| #82 | Şema sözleşmesi (20.0) |
| #83 | Explicit FK sözleşmesi + cross-db tutarlılık (20.1) |
| #84 | Örtük ilişki tespiti sağlamlaştırma (20.2) |
| #85–#86 | Graph traversal (20.3) |
| #87 | Şema serileştirme (20.4) |

## Sprint 21 — Retrieval / Context Selection · 2026-06-10 → 06-13
| PR | Açıklama |
|---|---|
| #88–#90 | Şema context seçimi sağlamlaştırma + selector entegrasyonu + deterministik context golden gate |
| #91–#93 | SQL generation / execution result golden case'leri; e2e golden eval |
| #94 | Şema özetleme sözleşmesi |
| #95 | Embedding pipeline güvenilirliği |
| #96 | Top-k retrieval sözleşmesi |
| #97 | Context ranking |
| #98 | Token budget yöneticisi |

## Sprint 22 — Intent & Prompt Planning · 2026-06-13 → 06-14
| PR | Açıklama |
|---|---|
| #99 | Intent extraction sözleşmesi |
| #100 | Intent → context köprüsü |
| #101 | Prompt planning sözleşmesi |
| #102 | Prompt rendering sözleşmesi |
| #103 | SQL generation input assembly |
| #104 | SQL generation provider sınırı |

## Sprint 23 — Prompt Builder v2 · 2026-06-14
| PR | Açıklama |
|---|---|
| #105 | Prompt builder v2 |
| #106–#107 | Few-shot örnek seçimi (deterministik + dinamik) |
| #108 | Structured output üretimi |
| #109 | Self-check üretimi |

## Sprint 24 — Golden Dataset V2 & Execution Accuracy · 2026-06-15
| PR | Açıklama |
|---|---|
| #110 | Golden Dataset V2 sözleşmesi + loader |
| #111 | `SQLExecutionAccuracyHarness` + comparator |
| #112 | Failure analytics sözleşmesi |
| #113 | Eval gate aggregator |
| #114 | Regression dashboard sözleşmesi |

## Sprint 25 — Multi-DB / Connection / PostgreSQL · 2026-06-15 → 06-17
| PR | Açıklama |
|---|---|
| #115 | Çoklu veritabanı execution sözleşmesi |
| #116 | Connection abstraction katmanı |
| #117 | Connection-aware execution planner |
| #118 | Connection-aware execution orchestrator |
| #119 | Execution accuracy orchestrator entegrasyonu (25.4) |
| #120 | Execution outcome failure analytics entegrasyonu (25.5) |
| #121 | Execution trace / audit sözleşme entegrasyonu (25.6) |
| (25.7) | **PostgreSQL adapter contract STUB** + strict False capability testleri — ⚠️ `NOT_IMPLEMENTED`, gerçek execution yok |
| #125 | **PostgreSQL Read-Only Adapter — yalnızca local Docker** — 25.7 stub'ı, local Docker'a karşı gerçek read-only SELECT çalıştıran kontrollü adapter'a dönüştürüldü (SELECT-only/tek-statement gate, read-only tx + `statement_timeout`, `max_rows` truncation, credential-safe hatalar, lazy driver import). live/remote/production capability'leri hard-False; bağlantı wire edilmediğinden orchestrator default'u inert (`NOT_IMPLEMENTED`). CI'da `postgres:16` servisi. |
| #126 | **Oracle Adapter Contract STUB** — Oracle adapter'ın gerçek implementasyonu **yok**; sadece uyacağı sözleşme kilitlendi (`SQLOracleAdapterCapability` tüm execution flag'leri `False`, immutable contract, deterministic `NOT_IMPLEMENTED`/`REJECTED`, secret-safe result — sadece `sql_sha256`). cx_Oracle/oracledb/SQLAlchemy/JDBC/socket/DSN/TNS/wallet/env-secret **yasak** (testlerle kilitli). ⚠️ Gerçek Oracle execution Phase 10'da (29.3 adapter, 29.4 Docker/test harness). **Phase 6 (adapter stub'ları) burada kapanır.** |

## Phase 7 — Security & Governance · Sprint 26.x · 2026-06-18 → …
| PR | Açıklama |
|---|---|
| (26.0) | **SQL Permission Policy Contract** — backend'in ilk güvenlik/governance sözleşmesi. Bir SQL çalışmadan önce "izinli mi / deny mi / approval mı, neden?" sorusuna deterministik cevap veren contract. `SQLPermissionPolicyContract.evaluate()` → ALLOW/DENY/REQUIRES_APPROVAL + audit reason code (`default_deny`, `unknown_action`, `missing_subject`, …). **Fail-closed**: bilinmeyen action/resource, eksik subject/resource, konfigüre edilmemiş policy → hep DENY. Immutable request/result, secret-free result (context — connection string/password/token — sonuca sızmaz). Enforcement engine / tenant / RBAC / AuthN **yok** (sırasıyla 26.1–26.11). `backend/app/security/`. (#127) |
| (26.1) | **Tenant / Workspace Boundary Contract** — her güvenlik/policy kararının hangi tenant/workspace sınırında geçerli olduğunu temsil eden contract; cross-tenant leakage'a karşı izolasyon boyutu. `TenantWorkspaceBoundaryContract.validate()` → ALLOW/DENY + audit reason code (`boundary_match`, `missing_tenant`, `missing_workspace`, `tenant_mismatch`, `workspace_mismatch`; `unknown_boundary`/`invalid_boundary` ileriye dönük rezerve). **Fail-closed**: eksik tenant/workspace, tenant/workspace mismatch → hep DENY; tenant kontrolü workspace'ten önce. Immutable request/result, JSON-safe `to_dict()`; request'te `context` yok, deny'de tenant/workspace echo edilmez (secret-free). RBAC/AuthN/persistence/API/UI ve 26.0 composition **yok**. `backend/app/security/tenant_workspace_boundary.py`. (#128) |
| (26.2) | **Read-Only Enforcement Hardening** — "bu SQL gerçekten read-only mi?" sorusunu dağınık string check'lerden çıkarıp tek, deterministik, contract-first enforcement katmanına bağlar (güvenlik üçgeninin SQL ayağı). `SQLReadOnlyEnforcementContract.enforce()` → ALLOW/DENY + audit reason code (`read_only_select`, `empty_sql`, `multi_statement`, `non_select_statement`, `forbidden_keyword`, `unsafe_procedure`, `unsafe_data_movement`, `invalid_sql_type`). **Fail-closed**: tek-statement SELECT (veya read-only `WITH … SELECT`) dışında her şey DENY. Sınıflandırmadan önce SQL lex edilir (yorumlar sökülür, string literal + tırnaklı identifier maskelenir); sadece çalıştırılabilir kod taranır — `SELECT comment FROM t` / `SELECT * FROM "merge"` yanlış reddedilmez, ama gerçek konumdaki `;`/write verb (injection kuyruğu dâhil) yakalanır. `SELECT … INTO` ve CTE içi `INSERT/UPDATE/DELETE` her yerde; DDL/`COPY`/`MERGE`/procedure leading verb. Bilinen sınır: fonksiyonla yazma (`setval`/`lo_export`) string katmanda ALLOW; savunması DB read-only session. Result ham SQL taşımaz — yalnızca `sql_sha256` + leading keyword (`normalized_prefix`). **PostgreSQL ve Oracle** adapter'ları artık bu ortak gate'e delege eder (cross-adapter divergence kapalı). PostgreSQL adapter'ın `validate_read_only_select` gate'i artık bu ortak contract'a **delege** eder (forbidden keyword listesi tek yerde; mevcut rejection davranışı korunur, yalnızca sıkılaşır). Risk classifier / sensitive policy / PII / audit / approval, yeni adapter, gerçek execution, API/UI, tenant/RBAC/AuthN **yok**. `backend/app/security/sql_read_only_enforcement.py`. (#129) |
| (26.3) | **Query Risk Classifier** — bir SQL sorgusunun *statik* (çalıştırmadan) risk seviyesini deterministik sınıflandıran contract; **gate değil, sinyal üreticisidir** (allow/deny vermez). `SQLQueryRiskClassifier.classify()` → risk_level `LOW/MEDIUM/HIGH/CRITICAL` + tetiklenen signal listesi (`select_star`, `no_where_filter`, `no_row_limit`, `cartesian_join`, `high_join_count`, `side_effecting_function`, `unbounded_result`, `invalid_or_unparseable`). **Belirsizlikte yukarı yuvarlar**: boş/non-string/comment-only/non-read → CRITICAL. `risk_level` = tetiklenen sinyallerin max severity'si; hiç yoksa LOW. 26.2'nin `_sql_text` sanitize'ını paylaşır (literal/yorum içindeki keyword/fonksiyon sinyal tetiklemez). 26.2'nin bilinen sınırını (`SELECT setval(...)`/`lo_export`/`pg_terminate_backend` gibi fonksiyonla yazma) **CRITICAL** olarak görünür kılar (engellemez). Result ham SQL taşımaz — `sql_sha256` + leading keyword. Refactor: 26.2/26.3 ortak `app/security/_sql_text.py` helper'ına bağlandı. Sensitive/PII policy (26.4+), audit, approval, gerçek parser/EXPLAIN, execution, API/UI, RBAC/AuthN **yok**. `backend/app/security/sql_query_risk_classifier.py`. *(PR pending)* |
| (26.4) | **Sensitive Table / Column Policy** — beyan-tabanlı (declaration-driven) hassas tablo/kolon gate'i; **gate** kararı + sinyal. `evaluate()` → ALLOW/DENY/REQUIRES_APPROVAL + eşleşen (matched) tablo/kolon ve hassasiyet seviyesi sinyali. **Hibrit referans**: explicit (beyan edilen) eşleşme = sound; SQL'den tablo/kolon çıkarımı = best-effort. Immutable request/result, secret-free. `backend/app/security/sql_sensitive_data_policy.py`. *(local squash-merge)* |
| (26.5) | **PII / PHI Detection Contract** — heuristik PII/PHI **detector** (sinyal, gate değil): kategori + PII/PHI veri-sınıfı + güven (confidence). **3 katman**: declared = sound; identifier-isim + literal-değer/Luhn = best-effort. Secret-free sonuç (ham değer sızmaz). `backend/app/security/sql_pii_phi_detection.py`. *(local squash-merge)* |
| (26.6) | **Audit Event Contract** — deterministik, secret-free audit kaydı + tamper-evident SHA-256 hash-chain. 26.0–26.5 sonuçlarını tek immutable `AuditEvent`'e normalize eden 6 builder (OWASP-style kategoriler, NIST SP 800-92 6-soru çekirdeği); zaman/ID caller-supplied. `verify_chain` mutation/reorder/insert/delete yakalar (integrity-evident; non-repudiation Phase 13). `backend/app/security/audit_event.py`. *(local squash-merge)* |
| (26.7) | **Approval Workflow Contract** — saf deterministik approval state machine (I/O & clock yok, time/id caller-supplied, frozen dataclass, secret-free). PENDING + terminal (APPROVED/REJECTED/EXPIRED/CANCELLED); fail-closed `from_permission` (N=1) / `from_sensitive` (CONFIDENTIAL→1, RESTRICTED→2); approve/reject quorum N-of-M + SoD (requester≠approver) + duplicate-vote guard + single-reject veto + terminal immutability; caller-driven expire; audit interlock (`AuditCategory.APPROVAL` + `from_approval`). `backend/app/security/approval_workflow.py`. *(local squash-merge)* |
| (26.8) | **Prompt-Injection / NL Abuse Defense** — Phase 7'nin **doğal dili** (SQL değil) inceleyen ilk contract'ı; kaynak-duyarlı (source-aware) detector (sinyal + advisory disposition, gate değil; secret-free, no-I/O, stdlib-only, frozen). 6 `InjectionCategory` (INSTRUCTION_OVERRIDE, SYSTEM_PROMPT_EXFIL, ROLE_HIJACK, DELIMITER_BREAKOUT, OBFUSCATION_EVASION, SQL_ABUSE_INTENT) + DIRECT/INDIRECT kaynak + confidence LOW<MEDIUM<HIGH + disposition ALLOW<REVIEW<BLOCK; per-segment tespit; NFKC normalize + **Türkçe-güvenli** obfuscation sinyali (homoglyph yalnız Cyrillic/Greek code point'leri). `evaluate`/`_aggregate`: any HIGH veya any INDIRECT≥MEDIUM → BLOCK; herhangi eşleşme → REVIEW; aksi ALLOW. Audit interlock (`AuditCategory.PROMPT_INJECTION` + `from_prompt_injection`). OWASP LLM01:2025 temelli. `backend/app/security/prompt_injection_defense.py`. *(local squash-merge → main `c733be4`)* |
| (26.9) | **Result-Set Privacy & Row/Size Limits** — Phase 7'nin **post-execution** sonuç kümesi (gerçek dönen satır/kolon) üzerinde çalışan ilk contract'ı; hibrit: limit **GATE** (ALLOW/TRUNCATE/DENY — caller policy `max_rows`/`max_bytes`/`max_columns` + `truncate_allowed`) + advisory privacy **SIGNAL** (26.5 value-scan'i tekrar kullanan kolon-seviyesi PII/PHI özeti; secret-free). Audit interlock (`AuditCategory.RESULT_SET_PRIVACY` + `from_result_set`) + public exports. Paylaşılan tarayıcı `_pii_value_scan.py`'ye çıkarıldı. PHI yolu yapısal olarak erişilemez (yalnız PII kategorileri üretilir) → bilinçli olarak inert iskele, spec §11/§12 + docstring'de belgeli. `backend/app/security/result_set_privacy_limits.py`. *(local squash-merge → main `6886288`)* |
| (26.10) | **Connection Credential Vault** — saf, deterministik, **secret-free**, I/O-free governance contract: bir call context'in bir connection `secret_ref`'i **resolve** edip edemeyeceğine karar veren gate + reference-only alanlara ham-secret sızıntısını işaretleyen advisory sinyal. Ham parola/connection-string/token'ı asla tutmaz/saklamaz/çözmez — yalnız *referansı* ve *kararı* yönetir. Gate = 6 erişilebilir boyut, deterministik öncelik (tek reason_code kazanır): leak → auth_mode → provider allowlist → environment → tenant → caller purpose → ALLOW. 7 reason code. `app.evaluation.connection_abstraction` profil tiplerini girdi olarak tekrar kullanır; leak taraması marker adı döner (asla değer). Audit interlock (`AuditCategory.CONNECTION_CREDENTIAL` + `from_credential_vault`; ALLOW→ALLOWED/INFO, DENY→DENIED + HIGH-if-leak-else-MEDIUM). Public API PEP 562 lazy `__getattr__` ile export edilir → driver-isolation invariant'ı korunur (`import app.security` driver yüklemez). `backend/app/security/connection_credential_vault.py` + `_secret_pattern_scan.py`. *(local squash-merge → main `f9a815c`)* |
| (26.11) | **Policy / Security Eval** — Phase 7'nin **son** sprint'i; saf, deterministik, **secret-free**, I/O-free **meta-evaluation harness** 26.0–26.10 güvenlik contract'ları üzerinde. `backend/app/evaluation/`'da yaşar → `app.security` driver-free kalır (driver-isolation invariant'ı doğrulandı: `import app.security` `urllib` yüklemez). Bileşenler: normalize `SecurityEvalOutcome(verdict, codes)` + exact-match `run_security_eval` runner; 11 per-contract **projector** + `PROJECTOR_REGISTRY` (**enum-purity invariant**: yalnız enum `.value` üretir); 22 in-code typed **blessed golden case** (1-2/contract, her biri gerçek contract'ı çağırır); enum-introspection **coverage** (`COVERAGE_UNIVERSE` − 8 declared exclusion → gaps); PASS/WARN/FAIL **gate aggregator** (`SQLEvalGate` şeklini aynalar; case mismatch→FAIL, coverage gap→WARN by default); entegrasyon meta testi (baseline green + `covered ⊆ universe`). Bilinçli kapsam-dışı: audit interlock yok, JSON/YAML loader yok. SDD ile inşa edildi (6 görev, her biri TDD + task review; opus whole-branch review = merge-ready, 0 Critical/Important). Full suite 1965 passed/9 skipped. `backend/app/evaluation/security_policy_eval{,_projectors,_cases,_coverage,_gate}.py`. *(local squash-merge → main `69d86c3`)* |

## Phase 8 — Observability & Debuggability · Sprint 27.x · 2026-06-30 → …
| PR | Açıklama |
|---|---|
| (27.0) | **End-to-End Trace Contract** — Phase 8'in **ilk** sprint'i; saf, deterministik, **secret-free**, I/O-free `EndToEndTrace` sözleşmesi: SQLGen pipeline'ın per-stage çıktılarını (intent→retrieval→prompt→generation→validation→security→execution) tek `request_id` altında ilişkilendirir. **Hibrit model**: typed envelope `EndToEndTrace` + ordered `TraceSpan` tuple (stage başına typed `detail` + generic `attributes` str→str escape hatch). Bileşenler: enums (`TraceStageKind`/`TraceSpanStatus`/`TraceTerminalStatus`) + frozen records (`TraceSpanDetail`/`ExecutionSpanDetail`/`SecurityCheck`/`SecuritySpanDetail`/`TraceSpan`/`EndToEndTrace`) + cross-field `__post_init__` invariant'lar (version eşitliği, non-empty id, duplicate-stage red, COMPLETED⇒no-ERROR, non-COMPLETED⇒terminal_stage span ERROR) + JSON-safe `to_payload`; `derive_terminal` precedence (execution blocked/rejected > ilk ERROR span > COMPLETED) + `build_end_to_end_trace` assembler; **duck-typed** `build_execution_span` + `build_security_span` (attrs off `Any` via `getattr`; empty/`None`→SKIPPED) → yalnız `app.trace.*` import eder, **driver-isolation** korunur (`import app.trace.end_to_end_trace` hiçbir `app.evaluation`/DB driver yüklemez; testle kilitli). **Secret-free**: yalnız `sql_sha256` (asla ham SQL) + reason/symbol string + `redact_sensitive_text`'ten geçmiş error mesajı payload'a ulaşır. Bilinçli kapsam-dışı (27.1): kalan stage builder'ları, live pipeline wiring, persistence. SDD ile inşa edildi (5 görev + 2 pre-merge minor fix `audit_events or ()` None-guard & `derive_terminal` annotation; her görev TDD + sonnet task review; opus whole-branch review = merge-ready, 0 Critical/Important). Full suite 1998 passed/9 skipped. `backend/app/trace/end_to_end_trace{,_builders}.py`. *(local squash-merge → main `48ebad6`)* |
| (27.1) | **Remaining Stage Span Builders** — 27.0 `EndToEndTrace` çatısının builder setini **tamamlar**: kalan 5 stage'in (INTENT/RETRIEVAL/PROMPT/GENERATION/VALIDATION) saf, **duck-typed**, secret-free span builder'ları + typed `*SpanDetail` frozen record'ları (`IntentSpanDetail`/`RetrievalSpanDetail`+`RetrievalCandidateRef`/`PromptSpanDetail`/`GenerationSpanDetail`/`ValidationSpanDetail`). Builder'lar attr'ları `Any` üzerinden `getattr` ile okur; empty/`None` girdi → SKIPPED span; `derive_terminal`/`build_end_to_end_trace`/`to_payload` **değişmedi**. **Driver-isolation** korunur ve full-set assembly + izolasyon testleriyle kilitlidir (`app.trace.*` importu hiçbir `app.evaluation`/DB driver yüklemez). **Secret-free**: ham SQL/prompt/secret yok — yalnız hash/sayaç/symbol/reason string'leri. Canlı pipeline telçekimi (request_id plumbing, per-stage `perf_counter`, `_capture_trace_on_exit` emission, modüler stage routing) bilinçli olarak **27.1w Live Trace Wiring**'e ertelendi (sessiz düşürme yok; PLANNED-SPRINTS'te ⏳→▶️). SDD ile inşa edildi (6 görev, her biri TDD + sonnet task review; opus whole-branch review = merge-ready, 0 Critical/0 Important, 3 Minor → 27.1w). Full suite 2024 passed/9 skipped. `backend/app/trace/end_to_end_trace{,_builders}.py`. *(local squash-merge → main `650caf7`)* |
| #134 | **Ara fix (sprint dışı) — Şema ilişki graph'ı görünürlük düzeltmesi** (2026-07-02) — `SchemaManager.vue` D3 graph'ı top-N hub seçimini *izole tablolar dahil tüm tablolar* üzerinden yapıp yalnızca iki ucu da seçimde kalan edge'leri çizdiğinden, varsayılan `maxNodesLimit=5` ile örnek şemada (2175 tablo/93 FK) ilişkilerin yalnızca **3/93**'ü görünüyordu; "limitsiz" ise 2073'ü izole 2175 node render edip tarayıcıyı donduruyordu (TECH-DEBT #2'nin kökeni). Seçim mantığı saf `frontend/src/utils/graphSelection.ts` modülüne çıkarıldı: **izole tablolar hiç çizilmez**, limit yalnızca bağlantılı tablolar arasında uygulanır, varsayılan `0 = tüm bağlantılı` (örnek şemada 102 tablo + **93/93** ilişki), edge'ler `d3.forceLink` mutasyonuna karşı kopyalanır; panele render istatistiği rozeti eklendi. TDD: `frontend/tests/graphSelection.test.ts` (8 test, `node --experimental-strip-types`; frontend'de test framework yok). Kalan borç (çok büyük *bağlantılı* graph'lar → WebGL/virtualized, Phase 12 adayı) TECH-DEBT #2'de. *(GitHub PR squash-merge → main `8211790`)* |
| #135 | **(27.1w) Live Trace Wiring** — 27.0/27.1'in saf `EndToEndTrace` sözleşmesini **canlı pipeline'a örer** (27.1'den bilinçli ertelenmişti; sessiz düşürme yok). **`request_id` plumbing**: HTTP `X-Request-ID` → `upload_excel_file`/`start_job_without_file` → `process_job_pipeline` → `run_pipeline`; yoksa `req_` önekiyle mint edilir (`RequestLoggingMiddleware` zaten `request.state.request_id` set ediyor). **Per-stage timing**: her stage `perf_counter` ile ölçülür; writer-critic'te per-phase (prompt/generation/validation/security) `try/finally` ile — `continue`/`break` dallarında da birikir. **Dual-emit**: `_capture_trace_on_exit`'te legacy `NL2SQLTrace`'in **yanına** `TraceRecord(trace_type="end_to_end")` emit edilir (7 sabit span; koşmayan stage SKIPPED; EXECUTION Faz-1'de hep SKIPPED). **Stage refactor**: `run_pipeline` → `_stage_intent`/`_stage_retrieval`/`_stage_writer_critic`; **davranış birebir korundu** — kanıt: branch genelinde tüm test dosyaları `+N/-0`, hiçbir mevcut assert değiştirilmedi/silinmedi; `pruned_schema_tables` invariant'ı (pruning_error'da boş, context_selection_exception'da dolu) 8 commit sonunda da holds. Yeni **saf** modül `backend/app/trace/live_trace_assembly.py` (yalnız `app.trace.*` + stdlib; purity artık kendi guard testine sahip). 27.1'den devreden **3 Minor kapatıldı**. **Invariant'lar**: emisyon hatası pipeline sonucunu asla etkilemez (assembly + `TraceRecord.__post_init__`'in serialization raise'i + save tek `try/except Exception` içinde; legacy save bu bloktan önce ve koşulsuz); ham SQL payload'a girmez (yalnız sha256). **Bilinen sınır (kasıtlı, kullanıcı onaylı, CHANGELOG'da yazılı)**: dual-emit yalnız `save_legacy` expose eden store'larda çalışır (`_save_trace_safely`'nin mevcut feature-detect deseniyle tutarlı) — prod `SQLiteTraceStore` tam emit alır; eski tekil-`save()` store'lar yalnız legacy görür. SDD ile inşa edildi (8 görev, her biri TDD + sonnet task review). **Opus whole-branch review "merge after fixes" verdi ve task review'ların yapısal olarak göremediği gerçek bir bug yakaladı**: intent/security timing'leri her run'da ölçülüp sessizce düşürülüyordu — kök neden planın kendi içinde çelişmesiydi (düzyazı kuralı satır 187 "her builder'a duration_ms verilir" derken planın kendi referans kodu INTENT/SECURITY'ye geçmiyordu; implementer kodu izlemişti). Task 8 ile düzeltildi (+ purity guard testi + `TraceRecord.trace_id` artık payload id'siyle aynı). Full suite 2055 passed/9 skipped. Kalan borç: **TECH-DEBT §3** (SKIPPED span'lerde `duration_ms` düşüyor → canlı yolda INTENT süresi yalnız hata dalında iniyor; "koşmamış stage süre taşımalı mı?" semantik kararı bekliyor). `backend/app/{sql_pipeline,main}.py`, `backend/app/trace/{live_trace_assembly,end_to_end_trace_builders}.py`. *(GitHub PR rebase-merge → main `466d9ee`)* |
| #136 | **(27.2) Error Taxonomy v2** — hata taksonomisini tek registry'de topladı: saf `backend/app/errors/` yaprak paketi (`StrEnum` `ErrorCode`/`ErrorCategory` + `DESCRIPTORS`/`describe`/`category_of`; stdlib-dışı importsuz, purity testli). Kategori (hatanın *doğası*, koda ait sabit) ile stage (nerede *yakalandığı*, çalışma-zamanı verisi) eksenlerini ayırdı (v1'in "semantic_validation hem stage hem type" kusurunun düzeltmesi); `run_pipeline` sonucuna `error_code` ekledi ama **bilinçli olarak pipeline katmanında durdu** — iş/API/frontend sınır geçişi 27.2.1'e ertelendi (sessiz düşürme yok). SDD ile inşa edildi; opus whole-branch review. *(GitHub PR rebase-merge → main `fff5691`)* |
| #138 | **(27.2.1) Error Taxonomy Boundary** — 27.2'nin `error_code`'unu iş/API/frontend sınırından geçirdi: `jobs.error_code` kolonu (idempotent `ALTER` migration) + `update_job_status` **dinamik-SET refactor** (sabit whitelist'ten kurulan SET cümlesi → injection-safe; mevcut testler değişmeden geçti = davranış korundu), `JobDetailResponse.error_code`, frontend `Job.error_code` + saf `extractApiErrorMessage` helper (RAG/indexing endpoint'leri artık backend'in gerçek hata mesajını gösteriyor — `errData.detail` bug'ı düzeltildi). `ExecutionSpanDetail.error_code` beslemesi **bilinçli ertelendi** (canlı execution fazına bağımlı; SKIPPED span'e kod iliştirmek anlamsız — TECH-DEBT §4.3). Contract snapshot'ları yenilendi (yalnız `JobDetailResponse` genişledi; `required` listeleri değişmedi). SDD (5 görev, her biri TDD + task review); opus whole-branch review = merge-ready (3 Important = hepsi doküman, tek commit ile giderildi). *(GitHub PR rebase-merge → main `c1e3335`)* |
| #139 | **(27.3) User Feedback Capture** — bir SQL üretimine (`job`) dair kullanıcı feedback'ini toplayan backend yüzeyi. Saf taksonomi katmanı `backend/app/feedback/categories.py`: `FeedbackVerdict` (`correct`/`incorrect`) + `FeedbackCategory` (`wrong_table`/`wrong_column`/`wrong_filter`/`wrong_join`/`wrong_aggregation`/`wrong_order_limit`/`other`) — 27.2'nin sistem/pipeline hata taksonomisinden ayrı bir eksen (SQL başarıyla üretilmiş ama semantik olarak yanlış olabilir). Append-only `feedback` tablosu (`id`/`job_id`/`verdict`/`category`/`note`/`corrected_sql`/`created_at`, `job_id` üzerinde index) + repo fonksiyonları `create_feedback`/`get_feedback`/`get_feedback_for_job` (`backend/app/database.py`; `get_feedback_for_job` `created_at ASC, rowid ASC` ile deterministik sıralar, bilinmeyen `job_id` → boş liste). `POST /api/jobs/{job_id}/feedback` endpoint'i (`backend/app/api/feedback.py` + `schemas.py` invariant'ları) — router enum'ları `.value` olarak DB'ye geçirir, DB string saklar, response `str` alanları taşır (enum sınırı geçmez). Contract snapshot'ları yenilendi. Öğrenen sistemin tohumu: `27.9` (Feedback Review → Rule Suggestion) `get_feedback_for_job` ile tüketecek. **Bilinçli olarak backend-only**: HTTP GET listeleme/admin görünümü (`30.6`), frontend UI (`31.7`) ve `rating` alanı bu sprintte kapsam dışı. SDD ile inşa edildi (4 görev — taksonomi/persistence/API/contract-snapshot —, her biri TDD + task review; Task 5 yaşayan doküman kapanışı). *(GitHub PR rebase-merge → main `6142797`)* |
| #TBD | **(27.4) Query Replay System** — gecmis bir `job`'i bugunun kodu ve semasiyla **deterministik** olarak yeniden kosturup (LLM'e gidilmez) o gunku `end_to_end` trace baseline'iyla karsilastiran, **yan etkisiz** bir replay yuzeyi. Saf yaprak paket `backend/app/replay/`: `ReplayVerdict` (`input_unavailable`/`baseline_unavailable`/`replay_failed`/`security_regression`/`validation_regression`/`retrieval_drift`/`validation_recovery`/`identical`, oncelik sirali) + frozen `RetrievalDelta`/`ValidationDelta`/`SecurityDelta`/`ReplayResult` + saf `extract_baseline` (end_to_end payload dict'i uzerinde, nesne kurmadan) ve `compare_replay`. Tum tuple ciktilari sirali → ayni girdi ayni payload. **Seam refactor:** dogrulama zinciri (guardrail → sandbox safety → sqlglot AST → semantik → pretty-print) LLM retry dongusunun govdesinden `SQLGenerationPipeline.validate_sql`'e ayiklandi; replay artik uretimin **ayni** kodunu kosuyor (kopya mantik yalan soylerdi). Davranis birebir korundu — `retry_disposition` alani donguydeki `continue`/`break` ayrimini **veri olarak** tasir, `log_callback` seam'e gecirilerek SSE mesajlari korunur, `pretty_printed` bayragi `last_generated_sql`'in yalniz pretty-print basarili oldugunda guncellenmesini korur; kanit: mevcut test dosyalari `+N/-0`. Kirli adaptor `app/replay_service.py` job satirini + en yeni `end_to_end` trace'i okur, uretimin `_stage_intent`/`_stage_retrieval`/`validate_sql`'ini kosturur, saf karsilastiriciyi cagirir. `POST /api/debug/jobs/{job_id}/replay` (API key + `debug_endpoints_enabled` ile gated, 200 envelope; job yoksa 404). **Bilincli kapsam disi:** LLM'li tam re-run, replay sonuclarinin kaliciligi, toplu replay (27.10/28.x), frontend UI (31.x), 27.1w oncesi joblar icin legacy `nl2sql_traces` fallback'i (acikca `baseline_unavailable` doner). *(GitHub PR #TBD)* |
