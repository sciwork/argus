"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, useTransition } from "react";
import { ChevronLeft, FileQuestion, MousePointerClick } from "lucide-react";
import toast from "react-hot-toast";
import { getEventTimeseries } from "@/apis/events";
import { EmptyState } from "@/components/empty-state";
import { EventChart } from "@/components/event-chart";
import { Badge } from "@/components/ui/badge";
import { formatEventStartDate } from "@/lib/datetime";
import type { EventTimeseries } from "@/types/responses/events";

function EventDetailContent() {
  const searchParams = useSearchParams();
  const slug = searchParams.get("slug");
  const [timeseries, setTimeseries] = useState<EventTimeseries | null>(null);
  const [isLoadingTimeseries, startLoadingTimeseries] = useTransition();

  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    startLoadingTimeseries(async () => {
      try {
        const result = await getEventTimeseries(slug);
        if (!cancelled) setTimeseries(result);
      } catch (err) {
        if (!cancelled) {
          console.error("Failed to load event data:", err);
          toast.error("Failed to load event data");
        }
      }
    });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (isLoadingTimeseries) {
    return <p>Loading…</p>;
  }

  if (!slug) {
    return (
      <EmptyState
        icon={MousePointerClick}
        title="No event selected"
        description="Pick an event from the list to see its registration chart."
      />
    );
  }

  if (!timeseries) {
    return (
      <EmptyState
        icon={FileQuestion}
        title="No data available"
        description="This event doesn't have any chart data yet."
      />
    );
  }

  const startLabel = formatEventStartDate(timeseries.event.start_at);

  return (
    <>
      <Link
        href="/"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronLeft className="size-3.5" />
        Back to events
      </Link>
      <h1 className="mt-3 font-heading text-3xl font-semibold">
        {timeseries.event.event_name}
      </h1>
      <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
        {timeseries.event.channel && (
          <Badge className="rounded-full bg-primary/15 px-2.5 py-0.5 text-xs text-primary">
            {timeseries.event.channel}
          </Badge>
        )}
        {timeseries.event.capacity !== null && (
          <span>Capacity {timeseries.event.capacity}</span>
        )}
        {startLabel && (
          <>
            <span className="text-border">·</span>
            <span>Starts {startLabel}</span>
          </>
        )}
      </div>
      <div className="mt-6 rounded-lg border border-border bg-card p-5">
        <EventChart timeseries={timeseries} />
      </div>
    </>
  );
}

export default function EventDetailPage() {
  // useSearchParams() opts the page out of static prerendering unless it's
  // wrapped in Suspense — required even for a fully client-rendered,
  // statically-exported route like this one (see next.config.ts's
  // `output: "export"`).
  return (
    <Suspense fallback={<p>Loading…</p>}>
      <EventDetailContent />
    </Suspense>
  );
}
