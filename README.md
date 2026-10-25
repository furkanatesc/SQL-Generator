# SQLGen

Text-to-SQL for large enterprise schemas: ask in natural language (or upload an Excel request
form) and get validated SQL for your target dialect.

[English](#english) · [Türkçe](#türkçe)

---

## English

### What it does

- **Schema relation engine** — merges physical foreign keys, user-defined virtual relations and
  inferred (name-based) relations into one graph; relations can also be disabled.
- **Schema pruning** — picks seed tables for the question and finds bridge tables over the relation
  graph, so the LLM only sees the sub-schema it needs.
- **Generate → validate → correct** — an LLM (NVIDIA NIM, with model failover) drafts the SQL,
  SQLGlot validates it against the dialect, and a critic step feeds errors back for a retry.
- **RAG** — Qdrant stores schema embeddings, business rules and approved past queries used as
  few-shot examples. Embeddings are multilingual, so Turkish questions match English schemas.
- **MCP server** — exposes schema and SQL-generation tools to Claude Desktop, Cursor, etc.
- **UI** — Vue 3 app (also packaged with Electron) with schema explorer, relationship graph,
  live job logs (SSE), result viewer and query history.

Supported databases: SQLite, PostgreSQL, Oracle, MySQL, SQL Server.

### Architecture

```
Vue 3 UI / Electron ──REST + SSE──► FastAPI backend ◄── MCP server (stdio)
                                       │
                                       ├─ schema graph + pruning
                                       ├─ Qdrant (RAG)
                                       ├─ LLM → SQLGlot validator → critic
                                       └─ background job worker (SQLite queue)
```

### Quick start

Requirements: Python 3.11, Node.js 18+, an NVIDIA NIM API key (build.nvidia.com).

```bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
set NVIDIA_API_KEY=your_key    # macOS/Linux: export NVIDIA_API_KEY=your_key
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev

# Optional: desktop app
cd electron && npm install && npm start

# Optional: MCP server
cd backend && python mcp_server.py
```

Production (backend, worker, frontend):

```bash
docker compose -f docker-compose.prod.yml up -d --build --wait
```

### Documentation

- [Environment variables](docs/env-contract.md)
- [Production runbook](docs/production-runbook.md)
- [Database migrations](docs/database-migrations.md)
- [Release notes](docs/product-v1-release-notes.md) · [Known limitations](docs/product-v1-known-limitations.md)

### License

[MIT](LICENSE)

---

## Türkçe

### Ne yapar

- **Şema ilişki motoru** — fiziksel foreign key'leri, kullanıcının tanımladığı sanal ilişkileri ve
  kolon adlarından çıkarılan ilişkileri tek bir grafikte birleştirir; ilişkiler devre dışı da
  bırakılabilir.
- **Şema budama** — soruya göre başlangıç tablolarını seçer, ilişki grafiği üzerinden köprü
  tabloları bulur; LLM yalnızca gereken alt şemayı görür.
- **Üret → doğrula → düzelt** — LLM (NVIDIA NIM, model failover ile) SQL taslağını yazar, SQLGlot
  hedef diyalekte göre doğrular, eleştirmen adımı hataları geri besleyip yeniden dener.
- **RAG** — Qdrant; şema embedding'lerini, iş kurallarını ve few-shot örnek olarak kullanılan onaylı
  geçmiş sorguları tutar. Embedding'ler çok dilli olduğu için Türkçe sorular İngilizce şemalarla
  eşleşir.
- **MCP sunucusu** — şema ve SQL üretim araçlarını Claude Desktop, Cursor vb. araçlara açar.
- **Arayüz** — Vue 3 uygulaması (Electron ile masaüstü olarak da paketlenir): şema gezgini,
  ilişki grafiği, canlı iş logları (SSE), sonuç görüntüleyici ve sorgu geçmişi.

Desteklenen veritabanları: SQLite, PostgreSQL, Oracle, MySQL, SQL Server.

### Hızlı başlangıç

Gereksinimler: Python 3.11, Node.js 18+, NVIDIA NIM API anahtarı (build.nvidia.com).
Kurulum komutları yukarıdaki [Quick start](#quick-start) bölümüyle aynıdır.

Production (backend, worker, frontend):

```bash
docker compose -f docker-compose.prod.yml up -d --build --wait
```

Ayrıntılar için [Documentation](#documentation) bölümündeki dokümanlara bakın.

### Lisans

[MIT](LICENSE)
