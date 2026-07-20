import { extractApiErrorMessage } from '../utils/apiError';

const DEFAULT_BACKEND_URL = `http://${window.location.hostname}:8000`;
const DEFAULT_API_KEY = 'sqlgen_secret_dev_key';

export interface Job {
  id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';
  file_path: string | null;
  natural_query: string | null;
  result_sql: string | null;
  error_message: string | null;
  /** Taksonomi kodu (backend ErrorCode.value) — şu an UI'da gösterilmiyor,
   *  yalnız taşınıyor (Sprint 27.2.1). */
  error_code: string | null;
  dialect?: string;
  created_at: string;
  updated_at: string;
}

export interface Config {
  key: string;
  value: string;
}

class ApiService {
  private getBackendUrl(): string {
    return localStorage.getItem('sqlgen_backend_url') || DEFAULT_BACKEND_URL;
  }

  private getApiKey(): string {
    return localStorage.getItem('sqlgen_api_key') || DEFAULT_API_KEY;
  }

  private getHeaders(): HeadersInit {
    return {
      'X-API-Key': this.getApiKey(),
      'Content-Type': 'application/json',
    };
  }

  async health(): Promise<any> {
    const res = await fetch(`${this.getBackendUrl()}/health`);
    if (!res.ok) throw new Error('API connection failed');
    return res.json();
  }

  async getConfig(key: string): Promise<Config> {
    const res = await fetch(`${this.getBackendUrl()}/api/configs/${key}`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error(`Config fetch failed for ${key}`);
    return res.json();
  }

  async setConfig(key: string, value: string): Promise<any> {
    const res = await fetch(`${this.getBackendUrl()}/api/configs/${key}`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ value }),
    });
    if (!res.ok) throw new Error(`Config set failed for ${key}`);
    return res.json();
  }

  async uploadFile(file: File, naturalQuery?: string): Promise<{ status: string; job: Job }> {
    const formData = new FormData();
    formData.append('file', file);
    if (naturalQuery) {
      formData.append('natural_query', naturalQuery);
    }

    const headers: HeadersInit = {
      'X-API-Key': this.getApiKey(),
    };

    const res = await fetch(`${this.getBackendUrl()}/api/files/upload`, {
      method: 'POST',
      headers,
      body: formData,
    });
    if (!res.ok) throw new Error('File upload failed');
    return res.json();
  }

  async startJob(naturalQuery: string, previousSql?: string): Promise<{ status: string; job: Job }> {
    const payload: any = { natural_query: naturalQuery };
    if (previousSql) {
      payload.previous_sql = previousSql;
    }
    const res = await fetch(`${this.getBackendUrl()}/api/jobs/without-file`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Job creation failed');
    return res.json();
  }

  async listJobs(limit = 50, offset = 0): Promise<{ jobs: Job[] }> {
    const res = await fetch(`${this.getBackendUrl()}/api/jobs?limit=${limit}&offset=${offset}`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to list jobs');
    return res.json();
  }

  async getJob(jobId: string): Promise<Job> {
    const res = await fetch(`${this.getBackendUrl()}/api/jobs/${jobId}`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error(`Failed to fetch job detail for ${jobId}`);
    return res.json();
  }

  async cancelJob(jobId: string): Promise<{ status: string; job: Job }> {
    const res = await fetch(`${this.getBackendUrl()}/api/jobs/${jobId}/cancel`, {
      method: 'POST',
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error(`Failed to cancel job ${jobId}`);
    return res.json();
  }

  async getSchema(forceRefresh = false): Promise<any> {
    const res = await fetch(`${this.getBackendUrl()}/api/schema?refresh=${forceRefresh}`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to fetch schema');
    return res.json();
  }

  async getRawSchema(): Promise<any> {
    const res = await fetch(`${this.getBackendUrl()}/api/schema/raw`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to fetch raw schema');
    return res.json();
  }

  async refreshSchema(): Promise<{ status: string; message: string; schema: any }> {
    const res = await fetch(`${this.getBackendUrl()}/api/schema/refresh`, {
      method: 'POST',
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to refresh database schema cache');
    return res.json();
  }

  async getRagStats(): Promise<{ status: string; stats: Record<string, number> }> {
    const res = await fetch(`${this.getBackendUrl()}/api/rag/stats`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to fetch RAG statistics');
    return res.json();
  }

  async searchRag(query: string, collection: string, limit = 3): Promise<{ status: string; results: any[] }> {
    const res = await fetch(`${this.getBackendUrl()}/api/rag/search`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ query, collection, limit }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(extractApiErrorMessage(errData, 'RAG search execution failed'));
    }
    return res.json();
  }

  async indexBusinessRule(ruleId: string, ruleText: string, sqlMapping: string): Promise<any> {
    const res = await fetch(`${this.getBackendUrl()}/api/rag/index/business-rule`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ rule_id: ruleId, rule_text: ruleText, sql_mapping: sqlMapping }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(extractApiErrorMessage(errData, 'Failed to index business rule'));
    }
    return res.json();
  }

  async indexSqlHistory(historyId: string, naturalQuery: string, sql: string): Promise<any> {
    const res = await fetch(`${this.getBackendUrl()}/api/rag/index/sql-history`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ history_id: historyId, natural_query: naturalQuery, sql }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(extractApiErrorMessage(errData, 'Failed to index SQL history pair'));
    }
    return res.json();
  }

  async getCustomRelations(): Promise<{ status: string; relations: any[] }> {
    const res = await fetch(`${this.getBackendUrl()}/api/schema/custom-relations`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to fetch custom relations');
    return res.json();
  }

  async saveCustomRelations(relations: any[]): Promise<any> {
    const res = await fetch(`${this.getBackendUrl()}/api/schema/custom-relations`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ relations }),
    });
    if (!res.ok) throw new Error('Failed to save custom relations');
    return res.json();
  }

  async getSchemaFilters(): Promise<{ status: string; hidden_tables: string[], hidden_columns: Record<string, string[]> }> {
    const res = await fetch(`${this.getBackendUrl()}/api/schema/filters`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to fetch schema filters');
    return res.json();
  }

  async saveSchemaFilters(hiddenTables: string[], hiddenColumns: Record<string, string[]>): Promise<any> {
    const res = await fetch(`${this.getBackendUrl()}/api/schema/filters`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ hidden_tables: hiddenTables, hidden_columns: hiddenColumns }),
    });
    if (!res.ok) throw new Error('Failed to save schema filters');
    return res.json();
  }

  async getDisabledRelations(): Promise<{ status: string; relations: any[] }> {
    const res = await fetch(`${this.getBackendUrl()}/api/schema/disabled-relations`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to fetch disabled relations');
    return res.json();
  }

  async saveDisabledRelations(relations: any[]): Promise<any> {
    const res = await fetch(`${this.getBackendUrl()}/api/schema/disabled-relations`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ relations }),
    });
    if (!res.ok) throw new Error('Failed to save disabled relations');
    return res.json();
  }
}

export const apiService = new ApiService();
