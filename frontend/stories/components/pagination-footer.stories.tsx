import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, fn, userEvent } from "storybook/test";
import { PaginationFooter } from "@/components/pagination-footer";

const meta = {
  component: PaginationFooter,
  tags: ["ai-generated"],
  args: {
    offset: 50,
    limit: 50,
    total: 130,
    onOffsetChange: fn(),
  },
} satisfies Meta<typeof PaginationFooter>;

export default meta;
type Story = StoryObj<typeof meta>;

// Middle page — both Previous and Next enabled, clicking each reports the
// expected next offset.
export const Default: Story = {
  play: async ({ canvas, args }) => {
    await expect(canvas.getByText("51–100 of 130")).toBeVisible();
    const previous = canvas.getByRole("button", { name: "Previous" });
    const next = canvas.getByRole("button", { name: "Next" });
    await expect(previous).toBeEnabled();
    await expect(next).toBeEnabled();

    await userEvent.click(previous);
    await expect(args.onOffsetChange).toHaveBeenLastCalledWith(0);

    await userEvent.click(next);
    await expect(args.onOffsetChange).toHaveBeenLastCalledWith(100);
  },
};

export const FirstPage: Story = {
  args: { offset: 0 },
  play: async ({ canvas }) => {
    await expect(
      canvas.getByRole("button", { name: "Previous" }),
    ).toBeDisabled();
    await expect(canvas.getByRole("button", { name: "Next" })).toBeEnabled();
  },
};

export const LastPage: Story = {
  args: { offset: 100 },
  play: async ({ canvas }) => {
    await expect(
      canvas.getByRole("button", { name: "Previous" }),
    ).toBeEnabled();
    await expect(canvas.getByRole("button", { name: "Next" })).toBeDisabled();
  },
};
