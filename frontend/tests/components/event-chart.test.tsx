import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EventChart } from "@/components/event-chart";
import type { EventTimeseries } from "@/types/responses/events";

const sample: EventTimeseries = {
  event: {
    event_slug: "test-event",
    event_name: "Test Event",
    channel: "SPRINT",
    start_at: "2026-04-25T01:00:00",
    capacity: 30,
  },
  labels: ["2026-04-15", "2026-04-16"],
  datasets: [
    { name: "Total", data: [1, 3] },
    { name: "一般票", data: [1, 2] },
  ],
  start_marker_label: "2026-04-25",
};

describe("EventChart", () => {
  it("renders a line for every dataset", () => {
    const { container } = render(<EventChart timeseries={sample} />);

    const lines = container.querySelectorAll(".recharts-line");
    expect(lines).toHaveLength(sample.datasets.length);
  });

  it("renders both the capacity and event-start reference lines when present", () => {
    const { container } = render(<EventChart timeseries={sample} />);

    const referenceLines = container.querySelectorAll(
      ".recharts-reference-line",
    );
    expect(referenceLines).toHaveLength(2);
  });

  it("omits reference lines whose value is null", () => {
    const timeseries: EventTimeseries = {
      ...sample,
      event: { ...sample.event, capacity: null },
      start_marker_label: null,
    };
    const { container } = render(<EventChart timeseries={timeseries} />);

    const referenceLines = container.querySelectorAll(
      ".recharts-reference-line",
    );
    expect(referenceLines).toHaveLength(0);
  });
});
