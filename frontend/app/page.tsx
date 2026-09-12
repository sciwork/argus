"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";
import { CalendarX, ChevronRight, RefreshCw } from "lucide-react";
import toast from "react-hot-toast";
import { deleteEvent, listEvents, triggerReport } from "@/apis/events";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useRequireAuth } from "@/hooks/use-require-auth";
import { formatEventStartDate } from "@/lib/datetime";
import type { EventSummary } from "@/types/responses/events";

export default function DashboardHomePage() {
  const auth = useRequireAuth();
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [isLoadingEvents, startLoadingEvents] = useTransition();
  const [isTriggeringReport, startTriggeringReport] = useTransition();
  const [isDeleting, startDeleting] = useTransition();

  useEffect(() => {
    if (auth.status !== "authenticated") return;
    let cancelled = false;
    startLoadingEvents(async () => {
      try {
        const result = await listEvents();
        if (!cancelled) setEvents(result);
      } catch (err) {
        if (!cancelled) {
          console.error("Failed to load events:", err);
          toast.error("Failed to load events");
        }
      }
    });
    return () => {
      cancelled = true;
    };
  }, [auth.status]);

  if (auth.status === "loading") {
    return null;
  }
  if (auth.status === "error") {
    return (
      <p className="text-base text-destructive">
        Failed to load: {auth.message}
      </p>
    );
  }
  if (auth.status !== "authenticated") {
    return null;
  }

  const handleTriggerReport = () => {
    startTriggeringReport(async () => {
      try {
        await triggerReport();
      } catch (err) {
        console.error("Failed to trigger report:", err);
        toast.error("Failed to trigger report");
      }
    });
  };

  const handleDelete = (slug: string, name: string) => {
    if (
      !window.confirm(
        `Delete event "${name}"?\n\nThis will permanently remove the event and all of its tickets.\nThis cannot be undone.`,
      )
    ) {
      return;
    }
    startDeleting(async () => {
      try {
        await deleteEvent(slug);
        setEvents(await listEvents());
      } catch (err) {
        console.error("Failed to delete event:", err);
        toast.error("Failed to delete event");
      }
    });
  };

  return (
    <>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-semibold">Events</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {auth.user.email}
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={handleTriggerReport}
          disabled={isTriggeringReport}
        >
          <RefreshCw className="size-3.5" />
          Run report now
        </Button>
      </div>
      <div className="mt-8 flex flex-col gap-3">
        {isLoadingEvents && (
          <p className="text-base text-muted-foreground">Loading…</p>
        )}
        {!isLoadingEvents && events.length === 0 && (
          <EmptyState
            icon={CalendarX}
            title="No events yet"
            description="Events appear automatically once KKTIX sends a registration webhook."
          />
        )}
        {!isLoadingEvents &&
          events.map((event) => {
            const startLabel = formatEventStartDate(event.start_at);
            return (
              <div
                key={event.event_slug}
                className="flex items-center justify-between gap-4 rounded-lg border border-border bg-card p-5 transition-colors hover:border-primary/40"
              >
                <Link
                  href={`/events?slug=${encodeURIComponent(event.event_slug)}`}
                  className="min-w-0 flex-1"
                >
                  <div className="text-base font-medium">
                    {event.event_name}
                  </div>
                  <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                    {event.channel && (
                      <Badge className="rounded-full bg-primary/15 px-2.5 py-0.5 text-xs text-primary">
                        {event.channel}
                      </Badge>
                    )}
                    {event.capacity !== null && (
                      <span>Capacity {event.capacity}</span>
                    )}
                    {startLabel && (
                      <>
                        <span className="text-border">·</span>
                        <span>Starts {startLabel}</span>
                      </>
                    )}
                  </div>
                </Link>
                <div className="flex items-center gap-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() =>
                      handleDelete(event.event_slug, event.event_name)
                    }
                    disabled={isDeleting}
                  >
                    Delete
                  </Button>
                  <ChevronRight className="size-4 text-muted-foreground" />
                </div>
              </div>
            );
          })}
      </div>
    </>
  );
}
