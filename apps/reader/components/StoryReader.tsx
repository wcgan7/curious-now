"use client";

import { useMemo, useState } from "react";

import type {
  ExplanationDepth,
  SourceLink,
  StoryDetail,
} from "@/lib/types";

type Orientation = "glance" | "explain";

const orientationMeta: Record<Orientation, { name: string; hint: string }> = {
  glance: { name: "Glance", hint: "New to this" },
  explain: { name: "Explain", hint: "Know the field" },
};

const roleNames: Record<SourceLink["sourceRole"], string> = {
  primary_research: "Primary research",
  journalism: "Independent reporting",
  lab_announcement: "Lab announcement",
  institutional: "Institution",
  government: "Government",
  press_release: "Press release",
  discovery: "Discovery source",
};

function formatDate(value: string | null): string | null {
  if (!value) {
    return null;
  }
  return new Intl.DateTimeFormat("en", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(value));
}

function estimateMinutes(text: string | null | undefined): number | null {
  if (!text) {
    return null;
  }
  const words = text.trim().split(/\s+/).length;
  return Math.max(1, Math.round(words / 220));
}

function ExplanationBody({ plainText }: { plainText: string | null | undefined }) {
  if (!plainText) {
    return (
      <p>This explanation is structured but has no plain-text rendering yet.</p>
    );
  }
  return (
    <div className="explanationText">
      {plainText
        .split("\n")
        .filter(Boolean)
        .map((paragraph) => (
          <p key={paragraph}>{paragraph}</p>
        ))}
    </div>
  );
}

export function StoryReader({
  story,
  initialView,
}: {
  story: StoryDetail;
  initialView?: string;
}) {
  const orientations = story.availableDepths.filter(
    (depth): depth is Orientation => depth !== "technical",
  );
  const hasTechnical = story.availableDepths.includes("technical");
  const defaultOrientation: Orientation | null = orientations.includes("glance")
    ? "glance"
    : (orientations[0] ?? null);

  const [view, setView] = useState<ExplanationDepth | null>(() => {
    if (initialView === "technical" && hasTechnical) {
      return "technical";
    }
    if (
      (initialView === "glance" || initialView === "explain") &&
      orientations.includes(initialView)
    ) {
      return initialView;
    }
    return defaultOrientation ?? (hasTechnical ? "technical" : null);
  });

  const selectView = (next: ExplanationDepth) => {
    setView(next);
    const url = new URL(window.location.href);
    url.searchParams.set("view", next);
    window.history.replaceState(null, "", url);
  };

  const activeExplanation = useMemo(
    () => story.explanations.find((value) => value.depth === view),
    [view, story.explanations],
  );
  const technical = story.explanations.find(
    (value) => value.depth === "technical",
  );
  const technicalMinutes = estimateMinutes(technical?.plainText);
  const technicalLabel =
    technicalMinutes === null
      ? "Technical walkthrough"
      : `Technical walkthrough · ${technicalMinutes} min`;

  return (
    <>
      <header className="storyHeader">
        <div className="storyMode">
          <span
            className={
              story.mode === "enriched"
                ? "statusDot statusDot--ready"
                : "statusDot"
            }
            aria-hidden="true"
          />
          {story.mode === "enriched"
            ? "Evidence-grounded explanation"
            : "Sources available · explanation pending"}
        </div>
        <h1>{story.title}</h1>
        <div className="storyHeaderMeta">
          <time dateTime={story.publishedAt}>
            {formatDate(story.publishedAt)}
          </time>
          <span>{story.sources.length} source{story.sources.length === 1 ? "" : "s"}</span>
        </div>
      </header>

      <div className="storyGrid">
        <div className="storyMain">
          {view === "technical" && technical ? (
            <>
              <div className="techBar">
                {defaultOrientation ? (
                  <button
                    onClick={() => selectView(defaultOrientation)}
                    type="button"
                  >
                    <span aria-hidden="true">←</span> Back to{" "}
                    {orientationMeta[defaultOrientation].name}
                  </button>
                ) : (
                  <span />
                )}
                <span className="techLabel">{technicalLabel}</span>
              </div>
              <section className="explanationPanel">
                <p className="sectionKicker">Technical · Investigate the work</p>
                <ExplanationBody plainText={technical.plainText} />
              </section>
            </>
          ) : orientations.length ? (
            <>
              <div
                aria-label="Orientation"
                className="depthSelector"
                role="tablist"
              >
                {orientations.map((value) => (
                  <button
                    aria-selected={view === value}
                    className={view === value ? "active" : ""}
                    key={value}
                    onClick={() => selectView(value)}
                    role="tab"
                    type="button"
                  >
                    <span>{orientationMeta[value].name}</span>
                    <span className="tabHint">{orientationMeta[value].hint}</span>
                  </button>
                ))}
              </div>
              <section className="explanationPanel">
                <p className="sectionKicker">
                  {view === "glance" || view === "explain"
                    ? `${orientationMeta[view].name} · ${orientationMeta[view].hint}`
                    : ""}
                </p>
                <ExplanationBody plainText={activeExplanation?.plainText} />
              </section>
              {hasTechnical ? (
                <aside className="goDeeper">
                  <div>
                    <p className="sectionKicker">
                      Want to investigate the actual work?
                    </p>
                    <h2>{technicalLabel}</h2>
                    <p>Methods, experiments, results, and limitations</p>
                  </div>
                  <button
                    className="primaryButton"
                    onClick={() => selectView("technical")}
                    type="button"
                  >
                    Go deeper →
                  </button>
                </aside>
              ) : null}
            </>
          ) : (
            <section className="pendingPanel">
              <p className="sectionKicker">Sources available</p>
              <h2>A grounded explanation is not available yet.</h2>
              <p>
                Read the original sources on the shelf, or return later once the
                evidence has been processed.
              </p>
            </section>
          )}

        </div>

        <aside className="evidenceShelf">
          <p className="sectionKicker">Source shelf</p>
          <h2>Read the originals</h2>
          <div className="sourceList">
            {story.sources.map((source, index) => (
              <a
                className="sourceItem"
                href={source.url}
                key={source.itemId}
                rel="noreferrer"
                target="_blank"
              >
                <span className="sourceNumber">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <span className="sourceType">{roleNames[source.sourceRole]}</span>
                  <h3>{source.title}</h3>
                  <p>
                    {source.sourceName}
                    {formatDate(source.publishedAt)
                      ? ` · ${formatDate(source.publishedAt)}`
                      : ""}
                  </p>
                </div>
                <span aria-hidden="true">↗</span>
              </a>
            ))}
          </div>

          {story.concepts.length ? (
            <div className="conceptShelf">
              <p className="sectionKicker">Useful prerequisites</p>
              <div>
                {story.concepts.map((concept) => (
                  <span key={concept.slug}>{concept.name}</span>
                ))}
              </div>
            </div>
          ) : null}
        </aside>
      </div>
    </>
  );
}
