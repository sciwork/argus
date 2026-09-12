"use client";

import { useEffect, useState, useTransition } from "react";
import { ChevronRight, Inbox } from "lucide-react";
import toast from "react-hot-toast";
import {
  clearWebhookLogs,
  deleteWebhookLog,
  listWebhookLogs,
} from "@/apis/webhook-logs";
import { EmptyState } from "@/components/empty-state";
import { JsonViewer } from "@/components/json-viewer";
import { PaginationFooter } from "@/components/pagination-footer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { formatTaipeiDateTime } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import type {
  WebhookLogEntry,
  WebhookLogsPage,
} from "@/types/responses/webhook-logs";

const PAGE_SIZE = 50;

const EMPTY_PAGE: WebhookLogsPage = {
  items: [],
  total: 0,
  limit: PAGE_SIZE,
  offset: 0,
};

function summarizeBody(body: string | null): string {
  if (!body) return "—";
  try {
    const parsed = JSON.parse(body) as {
      notifications?: Array<{ type?: string; event?: { slug?: string } }>;
    };
    const notification = parsed.notifications?.[0];
    if (notification?.type && notification.event?.slug) {
      return `${notification.type} · ${notification.event.slug}`;
    }
  } catch {
    // Not JSON, or not the shape we expect — show the placeholder below.
  }
  return "—";
}

