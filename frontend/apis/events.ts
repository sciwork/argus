import { apiClient } from "@/apis/client";
import type { EventSummary, EventTimeseries } from "@/types/responses/events";

export async function listEvents(): Promise<EventSummary[]> {
  const response = await apiClient.get<EventSummary[]>("/events");
  return response.data;
}

export async function getEventTimeseries(
  slug: string,
): Promise<EventTimeseries> {
  const response = await apiClient.get<EventTimeseries>(
    `/events/${encodeURIComponent(slug)}/timeseries`,
  );
  return response.data;
}

export async function deleteEvent(slug: string): Promise<void> {
  await apiClient.delete(`/events/${encodeURIComponent(slug)}`);
}

export async function triggerReport(): Promise<void> {
  await apiClient.post("/report/trigger");
}
