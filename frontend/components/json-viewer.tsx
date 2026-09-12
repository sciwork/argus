// Minimal JSON syntax highlighter. Deliberately hand-rolled instead of
// pulling in a full highlighting library (shiki, prismjs, ...) — JSON's
// grammar is simple enough that a single regex pass covers it, and this
// ships as part of a static-exported bundle where every dependency counts.
function highlightJson(json: string): string {
  // Escape HTML first — the JSON can contain arbitrary strings from
  // webhook payloads (ticket names, etc.), so this must not be
  // injectable before we wrap tokens in <span>s below.
  const escaped = json
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  return escaped.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\btrue\b|\bfalse\b|\bnull\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,
    (match) => {
      let className = "text-chart-3"; // number
      if (/^"/.test(match)) {
        className = /:$/.test(match) ? "text-chart-1" : "text-chart-2"; // key : string
      } else if (match === "true" || match === "false") {
        className = "text-chart-4";
      } else if (match === "null") {
        className = "text-muted-foreground";
      }
      return `<span class="${className}">${match}</span>`;
    },
  );
}

function formatJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    // Not valid JSON (or already redacted/truncated) — show it verbatim
    // rather than failing to render at all.
    return raw;
  }
}

interface JsonViewerProps {
  value: string;
}

export function JsonViewer({ value }: JsonViewerProps) {
  const formatted = formatJson(value);
  return (
    <pre className="overflow-x-auto rounded-md bg-background p-4 font-mono text-xs leading-relaxed">
      <code dangerouslySetInnerHTML={{ __html: highlightJson(formatted) }} />
    </pre>
  );
}
