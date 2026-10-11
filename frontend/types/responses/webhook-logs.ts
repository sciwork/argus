export interface WebhookLogEntry {
  id: number;
  method: string;
  channel: string | null;
  headers: string;
  body: string | null;
  created_at: string;
}

export interface WebhookLogsPage {
  items: WebhookLogEntry[];
  total: number;
  limit: number;
  offset: number;
}
