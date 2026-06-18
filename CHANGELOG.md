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
