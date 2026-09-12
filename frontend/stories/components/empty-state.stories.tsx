import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Inbox } from "lucide-react";
import { expect } from "storybook/test";
import { EmptyState } from "@/components/empty-state";

const meta = {
  component: EmptyState,
  tags: ["ai-generated"],
  args: {
    icon: Inbox,
    title: "No webhook events yet",
    description:
      "Registration and cancellation webhooks from KKTIX will show up here.",
  },
} satisfies Meta<typeof EmptyState>;

export default meta;
type Story = StoryObj<typeof meta>;

// Smoke check — one is enough per file
export const Default: Story = {
  play: async ({ canvas }) => {
    await expect(canvas.getByText("No webhook events yet")).toBeVisible();
    await expect(
      canvas.getByText(
        "Registration and cancellation webhooks from KKTIX will show up here.",
      ),
    ).toBeVisible();
  },
};

export const WithoutDescription: Story = {
  args: { description: undefined },
};
