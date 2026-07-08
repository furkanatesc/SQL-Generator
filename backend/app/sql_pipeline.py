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
from app.schema.schema_adapter import from_legacy_schema
from app.schema.schema_context_selector import select_schema_context
from app.schema.schema_prompt_serializer import serialize_selection_for_prompt

logger = logging.getLogger("sql_pipeline")

from app.sql_validator import SQLValidator
from app.sql_guardrail import SQLGuardrailValidator
from app.sql_safety import SqlSafetyValidator
from app.trace.builders import build_trace_from_pruned_schema
from app.trace.store import TraceStore
from app.trace.models import NL2SQLTrace
from app.schema_graph import TraversalPolicy

import time

from app.trace.redaction import redact_sensitive_text, redact_sensitive

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
            if isinstance(trace, NL2SQLTrace) and hasattr(self.trace_store, "save_legacy"):
                self.trace_store.save_legacy(trace)
            else:
                self.trace_store.save(trace)
        except Exception as e:
            logger.error(f"Failed to save NL2SQL trace: {e}")

    def _stage_intent(
        self,
        *,
        excel_file_path: Optional[str],
        natural_query: Optional[str],
        log_callback: Optional[Any],
    ) -> Tuple[Optional[dict], Optional[dict], int]:
        """1. Excel Ayrıştırma (AQR) veya Doğal Dil Sorgusu.

        Dönüş: (aqr, error, elapsed_ms); error = {"message": str, "error_type": str} | None
        """
        t0 = time.perf_counter()

        if excel_file_path:
            try:
                if log_callback:
                    log_callback("Excel dosyası inceleniyor ve AQR formatına dönüştürülüyor...", 1)
                aqr = parse_excel_request(excel_file_path)
                if log_callback:
                    log_callback(f"Excel başarıyla ayrıştırıldı. Sorgu: '{aqr.get('natural_query')}'", 1)
            except Exception as e:
                error_message = f"Excel Ayrıştırma Hatası: {str(e)}"
                if log_callback:
                    log_callback(f"Excel Ayrıştırma BAŞARISIZ: {str(e)}", 1)
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                return None, {"message": error_message, "error_type": "excel_parse_error"}, elapsed_ms
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

        else:
            error_message = "Girdi hatası: Hem Excel dosyası hem de Doğal Dil Sorgusu boş olamaz."
            if log_callback:
                log_callback("Girdi hatası: Girdi parametreleri eksik.", 1)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return None, {"message": error_message, "error_type": "input_error"}, elapsed_ms

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return aqr, None, elapsed_ms

    def _stage_retrieval(
        self,
        *,
        aqr: dict,
        natural_query: Optional[str],
        dialect: str,
        log_callback: Optional[Any],
    ) -> Tuple[dict, Optional[str], Optional[dict], Optional[dict], int]:
        """2. Şema Yükleme, Budama ve Deterministik Context Selection.

        Dönüş: (pruned_schema, prompt_schema_context, schema_selection_trace, error, elapsed_ms)
        error = {"message": str, "error_type": str, "pruned_schema_for_trace": dict,
                 "pruned_tables": list[str]} | None
        """
        t0 = time.perf_counter()
        schema_selection_trace = None
        pruned_schema: Dict[str, Any] = {}
        prompt_schema_context: Optional[str] = None

        try:
            if log_callback:
                log_callback("Veritabanı şeması analiz ediliyor ve akıllı budama (Schema Pruning) tetikleniyor...", 2)
            pruned_schema = self.schema_pruner.prune_schema(aqr, policy=TraversalPolicy(token_budget=8000))
            if pruned_schema.get("error"):
                error_message = pruned_schema["error"]
                if log_callback:
                    log_callback(f"Şema Budama Başarısız: {error_message}", 2)

                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                return (
                    pruned_schema,
                    None,
                    schema_selection_trace,
                    {
                        "message": error_message,
                        "error_type": "schema_pruning_error",
                        "pruned_schema_for_trace": pruned_schema,
                        "pruned_tables": [],
                    },
                    elapsed_ms,
                )

            pruned_tables = list(pruned_schema.get("tables", {}).keys())
            if log_callback:
                log_callback(f"Şema budama tamamlandı. Bütçelenen token: {pruned_schema.get('estimated_tokens', 0)}. Seçilen tablolar: {', '.join(pruned_tables)}", 2)

            # --- Context Selection ---
            if log_callback:
                log_callback("Deterministik schema context selection (Sprint 21.1) başlatılıyor...", 2)

            try:
                database_schema = from_legacy_schema(pruned_schema, dialect=dialect)
                schema_context_selection = select_schema_context(
                    schema=database_schema,
                    question=natural_query or aqr.get("natural_query", "")
                )

                prompt_schema_context = serialize_selection_for_prompt(
                    schema=database_schema,
                    selection=schema_context_selection,
                    max_columns_per_table=15
                )

                # Trace mapping
                schema_selection_trace = {
                    "focus_tables": schema_context_selection.focus_tables,
                    "selected_tables": [st.table_name for st in schema_context_selection.selected_tables],
                    "fallback_used": schema_context_selection.fallback_used,
                    "fallback_strategy": schema_context_selection.fallback_strategy,
                    "fallback_limit": schema_context_selection.fallback_limit,
                    "max_fallback_tables": schema_context_selection.max_fallback_tables,
                    "selector_version": "deterministic_v1",
                    "selection_failed": False
                }
            except Exception as context_e:
                error_message = f"Schema context selection failed: {context_e}"
                if log_callback:
                    log_callback(f"Context selection failed: {context_e}", 2)

                schema_selection_trace = {
                    "selector_version": "deterministic_v1",
                    "selection_failed": True,
                    "error_type": "schema_context_selection_exception",
                }

                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                return (
                    pruned_schema,
                    None,
                    schema_selection_trace,
                    {
                        "message": error_message,
                        "error_type": "schema_context_selection_exception",
                        "pruned_schema_for_trace": {"error": error_message},
                        "pruned_tables": pruned_tables,
                    },
                    elapsed_ms,
                )

        except Exception as e:
            error_message = f"Şema Budama Hatası: {str(e)}"
            if log_callback:
                log_callback(f"Şema Budama BAŞARISIZ: {str(e)}", 2)

            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return (
                pruned_schema,
                None,
                schema_selection_trace,
                {
                    "message": error_message,
                    "error_type": "schema_pruning_exception",
                    "pruned_schema_for_trace": {"error": error_message},
                    "pruned_tables": [],
                },
                elapsed_ms,
            )

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return pruned_schema, prompt_schema_context, schema_selection_trace, None, elapsed_ms

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
        known_secrets = set()
        if api_key:
            known_secrets.add(api_key)
        env_nvidia = os.environ.get("NVIDIA_API_KEY")
        if env_nvidia:
            known_secrets.add(env_nvidia)
        for env_k, env_v in os.environ.items():
            if env_v and any(sec in env_k.upper() for sec in ["KEY", "SECRET", "PASSWORD", "TOKEN"]):
                known_secrets.add(env_v)

        result = {
            "success": False,
            "aqr": None,
            "pruned_schema_tables": [],
            "generated_sql": "",
            "attempts": [],
            "error": None
        }
        
        schema_selection_trace = None

        if log_callback:
            log_callback("SQL üretim süreci başlatıldı...", 1)
            
        start_time = time.perf_counter()

        # 1. Girdi yorumlama (Excel AQR / doğal dil)
        aqr, intent_error, intent_ms = self._stage_intent(
            excel_file_path=excel_file_path, natural_query=natural_query,
            log_callback=log_callback)
        if intent_error:
            result["error"] = intent_error["message"]
            self._capture_trace_on_exit(
                start_time=start_time, job_id=job_id, dialect=dialect,
                natural_query=natural_query or "",
                pruned_schema={"error": result["error"]},
                generated_sql=None, last_generated_sql=None, sql_valid=None,
                sql_validation_errors=[], attempts=[],
                error_message=result["error"],
                error_type=intent_error["error_type"],
                known_secrets=known_secrets,
                schema_selection_trace=None)
            return redact_sensitive(result, known_secrets)
        result["aqr"] = aqr

        # 2. Şema yükleme + budama + context selection
        pruned_schema, prompt_schema_context, schema_selection_trace, retr_error, retrieval_ms = \
            self._stage_retrieval(aqr=aqr, natural_query=natural_query,
                                  dialect=dialect, log_callback=log_callback)
        if retr_error:
            result["error"] = retr_error["message"]
            result["pruned_schema_tables"] = retr_error.get("pruned_tables", [])
            self._capture_trace_on_exit(
                start_time=start_time, job_id=job_id, dialect=dialect,
                natural_query=natural_query or aqr.get("natural_query", ""),
                pruned_schema=retr_error["pruned_schema_for_trace"],
                generated_sql=None, last_generated_sql=None, sql_valid=None,
                sql_validation_errors=[], attempts=[],
                error_message=result["error"],
                error_type=retr_error["error_type"],
                known_secrets=known_secrets,
                schema_selection_trace=schema_selection_trace)
            return redact_sensitive(result, known_secrets)
        result["pruned_schema_tables"] = list(pruned_schema.get("tables", {}).keys())

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
                        prompt_schema_context=prompt_schema_context,
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
                        prompt_schema_context=prompt_schema_context,
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
                    
                    if guardrail_errors[0]["type"] == "sql_parse_error":
                        continue
                    else:
                        break

                # --- Sandbox Safety Validation ---
                try:
                    SqlSafetyValidator().ensure_read_only(current_sql)
                except sqlglot.errors.ParseError:
                    # Let the syntax parse errors be caught standardly by the pipeline's AST validator
                    pass
                except ValueError as safety_err:
                    last_error = str(safety_err)
                    attempt_info["valid"] = False
                    attempt_info["error"] = last_error
                    attempt_info["validation_errors"] = [{
                        "type": "unsafe_sql",
                        "stage": "sql_sandbox_safety",
                        "message": last_error
                    }]
                    result["attempts"].append(attempt_info)
                    validation_errors.append(attempt_info["validation_errors"][0])
                    if log_callback:
                        log_callback(f"Sandbox güvenlik doğrulaması BAŞARISIZ: {last_error}", 4)
                    break

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
                    err.get("stage") in ["sql_guardrail", "sql_sandbox_safety"] 
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
            error_type=final_error_type,
            known_secrets=known_secrets,
            schema_selection_trace=schema_selection_trace
        )
                
        return redact_sensitive(result, known_secrets)

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
        error_type: Optional[str] = None,
        known_secrets: Optional[Set[str]] = None,
        schema_selection_trace: Optional[Dict[str, Any]] = None
    ):
        if not self.trace_store:
            return
            
        total_ms = int((time.perf_counter() - start_time) * 1000)

        # Collect known secrets dynamically for trace redaction
        known_secrets = set(known_secrets or set())
        env_nvidia = os.environ.get("NVIDIA_API_KEY")
        if env_nvidia:
            known_secrets.add(env_nvidia)
        for env_k, env_v in os.environ.items():
            if env_v and any(sec in env_k.upper() for sec in ["KEY", "SECRET", "PASSWORD", "TOKEN"]):
                known_secrets.add(env_v)

        # Redact potentially sensitive input parameters before saving
        natural_query = redact_sensitive(natural_query, known_secrets)
        pruned_schema = redact_sensitive(pruned_schema, known_secrets)
        generated_sql = redact_sensitive(generated_sql, known_secrets)
        last_generated_sql = redact_sensitive(last_generated_sql, known_secrets)
        sql_validation_errors = redact_sensitive(sql_validation_errors, known_secrets)
        attempts = redact_sensitive(attempts, known_secrets)
        error_message = redact_sensitive(error_message, known_secrets)
        
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
            },
            schema_context_selection=schema_selection_trace
        )
        self._save_trace_safely(trace)
