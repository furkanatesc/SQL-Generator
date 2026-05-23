import os
import re
import json
import logging
from typing import Dict, Any, List, Optional, Set, Tuple
import sqlglot
from sqlglot import exp as sqlglot_exp
from app.excel_parser import parse_excel_request
from app.schema_manager import SchemaManager
from app.schema_pruner import SchemaPruner
from app.llm_client import NVIDIAClient, PromptTemplateManager

logger = logging.getLogger("sql_pipeline")

from app.sql_validator import SQLValidator
from app.trace_store import TraceStore


def enforce_oracle_case(sql: str, dialect: str = "oracle") -> str:
    """
    Katman 4: Oracle dialect'inde tüm identifier'ları (tablo ve kolon isimleri)
    UPPERCASE'e çevirerek ORA-00904 hatalarını önler.
    sqlglot AST üzerinden güvenli dönüşüm yapar.
    """
    if dialect.lower() != "oracle":
        return sql

    try:
        tree = sqlglot.parse_one(sql, read=dialect)

        # Tüm identifier'ları (tablo, kolon, alias) uppercase yap
        for node in tree.walk():
            if isinstance(node, sqlglot_exp.Column):
                if node.name:
                    node.set("this", sqlglot_exp.to_identifier(node.name.upper(), quoted=False))
                if node.table:
                    node.set("table", sqlglot_exp.to_identifier(node.table.upper(), quoted=False))
            elif isinstance(node, sqlglot_exp.Table):
                if node.name:
                    node.set("this", sqlglot_exp.to_identifier(node.name.upper(), quoted=False))
                if node.alias:
                    node.set("alias", sqlglot_exp.TableAlias(this=sqlglot_exp.to_identifier(node.alias.upper(), quoted=False)))
            elif isinstance(node, sqlglot_exp.Alias):
                if node.alias:
                    node.set("alias", sqlglot_exp.to_identifier(node.alias.upper(), quoted=False))

        return tree.sql(dialect=dialect, pretty=True)
    except Exception as e:
        logger.warning(f"[Oracle Case Enforcement] AST dönüşümü başarısız, fallback: {e}")
        # Fallback: Basit regex ile keyword'ler dışındakileri uppercase yap
        return sql.upper()

