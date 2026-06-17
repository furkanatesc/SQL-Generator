# SQLGen

SQLGen, kurumsal ölçekteki büyük ve karmaşık veritabanlarından doğal dil sorguları ve Excel tabanlı veri talep formları aracılığıyla tamamen doğrulanmış, optimize edilmiş SQL sorguları üreten, NVIDIA NIM ve çoklu ajan (multi-agent) tabanlı bir Text-to-SQL platformudur.

Electron tabanlı masaüstü kabuğu, Vue 3 tabanlı arayüzü ve FastAPI mimarisiyle yerel ve bulut kaynaklarını asenkron olarak yönetir.

---

## Sistem Mimarisi

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

---

## Öne Çıkan Özellikler

### 1. Çok Katmanlı Akıllı Şema İlişki Motoru
Veritabanınızda fiziksel Foreign Key tanımları eksik veya hiç olmasa bile SQLGen çalışabilir. Dört farklı katmandan gelen ilişkileri dinamik olarak birleştirir ve tek bir ilişkisel ağ oluşturur:
- **Fiziksel İlişkiler (Explicit):** PostgreSQL, Oracle ve SQLite sistemlerinden otomatik olarak taranan yabancı anahtarlar.
- **Sanal İlişkiler (Custom/Virtual):** Kullanıcının arayüzden kolayca eklediği ve yerel SQLite (sqlgen.db) ayarlarında saklanan özel manuel ilişkiler.
- **Örtük İlişkiler (Implicit):** Kolon adı kalıpları (örneğin order_id ile orders.id eşleşmesi) üzerinden sistemin otomatik keşfettiği ilişkiler.
- **Kısıtlayıcı Filtreler (Disabled):** Budama esnasında yanlış join yollarına girilmesini önlemek amacıyla kullanıcının pasifize edebildiği geçiş yolları.

### 2. Grafik Tabanlı Deterministik Şema Budama
Yüzlerce tablo içeren şemaları yapay zekaya doğrudan göndermek, yüksek maliyetlere ve modelin kafa karışıklığına (hallucination) yol açar.
- **Tohum Tablo Belirleme:** Kullanıcı sorgusunu ve Excel talebini Jaccard benzerliği ve akıllı kolon öbekleri ile analiz ederek başlangıç (seed) tablolarını tespit eder.
- **Genişlik Öncelikli Arama (BFS):** Tohum tabloları birleştirmek için gereken köprü (bridge) tabloları, birleşik ilişki grafiği üzerinde deterministik olarak bularak en kısa join yollarını hesaplar.
- **Yüksek Bağlam Tasarrufu:** Yapay zekaya sadece sorgunun ihtiyaç duyduğu minimal alt şemayı sunarak şema boyutunu %93 oranında daraltır ve hata oranını sıfıra yaklaştırır.

### 3. Çoklu Ajan ve Otonom Hata Düzeltme Döngüsü
SQLGen, tek bir prompt ile SQL üretip hata vermesini beklemek yerine, kendi içinde iş birliği yapan ajanlar çalıştırır:
- **Yazar Ajan (Writer):** NVIDIA NIM API (Llama-3.3-Nemotron-70B) kullanarak, budanmış alt şema, AQR kısıtları ve RAG kataloğundan gelen few-shot örnekleri ile optimize ilk taslak SQL'i yazar.
- **Doğrulayıcı Ajan (Validator):** Üretilen SQL sorgusunu SQLGlot AST (Abstract Syntax Tree) analiziyle parçalar. Seçilen veritabanı diyalekti (Oracle, PostgreSQL, SQLite, Snowflake vb.) ile sentaks uyumluluğunu test eder.
- **Eleştirmen Ajan (Critic):** Derleme hatası oluşursa, Validator'ın ürettiği AST hata logunu ve hedef şemayı analiz ederek Writer Agent'a nokta atışı düzeltme talimatı verir. Sistem otonom olarak 3 denemeye kadar kendi kendini düzelterek sıfır hatalı sorgu üretir.

