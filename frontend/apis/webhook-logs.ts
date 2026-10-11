import { apiClient } from "@/apis/client";
import type { WebhookLogsPage } from "@/types/responses/webhook-logs";

export async function listWebhookLogs(
  limit: number,
  offset: number,
): Promise<WebhookLogsPage> {
  const response = await apiClient.get<WebhookLogsPage>("/webhook-logs", {
    params: { limit, offset },
  });
  return response.data;
}

export async function deleteWebhookLog(id: number): Promise<void> {
  await apiClient.delete(`/webhook-logs/${id}`);
}

export async function clearWebhookLogs(): Promise<void> {
  await apiClient.delete("/webhook-logs");
}
