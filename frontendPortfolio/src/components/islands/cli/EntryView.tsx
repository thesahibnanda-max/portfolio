import { memo, useEffect, useState } from "react";
import type { CliData } from "../../../lib/cli/data";
import { describe, withKeys } from "../../../lib/cli/keys";
import type { Entry } from "../../../lib/cli/terminalState";
import { BlockView } from "./BlockView";
import { Markdown } from "./Markdown";

const SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"] as const;
const SPINNER_MS = 80;
const builtFormat = new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" });

function Spinner({ startedAt, label }: { readonly startedAt: number; readonly label: string }) {
  const [now, setNow] = useState(startedAt);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), SPINNER_MS);
    return () => window.clearInterval(timer);
  }, []);
  const frame = SPINNER[Math.floor(now / SPINNER_MS) % SPINNER.length];
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000));
  return (
    <p className="text-accent" role="status">
      <span aria-hidden="true" className="motion-reduce:hidden">
        {frame}{" "}
      </span>
      {label}
      <span className="text-faint"> ({seconds}s · esc to interrupt)</span>
    </p>
  );
}

function Welcome({ data }: { readonly data: CliData }) {
  const current = data.profile.experience.find((job) => job.end_date === "Present") ?? data.profile.experience[0];
  return (
    <section aria-label="Welcome" className="mb-5">
      <div className="max-w-2xl rounded-xl border border-accent/40 px-4 py-3">
        <p>
          <span className="text-accent" aria-hidden="true">
            ✻{" "}
          </span>
          Welcome to <span className="font-semibold">{data.ownerName}</span>'s Portfolio Agent
        </p>
        <p className="mt-2 text-faint">/help for commands · Tab to complete · ask anything in plain English</p>
        <p className="text-faint">
          cwd: ~/portfolio/{data.ownerName.toLowerCase().replace(/\s+/g, "-")} · data as of{" "}
          {builtFormat.format(new Date(data.builtAt))}
        </p>
      </div>
      <p className="mt-5 text-3xl leading-tight font-semibold tracking-tight sm:text-5xl" aria-hidden="true">
        <span className="text-faint">&gt; </span>
        {data.ownerName.split(" ")[0]}
        <span className="text-accent">.</span>
        <span className="text-muted">agent</span>
        <span className="caret" />
      </p>
      {current !== undefined && (
        <p className="mt-2 text-muted">
          {current.title} at <span className="text-text">{current.company}</span>
        </p>
      )}
      <p className="mt-4 text-faint">Tips for getting started:</p>
      <ol className="list-decimal pl-5 text-muted marker:text-faint">
        <li>
          <span className="text-text">/whoami</span> for the one-screen summary
        </li>
        <li>
          <span className="text-text">/projects relay</span> to dig into a project
        </li>
        <li>Or just ask: what is his strongest backend project?</li>
      </ol>
    </section>
  );
}

function answerMeta(entry: Extract<Entry, { kind: "answer" }>): string {
  if (entry.note !== null) {
    return entry.note;
  }
  if (entry.finishedAt === null) {
    return "";
  }
  const seconds = ((entry.finishedAt - entry.startedAt) / 1000).toFixed(1);
  const recalled = entry.steps.some((step) => step.startsWith("Recalling"));
  return recalled ? "0 AI calls · cached answer" : `answered in ${seconds}s`;
}

export const EntryView = memo(function EntryView({ entry, data }: { readonly entry: Entry; readonly data: CliData }) {
  switch (entry.kind) {
    case "welcome":
      return <Welcome data={data} />;
    case "input":
      return (
        <p className="term-entry mt-4 whitespace-pre-wrap break-words text-text first:mt-0">
          <span className="text-accent" aria-hidden="true">
            ❯{" "}
          </span>
          <span className="sr-only">You typed: </span>
          {entry.text}
        </p>
      );
    case "output":
      return (
        <div className="term-entry term-gutter mt-1 grid gap-1">
          {withKeys(entry.blocks, describe).map(([key, block]) => (
            <BlockView key={key} block={block} />
          ))}
        </div>
      );
    case "answer": {
      const isStreaming = entry.status === "streaming";
      const meta = answerMeta(entry);
      return (
        <div className="term-entry term-gutter mt-1 grid gap-1">
          {withKeys(entry.steps, String).map(([key, step]) => (
            <p key={key} className="text-muted">
              <span className="text-success" aria-hidden="true">
                ●{" "}
              </span>
              {step}
            </p>
          ))}
          {isStreaming && entry.text === "" && (
            <Spinner
              startedAt={entry.startedAt}
              label={entry.steps.length === 0 ? "Connecting to the agent…" : "Thinking…"}
            />
          )}
          {entry.text !== "" && <Markdown text={entry.text} />}
          {isStreaming && entry.text !== "" && <span className="caret" aria-hidden="true" />}
          {meta !== "" && (
            <p className={entry.status === "failed" ? "text-danger" : "text-faint"}>
              {entry.status === "failed" ? "✗ " : ""}
              {meta}
            </p>
          )}
        </div>
      );
    }
  }
});
