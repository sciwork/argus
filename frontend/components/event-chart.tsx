"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  XAxis,
  YAxis,
} from "recharts";
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import type { EventTimeseries } from "@/types/responses/events";

interface EventChartProps {
  timeseries: EventTimeseries;
}

export function EventChart({ timeseries }: EventChartProps) {
  // Recharts' category x-axis derives its domain purely from the plotted
  // data, ignoring an explicit `domain` prop — so a ReferenceLine for a date
  // outside `labels` (e.g. an upcoming event's start date) is silently
  // discarded unless that date is itself a row in `data`. Add it as an
  // otherwise-empty row so the axis includes it, connecting the surrounding
  // line across the gap.
  const labels =
    timeseries.start_marker_label !== null &&
    !timeseries.labels.includes(timeseries.start_marker_label)
      ? [...timeseries.labels, timeseries.start_marker_label].sort()
      : timeseries.labels;

  const data = labels.map((label) => {
    const point: Record<string, string | number> = { label };
    const index = timeseries.labels.indexOf(label);
    if (index !== -1) {
      timeseries.datasets.forEach((dataset, datasetIndex) => {
        point[`series-${datasetIndex}`] = dataset.data[index];
      });
    }
    return point;
  });

  // Ticket-type names come from arbitrary KKTIX strings (spaces, parens,
  // etc.) and are unsafe to interpolate directly into a CSS custom-property
  // name (`var(--color-${name})`) or a Recharts dataKey — key everything by
  // index instead. `dataset.name` is still used as the human-readable
  // `label` (shown in the tooltip) and for the `strokeWidth` check below.
  const config: ChartConfig = Object.fromEntries(
    timeseries.datasets.map((dataset, index) => [
      `series-${index}`,
      { label: dataset.name, color: `var(--chart-${(index % 5) + 1})` },
    ]),
  );

  return (
    <ChartContainer config={config} className="h-80 w-full">
      <LineChart data={data}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="label" tickLine={false} axisLine={false} />
        <YAxis tickLine={false} axisLine={false} />
        <ChartTooltip content={<ChartTooltipContent />} />
        <ChartLegend content={<ChartLegendContent />} />
        {timeseries.event.capacity !== null && (
          <ReferenceLine
            y={timeseries.event.capacity}
            strokeDasharray="4 4"
            label="Capacity"
            ifOverflow="extendDomain"
          />
        )}
        {timeseries.start_marker_label !== null && (
          <ReferenceLine
            x={timeseries.start_marker_label}
            strokeDasharray="4 4"
            label="Event start"
          />
        )}
        {timeseries.datasets.map((dataset, index) => (
          <Line
            key={`series-${index}`}
            dataKey={`series-${index}`}
            stroke={`var(--color-series-${index})`}
            strokeWidth={dataset.name === "Total" ? 2 : 1}
            dot={false}
            connectNulls
          />
        ))}
      </LineChart>
    </ChartContainer>
  );
}
