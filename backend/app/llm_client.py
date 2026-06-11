import os
import time
import json
import random
import threading
from typing import Dict, Any, List, Set, Tuple, Optional
import requests

class TokenBucket:
    def __init__(self, capacity: float, fill_rate: float):
        """
        Token Bucket hız sınırlayıcı.
        capacity: Maksimum birikebilecek token/istek sayısı (burst limiti).
        fill_rate: Saniyede yenilenen token miktarı.
        """
        self.capacity = capacity
        self.fill_rate = fill_rate
        self.tokens = capacity
        self.last_update = time.time()
        self.lock = threading.Lock()

    def consume(self, amount: float = 1.0) -> float:
        """
        Belirtilen miktarda token tüketir.
        Kullanıcının beklemesi gereken süreyi saniye cinsinden döner.
        Süre 0.0 ise hemen devam edilebilir.
        """
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            self.last_update = now
            
            # Bucket doldurma
            self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
            
            if self.tokens >= amount:
                self.tokens -= amount
                return 0.0
            
            # Yetersiz token, bekleme süresini hesapla
            needed = amount - self.tokens
            wait_time = needed / self.fill_rate
            return wait_time

def get_nvidia_api_key() -> str:
    """
    Öncelikli olarak Çevre değişkenlerinden (Environment Variables) NVIDIA_API_KEY okur.
    Bulamazsa local veritabanı configs tablosundan çeker.
    """
    # 1. Environment Variable
    api_key = os.environ.get("NVIDIA_API_KEY")
    if api_key:
        return api_key
        
    # 2. SQLite local configs
    try:
        from app.database import get_config
        api_key = get_config("nvidia_api_key")
        if api_key:
            return api_key
    except Exception:
        pass
        
    return ""

class PromptTemplateManager:
    @staticmethod
    def get_writer_prompt(natural_query: str, aqr: Dict[str, Any], prompt_schema_context: str, previous_sql: Optional[str] = None, dialect: str = "postgres") -> str:
        """
        SQL Yazar Ajanı (SQL Generator) için kapsamlı sistem ve yönlendirme promptunu oluşturur.
        """
        business_rules_text = "\n".join([f"- {rule}" for rule in aqr.get("business_rules", [])]) if aqr.get("business_rules") else "None"
        
        revision_context = ""
        if previous_sql:
            revision_context = f"""
PREVIOUS SQL QUERY TO REVISE:
```sql
{previous_sql}
```
NOTE: The user is asking to REVISE or UPDATE the previous query above based on their new instructions.
"""
        
        prompt = f"""You are an expert SQL Generator. Your task is to generate a syntactically correct {dialect} SQL query to answer the user's question based on the provided schema, AQR structure, and business rules.

DATABASE SCHEMA:
{prompt_schema_context}

STRUCTURED TARGET REPRESENTATION (AQR):
- Target Entities: {", ".join(aqr.get("entities", []))}
- Requested Fields: {", ".join(aqr.get("fields", []))}
- Requested Filters: {json.dumps(aqr.get("filters", []))}
- Requested Aggregations: {json.dumps(aqr.get("aggregations", []))}
- Requested Sorting: {json.dumps(aqr.get("sorts", []))}

BUSINESS RULES & CONSTRAINTS:
{business_rules_text}
{revision_context}
USER NATURAL LANGUAGE QUERY:
"{natural_query}"

INSTRUCTIONS:
1. Write a high-performance, valid {dialect} query.
2. Use proper JOIN conditions based on the database schema.
3. Apply all business rules and filters.
4. Output ONLY the raw SQL query. Do not wrap it in explanation, introduction, or other conversational filler. Just the SQL code.
5. CRITICAL SCHEMA RULE: You must ONLY use table names and column names that exist in the DATABASE SCHEMA provided above. Do NOT invent, assume, or hallucinate any table or column that is not explicitly listed. If a column you need is not in a given table, you MUST JOIN with the table that actually contains that column.
6. For Oracle dialect: ALL table names, column names, and aliases MUST be written in UPPERCASE exactly as shown in the schema above. Never use lowercase identifiers for Oracle.
7. When the user mentions a concept (e.g., "country", "ülke", "region", "bölge"), carefully examine ALL tables in the schema to find which table actually has that column, then JOIN to that table. Do NOT assume all attributes exist on the main entity table.
8. Always prefer using explicit table aliases and qualify every column reference with its table alias (e.g., C.COUNTRY, O.ORDER_ID) to eliminate ambiguity.
"""
        return prompt

    @staticmethod
    def get_corrector_prompt(natural_query: str, original_sql: str, error_message: str, prompt_schema_context: str, dialect: str = "postgres") -> str:
        """
        SQL Eleştirmen/Düzeltici Ajanı (Corrector) için prompt hazırlar.
        """
        prompt = f"""You are an expert SQL Debugger and Analyst. A previously generated {dialect} SQL query failed with an execution or validation error.
Your task is to fix the query and output a fully correct, working version.

DATABASE SCHEMA:
{prompt_schema_context}

USER QUESTION:
"{natural_query}"

FAILED SQL QUERY:
```sql
{original_sql}
```

ERROR ENCOUNTERED:
{error_message}

INSTRUCTIONS:
1. Carefully analyze the database schema and the error message.
2. Fix the join paths, table/column names, or syntactic errors.
3. Output ONLY the corrected, raw SQL query. Do not include any explanations.
"""
        return prompt