class SQLGenerationPipeline:
    def __init__(self, schema_manager: SchemaManager = None, nvidia_client: NVIDIAClient = None):
        self.schema_manager = schema_manager or SchemaManager()
        self.schema_pruner = SchemaPruner(schema_manager=self.schema_manager)
        self.nvidia_client = nvidia_client or NVIDIAClient()
        self.trace_store = TraceStore()
        # Şema bilgisini AQR zenginleştirme için yükle
        self._full_schema = None

    def run_pipeline(
        self, 
        job_id: str = "local_test",
        excel_file_path: Optional[str] = None, 
        natural_query: Optional[str] = None,
        previous_sql: Optional[str] = None,
        dialect: str = "postgres", 
        api_key: str = None, 
        max_attempts: int = 3,
        log_callback: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Doğal dilden SQL'e tüm üretim pipeline'ını çalıştırır:
        1. Excel Ayrıştırma (AQR) veya Doğal Dil Sorgusu
        2. Veritabanı Şeması Çekimi ve Akıllı Budama
        3. LLM (NVIDIA NIM) ile ilk SQL üretimi (Writer Agent)
        4. sqlglot ile AST doğrulaması
        5. Sözdizimi hatası durumunda Eleştirmen Ajan (Critic/Corrector Agent) döngüsü
        """
        result = {
            "success": False,
            "aqr": None,
            "pruned_schema_tables": [],
            "generated_sql": "",
            "attempts": [],
            "error": None
        }

        if log_callback:
            log_callback("SQL üretim süreci başlatıldı...", 1)

        # 1. Excel Ayrıştırma (AQR) veya Doğal Dil Sorgusu
        if excel_file_path:
            try:
                if log_callback:
                    log_callback("Excel dosyası inceleniyor ve AQR formatına dönüştürülüyor...", 1)
                aqr = parse_excel_request(excel_file_path)
                result["aqr"] = aqr
                if log_callback:
                    log_callback(f"Excel başarıyla ayrıştırıldı. Sorgu: '{aqr.get('natural_query')}'", 1)
            except Exception as e:
                result["error"] = f"Excel Ayrıştırma Hatası: {str(e)}"
                if log_callback:
                    log_callback(f"Excel Ayrıştırma BAŞARISIZ: {str(e)}", 1)
                return result
        elif natural_query:
            if log_callback:
                log_callback("Doğal dil sorgusu alındı (Excel şablonu pas geçildi).", 1)
            aqr = {
                "natural_query": natural_query,
                "entities": [],
                "fields": [],
                "filters": [],
                "aggregations": [],
                "sorts": [],
                "business_rules": []
            }
            result["aqr"] = aqr


        else:
            result["error"] = "Girdi hatası: Hem Excel dosyası hem de Doğal Dil Sorgusu boş olamaz."
            if log_callback:
                log_callback("Girdi hatası: Girdi parametreleri eksik.", 1)
            return result

        # 2. Şema Yükleme ve Budama
        try:
            if log_callback:
                log_callback("Veritabanı şeması analiz ediliyor ve akıllı budama (Schema Pruning) tetikleniyor...", 2)
            pruned_schema = self.schema_pruner.prune_schema(aqr, token_budget=8000)
            if pruned_schema.get("error"):
                result["error"] = pruned_schema["error"]
                if log_callback:
                    log_callback(f"Şema Budama Başarısız: {result['error']}", 2)
                return result

            result["pruned_schema_tables"] = list(pruned_schema.get("tables", {}).keys())
            if log_callback:
                log_callback(f"Şema budama tamamlandı. Bütçelenen token: {pruned_schema.get('estimated_tokens', 0)}. Seçilen tablolar: {', '.join(result['pruned_schema_tables'])}", 2)
        except Exception as e:
            result["error"] = f"Şema Budama Hatası: {str(e)}"
            if log_callback:
                log_callback(f"Şema Budama BAŞARISIZ: {str(e)}", 2)
            return result

        # 3. İteratif Üretim Döngüsü (Writer-Critic)
        natural_query = aqr.get("natural_query", "")
        current_sql = ""
        last_error = "Syntax error in SQL query"
        
        for attempt in range(1, max_attempts + 1):
            attempt_info = {
                "attempt": attempt,
                "action": "generate" if attempt == 1 else "correct",
                "sql": "",
                "valid": False,
                "error": None
            }
            
            try:
                if attempt == 1:
                    if log_callback:
                        log_callback("NVIDIA NIM (Llama-3.3-Nemotron) ile taslak SQL sorgusu üretiliyor...", 3)
                    prompt = PromptTemplateManager.get_writer_prompt(
                        natural_query=natural_query,
                        aqr=aqr,
                        schema=pruned_schema,
                        previous_sql=previous_sql,
                        dialect=dialect
                    )
                else:
                    if log_callback:
                        log_callback(f"Critic döngüsü devrede. AST hataları düzeltiliyor (Deneme {attempt}/{max_attempts})...", 5)
                    prompt = PromptTemplateManager.get_corrector_prompt(
                        natural_query=natural_query,
                        original_sql=current_sql,
                        error_message=last_error,
                        schema=pruned_schema,
                        dialect=dialect
                    )
                
                # API Çağrısı ile SQL üret
                generated_sql = self.nvidia_client.generate_sql(prompt, api_key=api_key)
                current_sql = generated_sql
                attempt_info["sql"] = current_sql
                
                if log_callback:
                    log_callback(f"Taslak SQL üretildi. sqlglot ile diyalekt ({dialect}) sözdizimi doğrulaması yapılıyor...", 4)
                
                # ── Katman 4: Oracle Büyük Harf Zorlama (Pre-Validation) ──
                if dialect.lower() == "oracle":
                    current_sql = enforce_oracle_case(current_sql, dialect=dialect)
                    attempt_info["sql"] = current_sql

                # AST Doğrulama (sqlglot)
                try:
                    sqlglot.parse_one(current_sql, read=dialect)
                except sqlglot.errors.ParseError as parse_err:
                    last_error = f"SQLGLOT AST Parse Error: {str(parse_err)}"
                    attempt_info["valid"] = False
                    attempt_info["error"] = last_error
                    result["attempts"].append(attempt_info)
                    if log_callback:
                        log_callback(f"AST doğrulaması BAŞARISIZ: {last_error}", 4)
                    continue

                if log_callback:
                    log_callback("AST sözdizimi doğrulaması geçti. Şema-bazlı semantik doğrulama başlatılıyor...", 4)

                # ── Katman 1 + 5: Schema-Aware Semantik Doğrulama ──
                sem_valid, sem_error = SQLValidator.validate(
                    current_sql, pruned_schema, dialect=dialect
                )
                if not sem_valid:
                    last_error = sem_error
                    attempt_info["valid"] = False
                    attempt_info["error"] = last_error
                    result["attempts"].append(attempt_info)
                    if log_callback:
                        log_callback(f"Semantik doğrulama BAŞARISIZ (Critic döngüsüne yönlendiriliyor): {last_error}", 4)
                    continue

                # Tüm doğrulamalar geçti
                try:
                    # SQL'i formatla (Pretty Print)
                    parsed_tree = sqlglot.parse_one(current_sql, read=dialect)
                    current_sql = parsed_tree.sql(dialect=dialect, pretty=True)
                except Exception:
                    pass  # Formatlama başarısız olursa orijinal haliyle bırak
                
                attempt_info["valid"] = True
                attempt_info["sql"] = current_sql
                result["attempts"].append(attempt_info)
                result["success"] = True
                result["generated_sql"] = current_sql
                if log_callback:
                    log_callback("AST + Semantik doğrulama başarılı! SQL sorgusu üretildi, şema uyumlu ve diyalekt standartlarıyla tam uyumlu.", 4)
                break
                    
            except Exception as e:
                last_error = f"LLM API Çağrı Hatası: {str(e)}"
                attempt_info["valid"] = False
                attempt_info["error"] = last_error
                result["attempts"].append(attempt_info)
                if log_callback:
                    log_callback(f"LLM API Çağrı Hatası: {str(e)}", 3)
                continue

        if not result["success"]:
            result["error"] = f"SQL üretimi başarısız oldu. {max_attempts} deneme yapıldı."
            if log_callback:
                log_callback(f"Maksimum deneme limitine ({max_attempts}) ulaşıldı. Süreç başarısız.", 5)
            if result["attempts"]:
                result["generated_sql"] = result["attempts"][-1]["sql"]
        else:
            if log_callback:
                log_callback("Tebrikler! SQL üretim aşaması başarıyla sonuçlandırıldı.", 5)
                
        # --- İzlenebilirlik (Traceability) Kaydı ---
        candidate_tables = []
        selected_tables = []
        estimated_tokens = 0
        if "pruned_schema" in locals() and pruned_schema:
            candidate_tables = pruned_schema.get("debug_trace", {}).get("seed_candidates", [])
            selected_tables = pruned_schema.get("debug_trace", {}).get("selected_tables", [])
            estimated_tokens = pruned_schema.get("estimated_tokens", 0)
            
        self.trace_store.save_trace(
            job_id=job_id,
            natural_query=natural_query or aqr.get("natural_query", ""),
            candidate_tables=candidate_tables,
            selected_tables=selected_tables,
            estimated_tokens=estimated_tokens,
            generated_sql=result["generated_sql"],
            sql_valid=result["success"],
            error_message=result.get("error") if not result["success"] else None
        )
                
        return result