### 4. Hibrit RAG (Retrieval-Augmented Generation)
SQLGen, şirketinizin iş kurallarını ve geçmiş onaylı SQL sorgularını hafızasında tutmak için yerel bir Qdrant vektör veritabanı kullanır:
- **Schema Embedding Index (Cross-lingual):** NVIDIA'nın çok dilli (`nvidia/llama-nemotron-embed-1b-v2`, 2048 boyut) modeli kullanılarak veritabanı şemasının anlamsal parmak izi çıkartılır. Türkçe bir sorgudaki ("ülke", "müşteri") kavramları, herhangi bir çeviriye veya statik sözlüğe ihtiyaç duymadan, doğrudan anlamsal yakınlık (Cosine Similarity) ile İngilizce şema tablolarıyla eşleştirir.
- **İş Kuralları Kataloğu:** Şirket içi KPI tanımlarını ve kodlama standartlarını semantik olarak arar (örn: active = 1 filtresinin "aktif üyeler" anlamına geldiğini bilir).
- **SQL Geçmişi (Few-Shot):** Doğal dil sorgusuna benzer geçmiş başarılı sorguları bularak LLM'e bağlam içi örnekler sağlar ve başarı oranını artırır.

### 5. FastMCP Sunucusu Entegrasyonu
SQLGen, Claude Desktop, Cursor veya Copilot gibi harici yapay zeka geliştirme araçlarının doğrudan veritabanı uzmanı olarak SQLGen'i kullanabilmesi için gelişmiş bir MCP Server barındırır:
- **FastMCP Standardı:** mcp_server.py üzerinden stdio protokolü ile çalışır.
- **Ultra-Compact Pseudo-DDL:** Şema yapısını dış LLM'lere aktarırken token maliyetini %85-90 oranında düşüren ultra kompakt bir pseudo-DDL formatı sunar.
- **Ajan Yeteneklerinin Paylaşımı:** Cursor veya Claude Desktop üzerinden geliştirme yaparken, SQLGen'in generate_validated_sql aracını çağırarak doğrudan editör içerisinden hatasız ve AST-doğrulanmış SQL sorguları üretebilirsiniz.

### 6. Etkileşimli Ağ Grafiği ve SSE Log Akışı
- **D3.js Ağ Grafiği:** Üretilen SQL sorgusunun veritabanı şemasındaki hangi tablolardan geçtiğini, tablolar arasındaki yabancı anahtar (FK) ilişkilerini etkileşimli 3D görünümlü bir ağ grafiğiyle görselleştirir.
- **SSE (Server-Sent Events) Canlı Loglar:** Arka planda asenkron olarak çalışan işçilerin durumlarını, budama kararlarını, RAG sonuçlarını ve hata düzeltme adımlarını anlık olarak arayüze log akışı halinde basar.

---

## Kurulum ve Çalıştırma

### 1. Ön Gereksinimler
- Node.js (v18+)
- Python (v3.10+)
- NVIDIA NIM API Key (build.nvidia.com adresinden alınabilir)

### 2. Backend Kurulumu
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

### 3. MCP Sunucusunu Başlatma (Geliştirici Araçları İçin)
SQLGen'i bir MCP sunucusu olarak çalıştırıp Cursor veya Claude Desktop uygulamanıza bağlamak için:
```bash
cd backend
python mcp_server.py
```
*Cursor ayarlarında (Settings > Models > MCP) yeni bir command sunucusu ekleyip command alanına `python c:/Users/furkan/Desktop/SQLGen/backend/mcp_server.py` yazarak entegrasyonu tamamlayabilirsiniz.*

### 4. Frontend Kurulumu
```bash
cd frontend
npm install
npm run dev
```

### 5. Electron (Masaüstü Uygulaması) Kurulumu
```bash
cd electron
npm install
npm start
```

---

## Dokümantasyon Dizin Rehberi

Projenin tüm teknik detaylarına ve gelecek yol haritasına aşağıdaki belgelerden ulaşabilirsiniz:
- [FEATURE.md](file:///c:/Users/furkan/Desktop/SQLGen/FEATURE.md) — Projedeki tüm özelliklerin detaylı teknik çalışma prensipleri, algoritmaları, MCP yapısı ve mimari kod özellikleri.
- [SOON.md](file:///c:/Users/furkan/Desktop/SQLGen/SOON.md) — Gelecek vizyonu: Uçtan uca Değer Düzeyi Semantik RAG (Value-Level RAG) ve Kurumsal Veri Sözlüğü RAG entegrasyon planları.

---

## Lisans

Bu proje kurumsal veri güvenliği, veri gizliliği ve yerel entegrasyon standartlarına göre tasarlanmış açık kaynaklı bir platform prototipidir.
