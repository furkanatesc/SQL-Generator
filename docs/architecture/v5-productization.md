# v5 — Productization (API / UI / Deployment)

## Amaç
v1–v4'te olgunlaşan "motoru" (engine) son kullanıcının ve entegratörün
kullanabileceği **product-grade** bir yüzeye dönüştürmek. Burada yeni model
yeteneği eklenmez; mevcut yetenek public API, production UI ve deploy/ops
altyapısıyla **ürünleştirilir**.

Kapsanan fazlar: **Phase 11 (API)**, **Phase 12 (UI/UX)**, **Phase 13 (Deploy/Ops)**.
Ayrıntılı sprint listesi: `docs/PLANNED-SPRINTS.md`.

## Kapsam
1. Public/Backend API yüzeyi (sözleşme-öncelikli)
2. Workspace / Connection Registry / Schema Sync API'leri
3. Query Run / Query History / Feedback / Admin API'leri
4. Production UI: Query Composer, Schema Explorer, Relationship Graph
5. SQL Explanation Panel, Execution Result Viewer, Error/Warning UX
6. Query History UX, Feedback UX
7. Production Docker Compose + Environment Config Contract
8. Secrets Management, Database Migration Strategy
9. Background Job Worker + Queue System
10. Rate Limiting, Health Checks, Backup/Restore, Logging Pipeline

## Çıktılar
- PublicQueryAPI (versiyonlanmış sözleşme)
- WorkspaceAPI / ConnectionRegistryAPI / SchemaSyncAPI
- QueryRunAPI / QueryHistoryAPI / FeedbackAPI / AdminAPI
- QueryComposer / SchemaExplorer / RelationshipGraph UI bileşenleri
- SQLExplanationPanel / ExecutionResultViewer / Error-Warning UX
- ProductionDockerCompose + EnvironmentConfigContract
- SecretsManager / MigrationRunner / JobWorker / QueueSystem
- RateLimiter / HealthCheckSuite / BackupRestoreRunbook / LoggingPipeline

## Başarı Kriterleri
- Public API'nin %100'ü versiyonlanmış sözleşme + contract testiyle kaplı
- Geriye dönük uyumsuz API değişikliği: sıfır (breaking change tespit gate'i)
- UI üzerinden uçtan uca akış (NL → SQL → açıklama → execution sonucu) çalışır
- D3 graph UI artık `maxNodesLimit=5` geçici çözümüne bağlı değil
  (bkz. `docs/TECH-DEBT.md`); büyük şema render'ı kabul edilebilir
- `docker compose up` ile tek komutta production benzeri ortam ayağa kalkar
- Secrets repo'da düz metin değil; migration ileri/geri çalışır
- Health/readiness check'leri + yapılandırılmış log pipeline aktif
- P95 API latency hedef eşik altında; rate limiting devrede

> Not: Bu faz **v4'ün motor/güvenlik kapsamını değiştirmez**; onu ürün yüzeyine
> taşır. SaaS ticarileşmesi (billing, multi-tenant onboarding) v6'dadır.
