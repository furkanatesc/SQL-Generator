# v6 — SaaS & Desktop Readiness

## Amaç
Ürünü (v5) iki dağıtım modeline hazırlamak: çok kiracılı **SaaS ticarileşmesi**
(organization/workspace, RBAC, billing, usage metering) ve **masaüstü dağıtımı**
(local vault, offline mode, packaging/signing, auto-update).

Kapsanan fazlar: **Phase 14 (SaaS / Multi-Tenant)**, **Phase 15 (Desktop)**.
Ayrıntılı sprint listesi: `docs/PLANNED-SPRINTS.md`.

> ⚠️ v4 ile ilişki: tenant/RBAC'in **güvenlik politikası** katmanı v4'tedir
> (permission-aware pruning, sensitive policy). v6 bunun üzerine **ticari SaaS**
> katmanını (org/workspace modeli, billing, metering, plan limits, admin
> console) ekler. İkisi çakışmamalı; v4 = politika, v6 = ticarileşme.

## Kapsam
1. Organization / Workspace veri modeli
2. User Roles + RBAC (v4 politika katmanının ürün karşılığı)
3. Billing Boundary + Usage Metering + Plan Limits
4. Audit Log UI + Admin Console
5. Desktop Architecture Decision (mimari karar)
6. Local Connection Vault + Local Schema Cache
7. Offline Mode
8. Electron Packaging + macOS Signing/Notarization + Windows Installer
9. Auto Update

## Çıktılar
- OrganizationModel / WorkspaceModel
- UserRoleService / RBACPolicyEngine
- BillingBoundary / UsageMeteringService / PlanLimitEnforcer
- AuditLogUI / AdminConsole
- LocalConnectionVault (şifreli) / LocalSchemaCache
- OfflineModeRuntime
- ElectronPackagingPipeline / macOS Notarization / Windows Installer
- AutoUpdateService

## Başarı Kriterleri
- Tenant izolasyonu: bir workspace'in verisi/şeması/bağlantısı başka workspace'e
  sızmaz (izolasyon testleri yeşil)
- RBAC: yetkisiz rol, kısıtlı tablo/kolonu ne sorgulayabilir ne de görebilir
- Usage metering doğru sayar; plan limitleri aşıldığında enforce edilir
- Billing sınırı net (kullanım → faturalanabilir olay eşlemesi)
- Local Connection Vault şifreli; credential düz metin diske yazılmaz
- Offline mode'da local schema cache ile çalışılabilir (NL→SQL üretimi
  bağlantısız da temel seviyede çalışır)
- macOS imzalı/notarize, Windows imzalı installer üretilir
- Auto-update kanalı çalışır (sürüm yükseltme + rollback)

> Bu, `docs/architecture/` zincirinin son halkasıdır: v1 (baseline) → v2
> (feedback) → v3 (graphrag) → v4 (enterprise) → v5 (productization) →
> v6 (saas/desktop).
