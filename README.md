# SQLGen

> 🇹🇷 **Türkçe** (aşağıda) · 🇬🇧 [**English**](#-english)

---

## 🇹🇷 Türkçe

SQLGen, kurumsal ölçekteki büyük ve karmaşık veritabanlarından doğal dil sorguları ve Excel tabanlı veri talep formları aracılığıyla tamamen doğrulanmış, optimize edilmiş SQL sorguları üreten, NVIDIA NIM ve çoklu ajan (multi-agent) tabanlı bir Text-to-SQL platformudur.

Electron tabanlı masaüstü kabuğu, Vue 3 tabanlı arayüzü ve FastAPI mimarisiyle yerel ve bulut kaynaklarını asenkron olarak yönetir.

### Sistem Mimarisi

```
[ Electron Masaüstü Kabuğu ]            [ Claude Desktop / Cursor / Copilot ]
         │                                                 │
         ▼                                                 ▼ (Model Context Protocol)
[ Vue 3 Frontend (TS / Vanilla CSS) ]   ┌──────────────────────────────────────────────┐
         │ (REST API & SSE Stream)      │         SQLGen-MCP Server (FastMCP)          │
         ▼                              └──────────────────┬───────────────────────────┘
[ FastAPI Uygulama Sunucusu ]◄─────────────────────────────┘
         │ (Asenkron Arka Plan Görevleri)
         ├──────────────► [ Çok Katmanlı Şema İlişki Motoru ] (Manuel + Örtük + Fiziksel Birleştirme)
         ├──────────────► [ Grafik Tabanlı Şema Budama ] (Yerel BFS Budama - %93 Bağlam Tasarrufu)
         ├──────────────► [ Qdrant Vektör Tabanı ] (İş Kuralları ve Geçmiş SQL RAG Kataloğu)
         └──────────────► [ Çoklu Ajan İş Akışı ]
                                 │
                                 ├──► [ Writer Agent ] (NVIDIA NIM Llama-3.3 API)
                                 ├──► [ Validator Agent ] (SQLGlot AST Sentaks Doğrulayıcı)
                                 └──► [ Critic Agent ] (Otonom Hata Düzeltme / Self-Correction)
```

### Öne Çıkan Özellikler

#### 1. Çok Katmanlı Akıllı Şema İlişki Motoru
Veritabanınızda fiziksel Foreign Key tanımları eksik veya hiç olmasa bile SQLGen çalışabilir. Dört farklı katmandan gelen ilişkileri dinamik olarak birleştirir ve tek bir ilişkisel ağ oluşturur:
- **Fiziksel İlişkiler (Explicit):** PostgreSQL, Oracle ve SQLite sistemlerinden otomatik olarak taranan yabancı anahtarlar.
- **Sanal İlişkiler (Custom/Virtual):** Kullanıcının arayüzden kolayca eklediği ve yerel SQLite (sqlgen.db) ayarlarında saklanan özel manuel ilişkiler.
- **Örtük İlişkiler (Implicit):** Kolon adı kalıpları (örneğin order_id ile orders.id eşleşmesi) üzerinden sistemin otomatik keşfettiği ilişkiler.
- **Kısıtlayıcı Filtreler (Disabled):** Budama esnasında yanlış join yollarına girilmesini önlemek amacıyla kullanıcının pasifize edebildiği geçiş yolları.

#### 2. Grafik Tabanlı Deterministik Şema Budama
Yüzlerce tablo içeren şemaları yapay zekaya doğrudan göndermek, yüksek maliyetlere ve modelin kafa karışıklığına (hallucination) yol açar.
- **Tohum Tablo Belirleme:** Kullanıcı sorgusunu ve Excel talebini Jaccard benzerliği ve akıllı kolon öbekleri ile analiz ederek başlangıç (seed) tablolarını tespit eder.
- **Genişlik Öncelikli Arama (BFS):** Tohum tabloları birleştirmek için gereken köprü (bridge) tabloları, birleşik ilişki grafiği üzerinde deterministik olarak bularak en kısa join yollarını hesaplar.
- **Yüksek Bağlam Tasarrufu:** Yapay zekaya sadece sorgunun ihtiyaç duyduğu minimal alt şemayı sunarak şema boyutunu %93 oranında daraltır ve hata oranını sıfıra yaklaştırır.

#### 3. Çoklu Ajan ve Otonom Hata Düzeltme Döngüsü
SQLGen, tek bir prompt ile SQL üretip hata vermesini beklemek yerine, kendi içinde iş birliği yapan ajanlar çalıştırır:
- **Yazar Ajan (Writer):** NVIDIA NIM API (Llama-3.3-Nemotron-70B) kullanarak, budanmış alt şema, AQR kısıtları ve RAG kataloğundan gelen few-shot örnekleri ile optimize ilk taslak SQL'i yazar.
- **Doğrulayıcı Ajan (Validator):** Üretilen SQL sorgusunu SQLGlot AST (Abstract Syntax Tree) analiziyle parçalar. Seçilen veritabanı diyalekti (Oracle, PostgreSQL, SQLite, Snowflake vb.) ile sentaks uyumluluğunu test eder.
- **Eleştirmen Ajan (Critic):** Derleme hatası oluşursa, Validator'ın ürettiği AST hata logunu ve hedef şemayı analiz ederek Writer Agent'a nokta atışı düzeltme talimatı verir. Sistem otonom olarak 3 denemeye kadar kendi kendini düzelterek sıfır hatalı sorgu üretir.

#### 4. Hibrit RAG (Retrieval-Augmented Generation)
SQLGen, şirketinizin iş kurallarını ve geçmiş onaylı SQL sorgularını hafızasında tutmak için yerel bir Qdrant vektör veritabanı kullanır:
- **Schema Embedding Index (Cross-lingual):** NVIDIA'nın çok dilli (`nvidia/llama-nemotron-embed-1b-v2`, 2048 boyut) modeli kullanılarak veritabanı şemasının anlamsal parmak izi çıkartılır. Türkçe bir sorgudaki ("ülke", "müşteri") kavramları, herhangi bir çeviriye veya statik sözlüğe ihtiyaç duymadan, doğrudan anlamsal yakınlık (Cosine Similarity) ile İngilizce şema tablolarıyla eşleştirir.
- **İş Kuralları Kataloğu:** Şirket içi KPI tanımlarını ve kodlama standartlarını semantik olarak arar (örn: active = 1 filtresinin "aktif üyeler" anlamına geldiğini bilir).
- **SQL Geçmişi (Few-Shot):** Doğal dil sorgusuna benzer geçmiş başarılı sorguları bularak LLM'e bağlam içi örnekler sağlar ve başarı oranını artırır.

#### 5. FastMCP Sunucusu Entegrasyonu
SQLGen, Claude Desktop, Cursor veya Copilot gibi harici yapay zeka geliştirme araçlarının doğrudan veritabanı uzmanı olarak SQLGen'i kullanabilmesi için gelişmiş bir MCP Server barındırır:
- **FastMCP Standardı:** mcp_server.py üzerinden stdio protokolü ile çalışır.
- **Ultra-Compact Pseudo-DDL:** Şema yapısını dış LLM'lere aktarırken token maliyetini %85-90 oranında düşüren ultra kompakt bir pseudo-DDL formatı sunar.
- **Ajan Yeteneklerinin Paylaşımı:** Cursor veya Claude Desktop üzerinden geliştirme yaparken, SQLGen'in generate_validated_sql aracını çağırarak doğrudan editör içerisinden hatasız ve AST-doğrulanmış SQL sorguları üretebilirsiniz.

#### 6. Etkileşimli Ağ Grafiği ve SSE Log Akışı
- **D3.js Ağ Grafiği:** Üretilen SQL sorgusunun veritabanı şemasındaki hangi tablolardan geçtiğini, tablolar arasındaki yabancı anahtar (FK) ilişkilerini etkileşimli 3D görünümlü bir ağ grafiğiyle görselleştirir.
- **SSE (Server-Sent Events) Canlı Loglar:** Arka planda asenkron olarak çalışan işçilerin durumlarını, budama kararlarını, RAG sonuçlarını ve hata düzeltme adımlarını anlık olarak arayüze log akışı halinde basar.

### Kurulum ve Çalıştırma

#### 1. Ön Gereksinimler
- Node.js (v18+)
- Python (v3.10+)
- NVIDIA NIM API Key (build.nvidia.com adresinden alınabilir)

#### 2. Backend Kurulumu
```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows için
source venv/bin/activate  # macOS/Linux için

pip install -r requirements.txt

# Arayüzdeki Ayarlar panelinden veya çevre değişkeni olarak API anahtarınızı girin:
set NVIDIA_API_KEY=your_nvidia_nim_key

# Sunucuyu başlatın
uvicorn app.main:app --reload --port 8000
```

#### 3. MCP Sunucusunu Başlatma (Geliştirici Araçları İçin)
SQLGen'i bir MCP sunucusu olarak çalıştırıp Cursor veya Claude Desktop uygulamanıza bağlamak için:
```bash
cd backend
python mcp_server.py
```
*Cursor ayarlarında (Settings > Models > MCP) yeni bir command sunucusu ekleyip command alanına depo kök dizininizdeki `python <repo>/backend/mcp_server.py` yolunu yazarak entegrasyonu tamamlayabilirsiniz.*

#### 4. Frontend Kurulumu
```bash
cd frontend
npm install
npm run dev
```

#### 5. Electron (Masaüstü Uygulaması) Kurulumu
```bash
cd electron
npm install
npm start
```

### Lisans
[MIT Lisansı](LICENSE) altında dağıtılmaktadır.

---

<a name="-english"></a>

## 🇬🇧 English

SQLGen is a Text-to-SQL platform — built on NVIDIA NIM and a multi-agent workflow — that produces fully validated, optimized SQL queries against large and complex enterprise databases, driven by natural-language questions and Excel-based data request forms.

It manages local and cloud resources asynchronously through an Electron-based desktop shell, a Vue 3 frontend, and a FastAPI backend.

### System Architecture

```
[ Electron Desktop Shell ]              [ Claude Desktop / Cursor / Copilot ]
         │                                                 │
         ▼                                                 ▼ (Model Context Protocol)
[ Vue 3 Frontend (TS / Vanilla CSS) ]   ┌──────────────────────────────────────────────┐
         │ (REST API & SSE Stream)      │         SQLGen-MCP Server (FastMCP)          │
         ▼                              └──────────────────┬───────────────────────────┘
[ FastAPI Application Server ]◄─────────────────────────────┘
         │ (Asynchronous Background Tasks)
         ├──────────────► [ Multi-Layer Schema Relation Engine ] (Manual + Implicit + Physical merge)
         ├──────────────► [ Graph-Based Schema Pruning ] (Local BFS pruning - 93% context saving)
         ├──────────────► [ Qdrant Vector Store ] (Business Rules & Historical SQL RAG catalog)
         └──────────────► [ Multi-Agent Workflow ]
                                 │
                                 ├──► [ Writer Agent ] (NVIDIA NIM Llama-3.3 API)
                                 ├──► [ Validator Agent ] (SQLGlot AST syntax validator)
                                 └──► [ Critic Agent ] (Autonomous error correction / Self-Correction)
```

### Key Features

#### 1. Multi-Layer Intelligent Schema Relation Engine
SQLGen works even when your database has incomplete physical Foreign Key definitions, or none at all. It dynamically merges relations from four distinct layers into a single relational network:
- **Physical relations (Explicit):** Foreign keys scanned automatically from PostgreSQL, Oracle, and SQLite systems.
- **Virtual relations (Custom/Virtual):** Custom manual relations the user adds easily from the UI, stored in the local SQLite (sqlgen.db) settings.
- **Implicit relations:** Relations the system discovers automatically from column-name patterns (e.g. matching `order_id` to `orders.id`).
- **Restrictive filters (Disabled):** Join paths the user can disable to keep the pruner from taking wrong join routes.

#### 2. Graph-Based Deterministic Schema Pruning
Sending schemas with hundreds of tables directly to the model causes high cost and model confusion (hallucination).
- **Seed table detection:** Detects the starting (seed) tables by analyzing the user query and the Excel request with Jaccard similarity and smart column clusters.
- **Breadth-First Search (BFS):** Finds the bridge tables needed to join the seed tables deterministically over the unified relation graph, computing the shortest join paths.
- **High context saving:** Presents the model only the minimal sub-schema the query needs, shrinking schema size by ~93% and driving the error rate toward zero.

#### 3. Multi-Agent & Autonomous Self-Correction Loop
Instead of generating SQL with a single prompt and hoping it compiles, SQLGen runs collaborating agents:
- **Writer Agent:** Uses the NVIDIA NIM API (Llama-3.3-Nemotron-70B) to write an optimized first-draft SQL from the pruned sub-schema, AQR constraints, and few-shot examples from the RAG catalog.
- **Validator Agent:** Parses the generated SQL via SQLGlot AST (Abstract Syntax Tree) analysis and tests syntax compatibility with the selected dialect (Oracle, PostgreSQL, SQLite, Snowflake, etc.).
- **Critic Agent:** When a compile error occurs, it analyzes the Validator's AST error log and the target schema and gives the Writer Agent a precise correction instruction. The system self-corrects autonomously for up to 3 attempts to produce error-free SQL.

#### 4. Hybrid RAG (Retrieval-Augmented Generation)
SQLGen uses a local Qdrant vector database to keep your company's business rules and past approved SQL queries in memory:
- **Schema Embedding Index (Cross-lingual):** Extracts a semantic fingerprint of the database schema using NVIDIA's multilingual model (`nvidia/llama-nemotron-embed-1b-v2`, 2048 dims). It matches concepts in a Turkish query ("ülke", "müşteri") directly to English schema tables via semantic proximity (Cosine Similarity), with no translation or static dictionary needed.
- **Business rules catalog:** Semantically searches internal KPI definitions and coding standards (e.g. knows the `active = 1` filter means "active members").
- **SQL history (Few-Shot):** Finds past successful queries similar to the natural-language query to provide in-context examples to the LLM and raise the success rate.

#### 5. FastMCP Server Integration
SQLGen hosts an advanced MCP Server so external AI development tools (Claude Desktop, Cursor, Copilot) can use SQLGen directly as a database expert:
- **FastMCP standard:** Runs over the stdio protocol via mcp_server.py.
- **Ultra-Compact Pseudo-DDL:** Offers an ultra-compact pseudo-DDL format that cuts the token cost of conveying schema structure to external LLMs by 85–90%.
- **Sharing agent capabilities:** While developing in Cursor or Claude Desktop, you can call SQLGen's `generate_validated_sql` tool to produce error-free, AST-validated SQL directly inside the editor.

#### 6. Interactive Network Graph & SSE Log Stream
- **D3.js network graph:** Visualizes which tables the generated SQL traverses in the database schema, and the foreign-key (FK) relations between tables, with an interactive 3D-style network graph.
- **SSE (Server-Sent Events) live logs:** Streams the status of asynchronous background workers, pruning decisions, RAG results, and error-correction steps to the UI in real time.

### Setup & Run

#### 1. Prerequisites
- Node.js (v18+)
- Python (v3.10+)
- NVIDIA NIM API Key (available at build.nvidia.com)

#### 2. Backend Setup
```bash
cd backend
python -m venv venv
venv\Scripts\activate      # on Windows
source venv/bin/activate  # on macOS/Linux

pip install -r requirements.txt

# Enter your API key from the Settings panel in the UI, or as an environment variable:
set NVIDIA_API_KEY=your_nvidia_nim_key

# Start the server
uvicorn app.main:app --reload --port 8000
```

#### 3. Starting the MCP Server (for developer tools)
To run SQLGen as an MCP server and connect it to Cursor or Claude Desktop:
```bash
cd backend
python mcp_server.py
```
*In Cursor settings (Settings > Models > MCP), add a new command server and set the command to `python <repo>/backend/mcp_server.py` using your repository root path.*

#### 4. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

#### 5. Electron (Desktop App) Setup
```bash
cd electron
npm install
npm start
```

### License
Distributed under the [MIT License](LICENSE).
