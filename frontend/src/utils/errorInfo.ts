// Backend hata taksonomisini (Sprint 27.2/27.2.1 — `app/errors/codes.py` +
// `categories.py` + `registry.py::_CATEGORY_BY_CODE`) kullanıcı-okur Türkçe
// gösterime eşleyen saf util. `Job.error_code` zaten taşınıyordu ama UI'da
// gösterilmiyordu; bu util onu kategori + etiket + ipucu + ton'a çevirir.

export type ErrorCategory =
  | 'input'
  | 'retrieval'
  | 'generation'
  | 'validation'
  | 'security'
  | 'execution'
  | 'internal';

export type ErrorTone = 'error' | 'warning';

// Backend registry._CATEGORY_BY_CODE'un birebir aynası (drift olursa fallback devreye girer)
const CODE_TO_CATEGORY: Record<string, ErrorCategory> = {
  input_error: 'input',
  excel_parse_error: 'input',
  schema_pruning_failed: 'retrieval',
  schema_pruning_crashed: 'retrieval',
  schema_context_selection_crashed: 'retrieval',
  llm_api_error: 'generation',
  sql_generation_exhausted: 'generation',
  empty_sql: 'validation',
  sql_parse_error: 'validation',
  syntax_error: 'validation',
  missing_table: 'validation',
  missing_column: 'validation',
  semantic_validation_failed: 'validation',
  unsupported_dialect: 'validation',
  multiple_statements: 'security',
  non_select_statement: 'security',
  unsafe_dangerous_function: 'security',
  unsafe_dml_keyword: 'security',
  unsafe_sandbox_rejected: 'security',
  query_timeout: 'execution',
  row_limit_exceeded: 'execution',
  read_only_violation: 'execution',
  permission_denied: 'execution',
  database_not_found: 'execution',
  invalid_result_shape: 'execution',
  execution_failed: 'execution',
};

// Kod başına kısa Türkçe etiket + (bazılarında) eyleme dönük ipucu
const CODE_LABEL: Record<string, { label: string; hint?: string }> = {
  input_error: { label: 'Girdi hatası', hint: 'Sorgu metnini veya yüklenen dosyayı kontrol edin.' },
  excel_parse_error: { label: 'Excel dosyası okunamadı', hint: 'Dosya biçimini (.xlsx/.csv) kontrol edin.' },
  schema_pruning_failed: { label: 'Şema daraltma başarısız' },
  schema_pruning_crashed: { label: 'Şema daraltma çöktü' },
  schema_context_selection_crashed: { label: 'Şema bağlam seçimi çöktü' },
  llm_api_error: { label: 'LLM servis hatası', hint: 'Biraz sonra tekrar deneyin.' },
  sql_generation_exhausted: { label: 'SQL üretilemedi (deneme limiti)', hint: 'Sorguyu sadeleştirip tekrar deneyin.' },
  empty_sql: { label: 'Boş SQL üretildi' },
  sql_parse_error: { label: 'SQL ayrıştırılamadı' },
  syntax_error: { label: 'SQL sözdizimi hatası' },
  missing_table: { label: 'Bilinmeyen tablo', hint: 'Sorguda geçen tablo şemada bulunamadı; tablo adını kontrol edin.' },
  missing_column: { label: 'Bilinmeyen sütun', hint: 'Sorguda geçen sütun şemada bulunamadı; sütun adını kontrol edin.' },
  semantic_validation_failed: { label: 'Anlamsal doğrulama başarısız' },
  unsupported_dialect: { label: 'Desteklenmeyen dialect' },
  multiple_statements: { label: 'Birden fazla ifade reddedildi', hint: 'Tek bir SELECT sorgusu kullanın.' },
  non_select_statement: { label: 'Yalnız SELECT sorgularına izin var' },
  unsafe_dangerous_function: { label: 'Tehlikeli fonksiyon reddedildi' },
  unsafe_dml_keyword: { label: 'Veri değiştiren anahtar kelime reddedildi', hint: 'Yalnız okuma (SELECT) sorgularına izin verilir.' },
  unsafe_sandbox_rejected: { label: 'Güvenlik kontrolü sorguyu reddetti' },
  query_timeout: { label: 'Sorgu zaman aşımına uğradı', hint: 'Sorguyu sadeleştirin veya filtre ekleyin.' },
  row_limit_exceeded: { label: 'Satır limiti aşıldı', hint: 'Sonuç kısıtlandı; LIMIT veya daha dar filtre ekleyin.' },
  read_only_violation: { label: 'Salt-okunur ihlali' },
  permission_denied: { label: 'İzin reddedildi' },
  database_not_found: { label: 'Veritabanı bulunamadı' },
  invalid_result_shape: { label: 'Geçersiz sonuç şekli' },
  execution_failed: { label: 'Sorgu çalıştırma başarısız' },
};

const CATEGORY_LABEL: Record<ErrorCategory, { label: string; tone: ErrorTone }> = {
  input: { label: 'Girdi', tone: 'error' },
  retrieval: { label: 'Şema / Retrieval', tone: 'error' },
  generation: { label: 'Üretim', tone: 'error' },
  validation: { label: 'Doğrulama', tone: 'error' },
  security: { label: 'Güvenlik', tone: 'error' },
  execution: { label: 'Çalıştırma', tone: 'warning' },
  internal: { label: 'İç hata', tone: 'error' },
};

export interface ErrorInfo {
  code: string | null;
  category: ErrorCategory;
  categoryLabel: string;
  label: string;
  hint?: string;
  tone: ErrorTone;
}

/** error_code'u kullanıcı-okur gösterime çevirir. Bilinmeyen/null kod → nazik
 *  fallback (category 'internal', label = fallbackMessage ?? 'Hata'). */
export function describeError(code?: string | null, fallbackMessage?: string | null): ErrorInfo {
  const normalized = code ? code.trim().toLowerCase() : '';
  const category = CODE_TO_CATEGORY[normalized];

  if (!category) {
    return {
      code: code ?? null,
      category: 'internal',
      categoryLabel: CATEGORY_LABEL.internal.label,
      label: (fallbackMessage && fallbackMessage.trim()) || 'Hata',
      tone: 'error',
    };
  }

  const cat = CATEGORY_LABEL[category];
  const codeInfo = CODE_LABEL[normalized] ?? { label: cat.label };
  return {
    code: normalized,
    category,
    categoryLabel: cat.label,
    label: codeInfo.label,
    hint: codeInfo.hint,
    tone: cat.tone,
  };
}
