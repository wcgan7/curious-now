"use client";

import { useMemo, useState } from "react";

import type {
  ExplanationDepth,
  SourceLink,
  StoryDetail,
} from "@/lib/types";

const depthNames: Record<ExplanationDepth, string> = {
  glance: "Glance",
  explain: "Explain",
  technical: "Technical",
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

export function StoryReader({ story }: { story: StoryDetail }) {
  const [depth, setDepth] = useState<ExplanationDepth | null>(
    story.availableDepths[0] ?? null,
  );
  const activeExplanation = useMemo(
    () => story.explanations.find((value) => value.depth === depth),
    [depth, story.explanations],
  );

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
          <span>{story.claims.length} grounded claim{story.claims.length === 1 ? "" : "s"}</span>
        </div>
      </header>

      <div className="storyGrid">
        <div className="storyMain">
          {story.availableDepths.length ? (
            <>
              <div className="depthSelector" role="tablist" aria-label="Reading depth">
                {story.availableDepths.map((value) => (
                  <button
                    aria-selected={depth === value}
                    className={depth === value ? "active" : ""}
                    key={value}
                    onClick={() => setDepth(value)}
                    role="tab"
                    type="button"
                  >
                    {depthNames[value]}
                  </button>
                ))}
              </div>
              <section className="explanationPanel">
                <p className="sectionKicker">{depth ? depthNames[depth] : ""}</p>
                {activeExplanation?.plainText ? (
                  <div className="explanationText">
                    {activeExplanation.plainText
                      .split("\n")
                      .filter(Boolean)
                      .map((paragraph) => (
                        <p key={paragraph}>{paragraph}</p>
                      ))}
                  </div>
                ) : (
                  <p>
                    This explanation is structured but has no plain-text rendering
                    yet.
                  </p>
                )}
              </section>
            </>
          ) : (
            <section className="pendingPanel">
              <p className="sectionKicker">Evidence first</p>
              <h2>The sources arrived before the summary.</h2>
              <p>
                Curious Now publishes useful links immediately. The explanation
                will appear only after it can be tied to a versioned evidence
                packet.
              </p>
            </section>
          )}

          {story.claims.length ? (
            <section className="claimsSection">
              <p className="sectionKicker">Claim ledger</p>
              <h2>What the evidence supports</h2>
              <ol>
                {story.claims.map((claim) => (
                  <li key={claim.id}>
                    <div>
                      <span>{claim.kind}</span>
                      <strong>{Math.round(claim.confidence * 100)}%</strong>
                    </div>
                    <p>{claim.text}</p>
                    <ul>
                      {claim.citations.map((citation) => (
                        <li key={`${claim.id}-${citation.itemId}`}>
                          <a href={citation.url} rel="noreferrer" target="_blank">
                            {citation.sourceName} ↗
                          </a>
                          {citation.excerpt ? <q>{citation.excerpt}</q> : null}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ol>
            </section>
          ) : null}
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
