"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, useTransition } from "react";
import { ChevronLeft, FileQuestion, MousePointerClick } from "lucide-react";
import toast from "react-hot-toast";
import { deleteEvent, getEventTimeseries } from "@/apis/events";
import { EmptyState } from "@/components/empty-state";
import { EventChart } from "@/components/event-chart";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatEventStartDate } from "@/lib/datetime";
import type { EventTimeseries } from "@/types/responses/events";

function EventDetailContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const slug = searchParams.get("slug");
  const [timeseries, setTimeseries] = useState<EventTimeseries | null>(null);
  const [isLoadingTimeseries, startLoadingTimeseries] = useTransition();
  const [isDeleting, startDeleting] = useTransition();

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
  const eventName = timeseries.event.event_name;

  const handleDelete = () => {
    if (
      !window.confirm(
        `Delete event "${eventName}"?\n\nThis will permanently remove the event and all of its tickets.\nThis cannot be undone.`,
      )
    ) {
      return;
    }
    startDeleting(async () => {
      try {
        await deleteEvent(slug);
        router.push("/");
      } catch (err) {
        console.error("Failed to delete event:", err);
        toast.error("Failed to delete event");
      }
    });
  };

  return (
    <>
      <Link
        href="/"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronLeft className="size-3.5" />
        Back to events
      </Link>
      <div className="mt-3 flex flex-col items-start gap-4 tablet:flex-row tablet:items-start tablet:justify-between">
        <h1 className="font-heading text-3xl font-semibold">{eventName}</h1>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-destructive hover:text-destructive"
          onClick={handleDelete}
          disabled={isDeleting}
        >
          Delete event
        </Button>
      </div>
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
