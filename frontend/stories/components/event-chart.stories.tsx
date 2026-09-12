import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect } from "storybook/test";
import { EventChart } from "@/components/event-chart";

const meta = {
  title: "Components/EventChart",
  component: EventChart,
  tags: ["ai-generated"],
} satisfies Meta<typeof EventChart>;

export default meta;
type Story = StoryObj<typeof meta>;

// Smoke check — one is enough per file
export const Default: Story = {
  args: {
    timeseries: {
      event: {
        event_slug: "test-event",
        event_name: "Test Event",
        channel: "SPRINT",
        start_at: "2026-04-25T01:00:00",
        capacity: 30,
      },
      labels: ["2026-04-15", "2026-04-16", "2026-04-17"],
      datasets: [
        { name: "Total", data: [1, 3, 5] },
        { name: "一般票", data: [1, 2, 3] },
        { name: "早鳥票", data: [0, 1, 2] },
      ],
      start_marker_label: "2026-04-25",
    },
  },
  play: async ({ canvasElement }) => {
    // Recharts renders each `<Line>` as a `.recharts-line` group — assert
    // one per dataset rather than just checking that something rendered.
    const lines = canvasElement.querySelectorAll(".recharts-line");
    await expect(lines).toHaveLength(3);
  },
};
