import { Button } from "@/components/ui/button";

interface PaginationFooterProps {
  offset: number;
  limit: number;
  total: number;
  onOffsetChange: (offset: number) => void;
}

/**
 * Offset/limit pagination controls: result count + Previous/Next.
 *
 * Deliberately renders nothing but the controls — how the paginated items
 * themselves are displayed (table, card list, ...) is entirely up to the
 * caller. `offset` stays owned by the caller; this component only reports
 * where to move via `onOffsetChange`.
 */
export function PaginationFooter({
  offset,
  limit,
  total,
  onOffsetChange,
}: PaginationFooterProps) {
  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd = Math.min(offset + limit, total);

  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">
        {rangeStart}–{rangeEnd} of {total}
      </span>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={offset === 0}
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
        >
          Previous
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={offset + limit >= total}
          onClick={() => onOffsetChange(offset + limit)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