class NVIDIAClient:
    def __init__(self):
        self.base_url = "https://integrate.api.nvidia.com/v1/chat/completions"
        # Configs tablosundan model adını oku, yoksa doğru default modeli kullan
        from app.database import get_config
        cfg_model = get_config("llm_model")
        if cfg_model:
            if "/" in cfg_model:
                self.model = cfg_model
            elif "llama-3.3-70b" in cfg_model:
                self.model = f"meta/{cfg_model}"
            else:
                self.model = f"nvidia/{cfg_model}"
        else:
            self.model = "meta/llama-3.3-70b-instruct"
        # Varsayılan hız sınırı: dakikada en fazla 15 istek (0.25 fill_rate/saniye), maksimum burst 3.
        self.limiter = TokenBucket(capacity=3.0, fill_rate=15.0/60.0)

    def generate_sql(self, prompt: str, api_key: str = None) -> str:
        """
        NVIDIA NIM API kullanarak SQL üretir.
        """
        key = api_key or get_nvidia_api_key()
        if not key:
            raise ValueError(
                "NVIDIA API Key bulunamadı! Lütfen NVIDIA_API_KEY ortam değişkenini "
                "tanımlayın veya yerel ayarlardan veritabanına kaydedin."
            )
            
        # Hız sınırını kontrol et (Token Bucket)
        wait_time = self.limiter.consume(1.0)
        if wait_time > 0.0:
            time.sleep(wait_time)
            
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 4096
        }
        
        max_retries = 4
        base_delay = 2.0
        
        for attempt in range(max_retries):
            try:
                response = requests.post(self.base_url, headers=headers, json=payload, timeout=120)
                
                # Başarılı istek
                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    
                    # Markdown kod bloklarını temizleme (```sql ... ```)
                    sql_clean = content.strip()
                    if sql_clean.startswith("```"):
                        # Satır satır oku, ilk satırdaki ```sql veya ``` ifadesini at, son satırı at
                        lines = sql_clean.split("\n")
                        if len(lines) >= 2:
                            if lines[0].strip().startswith("```"):
                                lines = lines[1:]
                            if lines[-1].strip().startswith("```"):
                                lines = lines[:-1]
                            sql_clean = "\n".join(lines).strip()
                            
                    return sql_clean
                    
                # Retry edilebilir hatalar (429 Too Many Requests veya 5xx Server Error)
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    if attempt == max_retries - 1:
                        raise Exception(f"NVIDIA API Hatası {response.status_code}: {response.text}")
                        
                    # Üstel geri çekilme (Exponential Backoff) + Jitter
                    delay = base_delay * (2 ** attempt) + random.uniform(0.1, 0.5)
                    time.sleep(delay)
                    continue
                else:
                    # Retry edilmeyecek hatalar (400, 401, 403 vb.)
                    raise Exception(f"NVIDIA API İstemci Hatası {response.status_code}: {response.text}")
                    
            except requests.RequestException as e:
                if attempt == max_retries - 1:
                    raise e
                delay = base_delay * (2 ** attempt) + random.uniform(0.1, 0.5)
                time.sleep(delay)
                
        raise Exception("NVIDIA NIM API bağlantısı gerçekleştirilemedi.")