export default function WebhookLogsPage() {
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<WebhookLogsPage>(EMPTY_PAGE);
  const [isLoadingLogs, startLoadingLogs] = useTransition();
  const [isDeleting, startDeleting] = useTransition();
  const [isClearingAll, startClearingAll] = useTransition();
  const [openIds, setOpenIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    let cancelled = false;
    startLoadingLogs(async () => {
      try {
        const result = await listWebhookLogs(PAGE_SIZE, offset);
        if (!cancelled) setPage(result);
      } catch (err) {
        if (!cancelled) {
          console.error("Failed to load logs:", err);
          toast.error("Failed to load logs");
        }
      }
    });
    return () => {
      cancelled = true;
    };
  }, [offset]);

  const toggleOpen = (id: number) => {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleDelete = (id: number) => {
    startDeleting(async () => {
      try {
        await deleteWebhookLog(id);
        setPage(await listWebhookLogs(PAGE_SIZE, offset));
      } catch (err) {
        console.error("Failed to delete log:", err);
        toast.error("Failed to delete log");
      }
    });
  };

  const handleClearAll = () => {
    if (
      !window.confirm(
        `Clear ALL ${page.total} webhook logs? This cannot be undone.`,
      )
    ) {
      return;
    }
    startClearingAll(async () => {
      try {
        await clearWebhookLogs();
        setOffset(0);
        setPage(await listWebhookLogs(PAGE_SIZE, 0));
      } catch (err) {
        console.error("Failed to clear logs:", err);
        toast.error("Failed to clear logs");
      }
    });
  };

  return (
    <>
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-3xl font-semibold">Webhook Logs</h1>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-destructive hover:text-destructive"
          onClick={handleClearAll}
          disabled={isClearingAll}
        >
          Clear all
        </Button>
      </div>
      {isLoadingLogs && (
        <p className="mt-4 text-base text-muted-foreground">Loading…</p>
      )}
      {!isLoadingLogs && page.total === 0 && (
        <div className="mt-6">
          <EmptyState
            icon={Inbox}
            title="No webhook events yet"
            description="Registration and cancellation webhooks from KKTIX will show up here."
          />
        </div>
      )}
      {!isLoadingLogs && page.total > 0 && (
        <>
          <div className="mt-6 overflow-hidden rounded-lg border border-border bg-card">
            <div className="hidden items-center gap-3 border-b border-border px-4 py-2.5 text-xs text-muted-foreground tablet:grid tablet:grid-cols-[2rem_4rem_9rem_5rem_6rem_1fr_auto]">
              <span />
              <span>ID</span>
              <span>Created</span>
              <span>Method</span>
              <span>Channel</span>
              <span>Body</span>
              <span />
            </div>
            {page.items.map((item: WebhookLogEntry) => {
              const isOpen = openIds.has(item.id);
              return (
                <Collapsible
                  key={item.id}
                  open={isOpen}
                  onOpenChange={() => toggleOpen(item.id)}
                  className="border-b border-border last:border-b-0"
                >
                  {/* Below `tablet:`, columns don't fit a single row — stack
                      each field as its own labeled line instead. */}
                  <div className="flex flex-col gap-2 p-4 tablet:hidden">
                    <div className="flex items-center justify-between">
                      <CollapsibleTrigger
                        aria-label={
                          isOpen ? "Collapse details" : "Expand details"
                        }
                        className="flex items-center gap-2 text-muted-foreground transition-colors hover:text-foreground"
                      >
                        <ChevronRight
                          className={cn(
                            "size-4 transition-transform",
                            isOpen && "rotate-90",
                          )}
                        />
                        <span className="text-sm font-medium text-foreground">
                          #{item.id}
                        </span>
                      </CollapsibleTrigger>
                      <Badge className="w-fit rounded bg-chart-3/15 px-2 py-0.5 font-mono text-xs text-chart-3">
                        {item.method}
                      </Badge>
                    </div>
                    <div className="flex flex-col gap-0.5">
                      <span className="text-xs text-muted-foreground">
                        Created
                      </span>
                      <span className="text-sm text-muted-foreground">
                        {formatTaipeiDateTime(item.created_at)}
                      </span>
                    </div>
                    <div className="flex flex-col gap-0.5">
                      <span className="text-xs text-muted-foreground">
                        Channel
                      </span>
                      <span className="text-sm text-foreground">
                        {item.channel ?? "—"}
                      </span>
                    </div>
                    <div className="flex flex-col gap-0.5">
                      <span className="text-xs text-muted-foreground">
                        Body
                      </span>
                      <span className="text-sm break-words text-muted-foreground">
                        {summarizeBody(item.body)}
                      </span>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="self-end text-destructive hover:text-destructive"
                      onClick={() => handleDelete(item.id)}
                      disabled={isDeleting}
                    >
                      Delete
                    </Button>
                  </div>
                  <div className="hidden items-center gap-3 px-4 py-2.5 text-sm tablet:grid tablet:grid-cols-[2rem_4rem_9rem_5rem_6rem_1fr_auto]">
                    <CollapsibleTrigger
                      aria-label={
                        isOpen ? "Collapse details" : "Expand details"
                      }
                      className="flex items-center justify-center rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                    >
                      <ChevronRight
                        className={cn(
                          "size-4 transition-transform",
                          isOpen && "rotate-90",
                        )}
                      />
                    </CollapsibleTrigger>
                    <span className="text-muted-foreground">{item.id}</span>
                    <span className="text-muted-foreground">
                      {formatTaipeiDateTime(item.created_at)}
                    </span>
                    <Badge className="w-fit rounded bg-chart-3/15 px-2 py-0.5 font-mono text-xs text-chart-3">
                      {item.method}
                    </Badge>
                    <span className="text-foreground">
                      {item.channel ?? "—"}
                    </span>
                    <span className="min-w-0 break-words text-muted-foreground">
                      {summarizeBody(item.body)}
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => handleDelete(item.id)}
                      disabled={isDeleting}
                    >
                      Delete
                    </Button>
                  </div>
                  <CollapsibleContent>
                    <div className="flex flex-col gap-4 border-t border-border p-4">
                      <div>
                        <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                          Headers
                        </p>
                        <JsonViewer value={item.headers} />
                      </div>
                      <div>
                        <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                          Body
                        </p>
                        {item.body ? (
                          <JsonViewer value={item.body} />
                        ) : (
                          <p className="text-sm text-muted-foreground">
                            No body.
                          </p>
                        )}
                      </div>
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              );
            })}
          </div>
          <div className="mt-4">
            <PaginationFooter
              offset={offset}
              limit={PAGE_SIZE}
              total={page.total}
              onOffsetChange={setOffset}
            />
          </div>
        </>
      )}
    </>
  );
}
