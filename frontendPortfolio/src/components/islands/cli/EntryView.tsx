import { memo, useEffect, useState } from "react";
import type { Block } from "../../../lib/cli/blocks";
import type { CliData } from "../../../lib/cli/data";
import { describe, withKeys } from "../../../lib/cli/keys";
import { stepCall } from "../../../lib/cli/menu";
import type { Entry } from "../../../lib/cli/terminalState";
import { BlockView } from "./BlockView";
import { Markdown } from "./Markdown";

const SPINNER = ["·", "✢", "✳", "✶", "✻", "✽", "✻", "✶", "✳", "✢"] as const;
const VERBS = ["Pondering", "Recalling", "Cross-checking", "Synthesizing", "Composing"] as const;
const FRAME_MS = 110;
const VERB_MS = 2400;

type AnswerEntry = Extract<Entry, { kind: "answer" }>;

function Spinner({
  startedAt,
  chars,
  animated,
}: {
  readonly startedAt: number;
  readonly chars: number;
  readonly animated: boolean;
}) {
  const [now, setNow] = useState(startedAt);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), animated ? FRAME_MS : 1000);
    return () => window.clearInterval(timer);
  }, [animated]);
  const elapsed = Math.max(0, now - startedAt);
  const frame = SPINNER[Math.floor(elapsed / FRAME_MS) % SPINNER.length];
  const verb = VERBS[Math.floor(elapsed / VERB_MS) % VERBS.length];
  return (
    <p className="term-bullet mt-[0.9em] text-accent" role="status">
      <span aria-hidden="true">{animated ? frame : "✻"}</span>
      <span>
        {verb}…{" "}
        <span className="text-faint">
          ({Math.floor(elapsed / 1000)}s{chars > 0 ? ` · ${chars} chars` : ""} · esc to interrupt)
        </span>
      </span>
    </p>
  );
}

function Welcome({ data, summary }: { readonly data: CliData; readonly summary: string }) {
  const slug = data.ownerName.toLowerCase().replace(/\s+/g, "-");
  return (
    <section aria-label="Welcome">
      <div className="inline-block max-w-full rounded-[0.55em] border border-accent/70 px-[1.5ch] py-[0.5em]">
        <p>
          <span className="text-accent" aria-hidden="true">
            ✻{" "}
          </span>
          Welcome to <span className="font-semibold">{data.ownerName}</span>'s Portfolio Agent!
        </p>
        <p className="mt-[0.6em] pl-[2ch] text-faint">/help for help, /go-back to return</p>
        <p className="hidden pl-[2ch] text-faint sm:block">cwd: ~/portfolio/{slug}</p>
        <p className="pl-[2ch] text-faint">{summary}</p>
      </div>
      <p className="mt-[1.2em] text-muted">Tips for getting started:</p>
      <ol className="term-tips mt-[0.4em] text-muted">
        <li className="term-bullet">
          <span className="text-faint">1.</span>
          <span>
            <span className="text-text">/whoami</span> for the one-screen summary
          </span>
        </li>
        <li className="term-bullet">
          <span className="text-faint">2.</span>
          <span>
            <span className="text-text">/projects relay</span> to dig into a project
          </span>
        </li>
        <li className="term-bullet">
          <span className="text-faint">3.</span>
          <span>Or just ask: what is his strongest backend project?</span>
        </li>
      </ol>
      <p className="mt-[0.8em] text-faint">
        ※ Tip: press <span className="text-muted">/</span> for every command
        <span className="hover-only">
          , <span className="text-muted">Tab</span> to complete
        </span>
      </p>
    </section>
  );
}

function OutputView({ blocks }: { readonly blocks: readonly Block[] }) {
  const [first, ...rest] = blocks;
  const titled = first?.kind === "heading";
  const body = titled ? rest : blocks;
  const failed = first?.kind === "error";
  return (
    <div className="term-entry">
      {titled && (
        <p className="term-bullet">
          <span aria-hidden="true">⏺</span>
          <span>
            <span className="font-semibold">{first.text}</span>
            {first.meta !== undefined && <span className="text-faint"> ({first.meta})</span>}
          </span>
        </p>
      )}
      {!titled && (
        <p className="term-bullet">
          <span aria-hidden="true" className={failed ? "text-danger" : "text-muted"}>
            ⏺
          </span>
          <span className="text-faint">{failed ? "Command failed" : "Done"}</span>
        </p>
      )}
      {body.length > 0 && (
        <div className="term-body grid gap-[0.35em]">
          {withKeys(body, describe).map(([key, block]) => (
            <BlockView key={key} block={block} />
          ))}
        </div>
      )}
    </div>
  );
}

