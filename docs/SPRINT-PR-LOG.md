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
