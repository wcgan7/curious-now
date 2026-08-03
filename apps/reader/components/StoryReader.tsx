"use client";

import { useMemo, useState } from "react";

import { citedWorkUrl, groupLineage, relationVerb } from "@/lib/lineage";
import { reviewBadge, vettingSource } from "@/lib/provenance";
import type {
  ExplanationDepth,
  SourceLink,
  StoryDetail,
} from "@/lib/types";

type Orientation = "glance" | "explain";

// Reader-facing names only; the layers are `glance` and `explain` everywhere
// else. "Summary" was considered and rejected: this layer carries ONE idea, not
// coverage, and promising a summary invites a reader to feel short-changed by
// the seventy words that replaced a compressed abstract.
const orientationMeta: Record<Orientation, { name: string; hint: string }> = {
  glance: { name: "The idea", hint: "New to this" },
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

type TechnicalSection = { heading: string; text: string; html?: string };
type TechnicalCitation = { label: string; used_for: string };

function technicalSections(content: Record<string, unknown>): TechnicalSection[] {
  const raw = content?.sections;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .filter(
      (s): s is TechnicalSection =>
        typeof s === "object" &&
        s !== null &&
        typeof (s as TechnicalSection).heading === "string" &&
        typeof (s as TechnicalSection).text === "string",
    )
    .filter((s) => s.text.trim().length > 0);
}

function technicalCitations(content: Record<string, unknown>): TechnicalCitation[] {
  const raw = content?.citations;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter(
    (c): c is TechnicalCitation =>
      typeof c === "object" &&
      c !== null &&
      typeof (c as TechnicalCitation).label === "string",
  );
}

// The walkthrough's headings are the order in which the work is inspected —
// problem, approach, evidence, results, limitations — so they are the reader's
// map through it. Flattening them into one column, which is what this did
// before, throws that away and leaves several thousand words undifferentiated.
function TechnicalBody({
  sections,
  plainText,
  html,
}: {
  sections: TechnicalSection[];
  plainText: string | null | undefined;
  html?: string | null;
}) {
  if (!sections.length) {
    return <ExplanationBody html={html} plainText={plainText} />;
  }
  return (
    <div className="technicalBody">
      {sections.map((section) => (
        <section className="technicalSection" key={section.heading}>
          <h3>{section.heading}</h3>
          <div className="explanationText">
            {section.text
              .split("\n")
              .filter(Boolean)
              .map((paragraph, index) => (
                <Prose
                  html={section.html?.split("\n").filter(Boolean)[index]}
                  key={paragraph}
                  text={paragraph}
                />
              ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function Prose({ html, text }: { html?: string | null; text: string }) {
  // The html is produced by lib/math on the server: prose escaped, formulas
  // typeset by KaTeX with trust disabled. Where none was produced the plain
  // text is rendered as text, never as markup.
  return html ? (
    <p dangerouslySetInnerHTML={{ __html: html }} />
  ) : (
    <p>{text}</p>
  );
}

function ExplanationBody({
  plainText,
  html,
}: {
  plainText: string | null | undefined;
  html?: string | null;
}) {
  if (!plainText) {
    return (
      <p>This explanation is structured but has no plain-text rendering yet.</p>
    );
  }
  const paragraphs = plainText.split("\n").filter(Boolean);
  const rendered = html ? html.split("\n").filter(Boolean) : null;
  return (
    <div className="explanationText">
      {paragraphs
        .map((paragraph, index) => (
          <Prose html={rendered?.[index]} key={paragraph} text={paragraph} />
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

  // Whether the work was reviewed belongs here as much as on the card. A reader
  // arriving from search or a shared link never saw the card, and "preprint" is
  // the single most load-bearing fact about how much weight to give a result.
  const vettingFrom = vettingSource(story.sources);
  const vetting = vettingFrom ? reviewBadge(vettingFrom) : undefined;

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
          {vetting ? <span className="reviewBadge">{vetting}</span> : null}
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
                <TechnicalBody
                  html={technical.html}
                  plainText={technical.plainText}
                  sections={technicalSections(technical.content)}
                />
                {technicalCitations(technical.content).length ? (
                  <div className="technicalCitations">
                    <p className="sectionKicker">Drawn from</p>
                    <ul>
                      {technicalCitations(technical.content).map((citation) => (
                        <li key={citation.label}>
                          <strong>{citation.label}</strong>
                          {citation.used_for ? ` — ${citation.used_for}` : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
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
                <ExplanationBody
                  html={activeExplanation?.html}
                  plainText={activeExplanation?.plainText}
                />
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

          {/* Lineage sits under the explanation, not in the rail: the quote is
              the whole point of it and a narrow column cannot carry a sentence.
              Withheld at "The idea", where someone new to the field is being
              given one idea and does not need the paper's citation history. */}
          {view !== "glance" && story.lineage.length > 0 ? (
            <section className="lineage">
              <p className="sectionKicker">What this paper builds on</p>
              <h2>Its own sources, and why</h2>
              <p className="lineageNote">
                Taken from the paper itself. Each line quotes the sentence that
                establishes the relationship.
              </p>
              <ul className="lineageList">
                {groupLineage(story.lineage).map((statement) => (
                  <li
                    className="lineageItem"
                    key={`${statement.relation}-${statement.quote}`}
                  >
                    <span
                      className={`lineageRelation lineageRelation--${statement.relation}`}
                    >
                      {relationVerb[statement.relation]}
                    </span>
                    <div className="lineageBody">
                      <ul className="lineageWorks">
                        {statement.works.map((work) => {
                          const href = citedWorkUrl(work);
                          return (
                            <li key={work.title}>
                              {href ? (
                                <a
                                  className="lineageTitle"
                                  href={href}
                                  rel="noreferrer"
                                >
                                  {work.title}
                                </a>
                              ) : (
                                <span className="lineageTitle">{work.title}</span>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                      <p className="lineageQuote">{statement.quote}</p>
                    </div>
                  </li>
                ))}
              </ul>
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