function answerMeta(entry: AnswerEntry): string {
  if (entry.note !== null) {
    return entry.note;
  }
  if (entry.finishedAt === null) {
    return "";
  }
  const recalled = entry.steps.some((step) => step.startsWith("Recalling"));
  if (recalled) {
    return "0 AI calls · recalled";
  }
  const checked = entry.steps.some((step) => step.startsWith("Checking"));
  return checked ? "0 AI calls" : `1 AI call · ${((entry.finishedAt - entry.startedAt) / 1000).toFixed(1)}s`;
}

function PlanView({ plan }: { readonly plan: NonNullable<AnswerEntry["plan"]> }) {
  return (
    <div className="mt-[0.6em]" data-plan>
      <p className="term-bullet">
        <span aria-hidden="true" className="text-plan">
          ⏺
        </span>
        <span>
          <span className="font-semibold">Plan</span>
          {plan.summary !== "" && <span className="text-muted"> · {plan.summary}</span>}
        </span>
      </p>
      <ol className="term-body">
        {withKeys(plan.steps, describe).map(([key, step], index) => (
          <li key={key} className="term-bullet term-tips">
            <span className="text-faint">{index + 1}.</span>
            <span>
              <span className="font-semibold">{step.command}</span>
              {step.reason !== "" && <span className="text-faint"> · {step.reason}</span>}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function AnswerView({
  entry,
  showCost,
  animated,
}: {
  readonly entry: AnswerEntry;
  readonly showCost: boolean;
  readonly animated: boolean;
}) {
  const isStreaming = entry.status === "streaming";
  const fullMeta = answerMeta(entry);
  const meta = showCost || entry.note !== null ? fullMeta : "";
  const hasText = entry.text !== "" || entry.plan !== null;
  return (
    <div className="term-entry">
      {entry.steps.map((step) => {
        const call = stepCall(step);
        return (
          <div key={step}>
            <p className="term-bullet">
              <span aria-hidden="true" className={hasText || !isStreaming ? "text-success" : "text-muted"}>
                ⏺
              </span>
              <span>
                <span className="font-semibold">{call.name}</span>
                {call.argument !== "" && <span className="text-muted">({call.argument})</span>}
              </span>
            </p>
            <p className="term-body text-faint">{hasText || !isStreaming ? "done" : "running…"}</p>
          </div>
        );
      })}
      {entry.plan !== null ? (
        <PlanView plan={entry.plan} />
      ) : (
        entry.text !== "" && (
          <div className="term-bullet mt-[0.6em]">
            <span aria-hidden="true">⏺</span>
            <Markdown text={entry.text} />
          </div>
        )
      )}
      {isStreaming && <Spinner startedAt={entry.startedAt} chars={entry.text.length} animated={animated} />}
      {meta !== "" && (
        <p className={`term-body mt-[0.2em] ${entry.status === "failed" ? "text-danger" : "text-faint"}`}>{meta}</p>
      )}
    </div>
  );
}

interface EntryViewProps {
  readonly entry: Entry;
  readonly data: CliData;
  readonly summary: string;
  readonly showCost: boolean;
  readonly animated: boolean;
}

export const EntryView = memo(function EntryView({ entry, data, summary, showCost, animated }: EntryViewProps) {
  switch (entry.kind) {
    case "welcome":
      return <Welcome data={data} summary={summary} />;
    case "input":
      return (
        <p className="term-echo">
          <span aria-hidden="true">&gt; </span>
          <span className="sr-only">You typed: </span>
          {entry.text}
        </p>
      );
    case "output":
      return <OutputView blocks={entry.blocks} />;
    case "answer":
      return <AnswerView entry={entry} showCost={showCost} animated={animated} />;
  }
});
