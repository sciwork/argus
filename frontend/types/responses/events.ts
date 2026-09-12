export interface EventSummary {
  event_slug: string;
  event_name: string;
  channel: string | null;
  start_at: string | null;
  capacity: number | null;
}

export interface TimeseriesDataset {
  name: string;
  data: number[];
}

export interface EventTimeseries {
  event: EventSummary;
  labels: string[];
  datasets: TimeseriesDataset[];
  start_marker_label: string | null;
}
