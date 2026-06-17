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
> *toplar* ama planda bunu *tüketen* bir adım yok. "Öğrenen sistem" (value index,
> trace mining, rule promotion) şu an planda yok; aşağıdaki "Önerilen Ek
> Sprintler" bölümünde aday olarak değerlendiriliyor.

---

## Sprint 25 — Kalan adımlar (Multi-DB / Adapter Stubs)
| Sprint | İş | Durum |
|---|---|---|
| 25.6 | Execution Trace / Audit Contract | ✅ Tamam (#121) |
| 25.7 | PostgreSQL Adapter Contract **Stub** | ✅ Tamam (`NOT_IMPLEMENTED`) |
| 25.8 | PostgreSQL Read-Only Adapter — **Local Docker Only** | ⏳ Planlı · *stub seviyesi; gerçek execution Phase 10/29.1'de* |
| 25.9 | Oracle Adapter Contract **Stub** | ⏳ Planlı · *stub; gerçek adapter 29.3'te* |

---

## Phase 7 — Security & Governance
**Amaç:** Production security, tenant boundary, permission policy, read-only
enforcement, query risk classification, sensitive table/column policy ve audit
governance.

| Sprint | İş |
|---|---|
| 26.0 | SQL Permission Policy Contract |
| 26.1 | Tenant / Workspace Boundary Contract |
| 26.2 | Read-Only Enforcement Hardening |
| 26.3 | Query Risk Classifier |
| 26.4 | Sensitive Table / Column Policy |
| 26.5 | PII / PHI Detection Contract |
| 26.6 | Audit Event Contract |
| 26.7 | Approval Workflow Contract |

> ⚠️ Phase 14 (SaaS) ile örtüşme: tenant boundary (26.1 ↔ 33.0), RBAC/permission
> (26.0 ↔ 33.2), audit (26.6 ↔ 33.6). Phase 7 = **backend sözleşme/politika
> katmanı**, Phase 14 = **SaaS/UI katmanı** olarak ayrılmalıdır.

---

## Phase 8 — Observability & Debuggability
**Amaç:** Production'da "neden bu SQL üretildi?", "neden fail oldu?", "hangi
context seçildi?", "hangi policy blocked etti?" sorularına cevap verebilmek.

| Sprint | İş |
|---|---|
| 27.0 | End-to-End Trace Contract |
| 27.1 | Prompt / Retrieval / Schema / Execution Trace Unification |
| 27.2 | Error Taxonomy v2 |
| 27.3 | User Feedback Capture |
| 27.4 | Query Replay System |
| 27.5 | Debug Bundle Export |
| 27.6 | Metrics Contract |
| 27.7 | Admin Observability Dashboard Backend |

---

## Phase 9 — Large Schema Production Scale
**Amaç:** 2000 tabloya yaklaşan enterprise database'lerde schema selection, join
path control, missing FK inference ve graph performance problemlerini
production-grade çözmek.

| Sprint | İş |
|---|---|
| 28.0 | Large Schema Benchmark Suite |
| 28.1 | Schema Graph Performance Profiling |
| 28.2 | Join Path Explosion Control |
| 28.3 | Table Selection Cost Model |
| 28.4 | Relationship Confidence Scoring |
| 28.5 | Missing Foreign Key Inference v2 |
| 28.6 | Schema Cache Invalidation |
| 28.7 | Incremental Schema Sync |

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

## Önerilen Ek Sprintler (review bekliyor)

Bunlar planda **gözden kaçmış olabileceğini düşündüğüm** boşluklar. Henüz onaylı
değil — kabul edersen ilgili faza taşırız, istemezsen sileriz. Her biri mevcut
bir faza eklenecek şekilde önerilmiştir.

### 🔴 En kritik: Sürekli Değerlendirme (Continuous Eval)
Sprint 21–25'te **büyük bir eval/regression harness** kuruldu; ama Phase 7–15'te
bu altyapıyı **kullanan/sürdüren tek bir adım yok**. Yeni adapter, policy ve API
eklendikçe doğruluk sessizce gerileyebilir.
| Öneri | Hangi faza | Neden |
|---|---|---|
| **Per-release Accuracy Regression Gate** | Phase 8 (27.x) | Her faz çıkışında golden/execution eval gate; doğruluk düşüşünü yakalar |
| **Adapter Conformance Eval** | Phase 10 (29.x) | PG/Oracle/MySQL/MSSQL aynı paylaşılan sözleşme testinden geçsin; adapter sapması önlenir |
| **Policy / Security Eval** | Phase 7 (26.x) | Permission/PII/read-only kurallarının gerçekten enforce edildiğini doğrulayan testler |

### Güvenlik boşlukları (→ Phase 7)
| Öneri | Neden |
|---|---|
| **26.8 Prompt-Injection / NL Abuse Defense** | Query Risk Classifier üretilen SQL'i sınıflar; ama kullanıcının doğal dil girdisiyle LLM'i kandırıp (jailbreak/exfiltration) güvensiz SQL ürettirmesine karşı savunma yok |
| **26.9 Result-Set Privacy & Limits** | 26.4/26.5 *şema/kolon* PII'sini kapsar; ama dönen **satır verisindeki** PII, satır/boyut tavanı ve export kısıtı yok |
| **26.10 Connection Credential Vault (server-side)** | Phase 13 secrets = app sırları, Phase 15 vault = desktop. Sunucu tarafında gerçek DB bağlantı kimliklerinin şifreli saklanması/rotasyonu eksik |

### Maliyet & Dayanıklılık (→ Phase 8/13)
| Öneri | Neden |
|---|---|
| **27.8 Cost & LLM Usage Telemetry** | Per-request/per-tenant token + LLM maliyet ölçümü — Phase 14 "Usage Metering / Billing"i besler |
| **32.10 LLM Provider Resilience & Failover** | NIM ~40 RPM rate-limit (kendi tasarım dokümanında geçiyor); backoff + model/provider failover olmadan production'da kırılgan |

### Performans (→ Phase 9)
| Öneri | Neden |
|---|---|
| **28.8 Embedding / RAG Re-Index Pipeline** | Şema değişince (28.7 incremental sync) Qdrant embedding + business-rule RAG yeniden indekslenmeli; 28.6 cache invalidation bunu kapsamıyor |
| **28.9 Semantic / Result Cache** | Anlamca eşdeğer sorgu için doğrulanmış SQL'i pipeline'ı atlayarak döndürme — büyük maliyet/latency kazancı (eski backlog'da vardı, düşmüş) |

### Ürün boşlukları (→ Phase 11/12/13)
| Öneri | Neden |
|---|---|
| **30.8 Authentication (AuthN)** | Phase 14 RBAC = *yetkilendirme*; ama login/SSO/API-key/session = *kimlik doğrulama* hiç yok. AuthN olmadan RBAC eksik |
| **31.8 Connection Onboarding / Schema Import UX** | UI'da explorer/composer var ama "veritabanı bağla / şema içe aktar" akışı yok |
| **32.11 CI/CD Release Pipeline + Staging** | Phase 13 docker-compose'u var ama otomatik build/test/deploy ve staging ortamı yok |
| **32.12 API Load / Concurrency Testing** | 28.0 benchmark sadece şema; SaaS multi-tenant öncesi API yük/eşzamanlılık testi gerekli |

### Feedback'i tüketme (öğrenen sistem tohumu)
| Öneri | Neden |
|---|---|
| **27.9 Feedback Review → Rule Suggestion** | `27.3 User Feedback Capture` feedback'i *toplar* ama tüketen yok. En azından manuel onaylı "feedback → kural önerisi" akışı, "öğrenen sistem" fikrinin minimal ilk adımıdır |
