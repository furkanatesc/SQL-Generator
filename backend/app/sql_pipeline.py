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
from app.llm.provider import LLMProvider, SQLGenerationRequest

logger = logging.getLogger("sql_pipeline")

from app.sql_validator import SQLValidator
from app.sql_guardrail import SQLGuardrailValidator
from app.trace.builders import build_trace_from_pruned_schema
from app.trace.store import TraceStore
from app.schema_graph import TraversalPolicy

import time

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

def classify_sql_error(error_message: str, stage: str) -> Dict[str, Any]:
    error_lower = (error_message or "").lower()

    if "missing column" in error_lower or "column" in error_lower:
        error_type = "missing_column"
    elif "missing table" in error_lower or "table" in error_lower:
        error_type = "missing_table"
    elif "parse" in error_lower or "syntax" in error_lower:
        error_type = "syntax_error"
    else:
        error_type = "validation_error"

    return {
        "type": error_type,
        "stage": stage,
        "message": error_message,
    }

class SQLGenerationPipeline:
    def __init__(self, schema_manager: SchemaManager = None, nvidia_client: NVIDIAClient = None, trace_store: TraceStore | None = None, llm_provider: LLMProvider | None = None):
        self.schema_manager = schema_manager or SchemaManager()
        self.schema_pruner = SchemaPruner(schema_manager=self.schema_manager)
        self.nvidia_client = nvidia_client
        self.trace_store = trace_store
        self.llm_provider = llm_provider
        # Şema bilgisini AQR zenginleştirme için yükle
        self._full_schema = None

    def _get_nvidia_client(self) -> NVIDIAClient:
        if self.nvidia_client is None:
            self.nvidia_client = NVIDIAClient()
        return self.nvidia_client

    def _generate_sql(
        self,
        *,
        prompt: str,
        dialect: str,
        purpose: str,
        api_key: str | None = None,
    ) -> str:
        if self.llm_provider is not None:
            response = self.llm_provider.generate_sql(
                SQLGenerationRequest(
                    prompt=prompt,
                    dialect=dialect,
                    purpose=purpose,
                )
            )
            return response.sql

        return self._get_nvidia_client().generate_sql(prompt, api_key=api_key)

    def _save_trace_safely(self, trace):
        if not self.trace_store:
            return
        try:
            self.trace_store.save(trace)
        except Exception as e:
            logger.error(f"Failed to save NL2SQL trace: {e}")

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
            
        start_time = time.perf_counter()

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
                
                self._capture_trace_on_exit(
                    start_time=start_time,
                    job_id=job_id,
                    dialect=dialect,
                    natural_query=natural_query or "",
                    pruned_schema={"error": result["error"]},
                    generated_sql=None,
                    last_generated_sql=None,
                    sql_valid=None,
                    sql_validation_errors=[],
                    attempts=[],
                    error_message=result["error"],
                    error_type="excel_parse_error"
                )
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
            
            self._capture_trace_on_exit(
                start_time=start_time,
                job_id=job_id,
                dialect=dialect,
                natural_query=natural_query or "",
                pruned_schema={"error": result["error"]},
                generated_sql=None,
                last_generated_sql=None,
                sql_valid=None,
                sql_validation_errors=[],
                attempts=[],
                error_message=result["error"],
                error_type="input_error"
            )
            return result

        # 2. Şema Yükleme ve Budama
        try:
            if log_callback:
                log_callback("Veritabanı şeması analiz ediliyor ve akıllı budama (Schema Pruning) tetikleniyor...", 2)
            pruned_schema = self.schema_pruner.prune_schema(aqr, policy=TraversalPolicy(token_budget=8000))
            if pruned_schema.get("error"):
                result["error"] = pruned_schema["error"]
                if log_callback:
                    log_callback(f"Şema Budama Başarısız: {result['error']}", 2)
                
                self._capture_trace_on_exit(
                    start_time=start_time,
                    job_id=job_id,
                    dialect=dialect,
                    natural_query=natural_query or aqr.get("natural_query", ""),
                    pruned_schema=pruned_schema,
                    generated_sql=None,
                    last_generated_sql=None,
                    sql_valid=None,
                    sql_validation_errors=[],
                    attempts=[],
                    error_message=result["error"],
                    error_type="schema_pruning_error"
                )
                return result

            result["pruned_schema_tables"] = list(pruned_schema.get("tables", {}).keys())
            if log_callback:
                log_callback(f"Şema budama tamamlandı. Bütçelenen token: {pruned_schema.get('estimated_tokens', 0)}. Seçilen tablolar: {', '.join(result['pruned_schema_tables'])}", 2)
        except Exception as e:
            result["error"] = f"Şema Budama Hatası: {str(e)}"
            if log_callback:
                log_callback(f"Şema Budama BAŞARISIZ: {str(e)}", 2)
                
            self._capture_trace_on_exit(
                start_time=start_time,
                job_id=job_id,
                dialect=dialect,
                natural_query=natural_query or aqr.get("natural_query", ""),
                pruned_schema={"error": result["error"]},
                generated_sql=None,
                last_generated_sql=None,
                sql_valid=None,
                sql_validation_errors=[],
                attempts=[],
                error_message=result["error"],
                error_type="schema_pruning_exception"
            )
            return result

        # 3. İteratif Üretim Döngüsü (Writer-Critic)
        natural_query = aqr.get("natural_query", "")
        current_sql = ""
        last_error = "Syntax error in SQL query"
        validation_errors = []
        last_generated_sql = None
        
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
                    purpose = "writer"
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
                    purpose = "corrector"
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
                generated_sql = self._generate_sql(
                    prompt=prompt,
                    dialect=dialect,
                    purpose=purpose,
                    api_key=api_key
                )
                current_sql = generated_sql
                last_generated_sql = current_sql
                attempt_info["sql"] = current_sql
                
                if log_callback:
                    log_callback(f"Taslak SQL üretildi. sqlglot ile diyalekt ({dialect}) sözdizimi doğrulaması yapılıyor...", 4)
                
                # ── Katman 4: Oracle Büyük Harf Zorlama (Pre-Validation) ──
                if dialect.lower() == "oracle":
                    current_sql = enforce_oracle_case(current_sql, dialect=dialect)
                    attempt_info["sql"] = current_sql

                # --- Guardrail Validation ---
                guardrail_errors = SQLGuardrailValidator.validate(current_sql, dialect=dialect)
                if guardrail_errors:
                    last_error = guardrail_errors[0]["message"]
                    attempt_info["valid"] = False
                    attempt_info["error"] = last_error
                    attempt_info["validation_errors"] = guardrail_errors
                    result["attempts"].append(attempt_info)
                    for err in guardrail_errors:
                        validation_errors.append(err)
                    if log_callback:
                        log_callback(f"Güvenlik doğrulaması (Guardrail) BAŞARISIZ: {last_error}", 4)
                    continue

                # AST Doğrulama (sqlglot)
                try:
                    sqlglot.parse_one(current_sql, read=dialect)
                except sqlglot.errors.ParseError as parse_err:
                    last_error = f"SQLGLOT AST Parse Error: {str(parse_err)}"
                    attempt_info["valid"] = False
                    attempt_info["error"] = last_error
                    classified_error = classify_sql_error(last_error, stage="ast_parse")
                    attempt_info["validation_errors"] = [classified_error]
                    result["attempts"].append(attempt_info)
                    validation_errors.append(classified_error)
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
                    classified_error = classify_sql_error(last_error, stage="semantic_validation")
                    attempt_info["validation_errors"] = [classified_error]
                    result["attempts"].append(attempt_info)
                    validation_errors.append(classified_error)
                    if log_callback:
                        log_callback(f"Semantik doğrulama BAŞARISIZ (Critic döngüsüne yönlendiriliyor): {last_error}", 4)
                    continue

                # Tüm doğrulamalar geçti
                try:
                    # SQL'i formatla (Pretty Print)
                    parsed_tree = sqlglot.parse_one(current_sql, read=dialect)
                    current_sql = parsed_tree.sql(dialect=dialect, pretty=True)
                    last_generated_sql = current_sql
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
                classified_error = {
                    "type": "llm_api_error",
                    "stage": "llm_generation",
                    "message": last_error,
                }
                attempt_info["validation_errors"] = [classified_error]
                result["attempts"].append(attempt_info)
                validation_errors.append(classified_error)
                if log_callback:
                    log_callback(f"LLM API Çağrı Hatası: {str(e)}", 3)
                continue

        if not result["success"]:
            result["error"] = f"SQL üretimi başarısız oldu. {max_attempts} deneme yapıldı."
            if log_callback:
                log_callback(f"Maksimum deneme limitine ({max_attempts}) ulaşıldı. Süreç başarısız.", 5)
            if result["attempts"]:
                last_attempt = result["attempts"][-1]
                has_guardrail_error = any(
                    err.get("stage") == "sql_guardrail" 
                    for err in last_attempt.get("validation_errors", [])
                )
                if has_guardrail_error:
                    # Do not expose unsafe/rejected SQL in the public generated_sql field
                    result["generated_sql"] = ""
                else:
                    result["generated_sql"] = last_attempt["sql"]
        else:
            if log_callback:
                log_callback("Tebrikler! SQL üretim aşaması başarıyla sonuçlandırıldı.", 5)
                
        # --- İzlenebilirlik (Traceability) Kaydı ---
        pruned_schema_ref = locals().get("pruned_schema", {})
        
        final_sql_valid = result["success"] if result.get("attempts") else None
        final_attempt = result["attempts"][-1] if result.get("attempts") else None
        final_validation_errors = (
            []
            if result["success"]
            else (final_attempt.get("validation_errors", []) if final_attempt else validation_errors)
        )
        final_error_type = None if result["success"] else "sql_generation_failed"
        final_error_message = None if result["success"] else result.get("error")
        
        self._capture_trace_on_exit(
            start_time=start_time,
            job_id=job_id,
            dialect=dialect,
            natural_query=natural_query or aqr.get("natural_query", ""),
            pruned_schema=pruned_schema_ref,
            generated_sql=result["generated_sql"] if result["success"] else None,
            last_generated_sql=last_generated_sql,
            sql_valid=final_sql_valid,
            sql_validation_errors=final_validation_errors,
            attempts=result.get("attempts", []),
            error_message=final_error_message,
            error_type=final_error_type
        )
                
        return result

    def _capture_trace_on_exit(
        self,
        start_time: float,
        job_id: str,
        dialect: str,
        natural_query: str,
        pruned_schema: Dict[str, Any],
        generated_sql: Optional[str] = None,
        last_generated_sql: Optional[str] = None,
        sql_valid: Optional[bool] = None,
        sql_validation_errors: Optional[List[Dict[str, Any]]] = None,
        attempts: Optional[List[Dict[str, Any]]] = None,
        error_message: Optional[str] = None,
        error_type: Optional[str] = None
    ):
        if not self.trace_store:
            return
            
        total_ms = int((time.perf_counter() - start_time) * 1000)
        
        trace = build_trace_from_pruned_schema(
            raw_query=natural_query,
            pruned_schema=pruned_schema,
            generated_sql=generated_sql,
            last_generated_sql=last_generated_sql,
            sql_valid=sql_valid,
            sql_validation_errors=sql_validation_errors or [],
            attempts=attempts or [],
            error_message=error_message,
            error_type=error_type,
            latency_ms={"total": total_ms},
            metadata={
                "job_id": job_id,
                "dialect": dialect,
                "source": "job_pipeline"
            }
        )
        self._save_trace_safely(trace)
