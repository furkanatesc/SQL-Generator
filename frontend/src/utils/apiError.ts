/**
 * Backend hata gövdesinden kullanıcıya gösterilecek mesajı çıkarır.
 *
 * Backend TÜM hataları global handler'larla şu envelope'a sarar
 * (backend/app/api/errors.py):
 *   {"error": {"code": ..., "message": ..., "details": ...}}
 * Eski kod `errData.detail` okuyordu; bu alan hiçbir zaman gelmediği için
 * her mesaj sessizce düşüyor, kullanıcı hep hardcoded fallback görüyordu.
 *
 * FastAPI'nin varsayılan {"detail": "..."} biçimi geriye dönük tolerans
 * olarak destekleniyor (handler'ları atlayan bir yol kalırsa diye).
 */
export function extractApiErrorMessage(errData: unknown, fallback: string): string {
  if (errData && typeof errData === 'object') {
    const err = (errData as Record<string, unknown>).error;
    if (err && typeof err === 'object') {
      const message = (err as Record<string, unknown>).message;
      if (typeof message === 'string' && message) return message;
    }
    const detail = (errData as Record<string, unknown>).detail;
    if (typeof detail === 'string' && detail) return detail;
  }
  return fallback;
}
