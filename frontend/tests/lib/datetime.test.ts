import { describe, expect, it } from "vitest";
import { formatEventStartDate, formatTaipeiDateTime } from "@/lib/datetime";

describe("formatTaipeiDateTime", () => {
  it("converts a naive SQLite-shaped UTC timestamp to Taipei time (+8)", () => {
    expect(formatTaipeiDateTime("2026-08-16 06:00:37")).toBe(
      "2026-08-16 14:00:37",
    );
  });

  it("rolls over into the next day when the UTC+8 offset crosses midnight", () => {
    expect(formatTaipeiDateTime("2026-08-16 20:15:00")).toBe(
      "2026-08-17 04:15:00",
    );
  });

  it("accepts an ISO string with an explicit Z suffix", () => {
    expect(formatTaipeiDateTime("2026-08-16T06:00:37Z")).toBe(
      "2026-08-16 14:00:37",
    );
  });

  it("accepts a timestamp with an explicit numeric offset", () => {
    expect(formatTaipeiDateTime("2026-08-16T06:00:37+00:00")).toBe(
      "2026-08-16 14:00:37",
    );
  });
});

describe("formatEventStartDate", () => {
  it("returns null when there is no start_at", () => {
    expect(formatEventStartDate(null)).toBeNull();
  });

  it("includes the year, not just month and day", () => {
    // Regression test: two events on the same month/day but different
    // years used to render identically ("Dec 1") in the events list.
    expect(formatEventStartDate("2026-12-01T10:00:00")).toBe("Dec 1, 2026");
    expect(formatEventStartDate("2027-12-01T10:00:00")).toBe("Dec 1, 2027");
  });
});
