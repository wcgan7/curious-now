"use client";

import { useCallback, useRef, useState } from "react";

import { StoryImage } from "@/components/StoryImage";
import { reviewBadge, sourceLinkLabel, vettingSource } from "@/lib/provenance";
import type { Explanation, ExplanationDepth, StoryDetail } from "@/lib/types";

const RUNGS: { depth: ExplanationDepth; label: string }[] = [
  { depth: "glance", label: "The idea" },
  { depth: "explain", label: "Explain" },
  { depth: "technical", label: "Technical" },
];

/**
 * A story, at whichever depth the reader asks for.
 *
 * The page this replaced put "Read the originals" directly under the headline,
 * so the first thing after the title told the reader to leave; made Technical a
 * "GO DEEPER" box at the foot rather than a rung, so a product built on three
 * depths rendered as two and an advertisement; and set the whole thing in a
 * serif nothing else in the reader uses, so arriving from the feed felt like
 * leaving the product.
 *
 * What is here instead, in order: the picture, the headline, the explanation,
 * the paper. Nothing between the prose and the way out.
 *
 * Three sections were built to sit in that gap and all three were cut. The
 * paper's own results and its own limitations both repeated the ladder — the
 * technical rung's headings already include 'results', 'evidence' and
 * 'limitations', and 63% of glances and 76% of explains state a limit without
 * being asked. A lineage panel repeated it too, and worse: papers write "this
 * agrees with X" for referees inside the methods, so lifting that sentence
 * verbatim can only produce a methodology section. It reached 110 of 974
 * stories; the technical rung's 'relation to prior work' answers the same
 * question on 412, in prose written for a reader.
 *
 * The evidence packet still earns its place, upstream. 28,759 claims, each
 * carrying the verbatim span it came from, are what the generator writes from —
 * a constraint on generation rather than a feature of a page. Showing three of
 * twenty-eight never verified the prose; it verified three arbitrary sentences
 * while looking like it verified all of it.
 */
export function StoryReader({
  initialView,
  story,
}: {
  initialView?: string;
  story: StoryDetail;
}) {
  const available = new Set(story.availableDepths);
  // Only the rungs this story earned. A greyed-out control invites a tap that
  // does nothing, and there is nothing a reader can do about a paper that
  // carried no walkthrough — 213 stories have no technical rung because their
  // source is already written for readers and has no paper to walk through.
  const rungs = RUNGS.filter((rung) => available.has(rung.depth));
  const [depth, setDepth] = useState<ExplanationDepth>(() => {
    const asked = rungs.find((rung) => rung.depth === initialView);
    return asked?.depth ?? rungs[0]?.depth ?? "glance";
  });
  const bar = useRef<HTMLDivElement>(null);
  const source = vettingSource(story.sources);
  const chosen = story.explanations.find((entry) => entry.depth === depth);

  const choose = useCallback((next: ExplanationDepth) => {
    setDepth(next);
    // The depths run 1,800px and 7,000px, so changing depth from halfway down
    // would leave a reader past the end of a shorter text, staring at the
    // source block. Every change starts the new text at its beginning.
    bar.current?.scrollIntoView({ block: "start" });
    // In the URL so a depth can be linked to and survives a reload, and
    // replaceState so moving between depths does not fill the back button
    // with a trail a reader has to walk out of.
    const url = new URL(window.location.href);
    url.searchParams.set("view", next);
    window.history.replaceState(null, "", url);
  }, []);

  return (
    <article className="article">
      {/* First, above the headline, which is where every publication that runs
          pictures puts them. A reader who arrived by tapping a card saw this
          picture on the card; anywhere lower and it reads as having gone
          missing on the way. */}
      <StoryImage source={source} title={story.title} />

      <header className="articleHead">
        <p className="articleMeta">
          {/* The publisher's name is the link. It costs no row, because the
              word was already on the page: a reader was reading "Nature", and
              now that word is the way to Nature. A filled pill on its own row
              was tried first and read as an interruption — the loudest object
              on the page, between the headline and the explanation, telling
              someone who had just arrived to leave. */}
          {source ? (
            <a
              className="articleByline"
              href={source.url}
              rel="noreferrer"
              target="_blank"
            >
              {source.sourceName}
              <span aria-hidden="true">↗</span>
            </a>
          ) : null}
          <time dateTime={story.publishedAt}>
            {new Date(story.publishedAt).toLocaleDateString("en", {
              day: "numeric",
              month: "short",
              year: "numeric",
              timeZone: "UTC",
            })}
          </time>
        </p>
        <h1 className="articleTitle">{story.title}</h1>
      </header>

      {/* Pinned, and the same height at every depth so switching rungs does
          not shift the prose under it. The active rung is underlined against
          the hairline the bar already draws, which means the control adds
          nothing to the page but a thickening of a line that was there. Three
          bordered boxes with a black fill were tried and were 20px taller and
          the only filled object in a design that has no fills. */}
      <div className="articleRungs" ref={bar} role="tablist">
        {rungs.map((rung) => (
          <button
            aria-selected={depth === rung.depth}
            className={depth === rung.depth ? "articleRung articleRung--on" : "articleRung"}
            key={rung.depth}
            onClick={() => choose(rung.depth)}
            role="tab"
            type="button"
          >
            {rung.label}
          </button>
        ))}
      </div>

      <Body explanation={chosen} />

      {/* The last thing on the page, and the loud thing.

          The byline at the top is deliberately quiet — it costs no row because
          it is a word that was already there — and quiet is missable. This is
          the other end: a reader who has finished is deciding what to do next,
          and the answer we want to give is "read the actual paper". A pill
          here interrupts nothing, because there is nothing after it.

          It names the source's own title as well as ours. 629 of the corpus's
          titles were rewritten because the original was unreadable without a
          doctorate, which is right for a feed and leaves a reader unable to
          recognise the paper when they arrive at it. */}
      {story.sources.map((entry) => (
        <aside className="articleOriginal" key={entry.itemId}>
          <p className="articleOriginalName">
            {entry.sourceName}
            {/* Whether the work was reviewed, said once, where it bears on a
                decision the reader is about to make. */}
            {reviewBadge(entry) ? <span> · {reviewBadge(entry)}</span> : null}
          </p>
          <p className="articleOriginalTitle">{entry.title}</p>
          <a
            className="articleCta"
            href={entry.url}
            rel="noreferrer"
            target="_blank"
          >
            {sourceLinkLabel(entry)}
            <span aria-hidden="true">↗</span>
          </a>
        </aside>
      ))}
    </article>
  );
}

type Section = { heading: string; text: string; html?: string };

function sectionsOf(content: Record<string, unknown> | undefined): Section[] {
  const raw = content?.sections;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter(
    (entry): entry is Section =>
      typeof entry === "object" &&
      entry !== null &&
      typeof (entry as Section).heading === "string" &&
      typeof (entry as Section).text === "string" &&
      (entry as Section).text.trim().length > 0,
  );
}

/** The prose at one depth.
 *
 * The technical walkthrough arrives already divided — orientation, problem
 * formulation, approach, evidence, results, limitations — and those headings
 * are the reader's map through several thousand words. Flattening them into one
 * column throws the map away.
 */
function Body({ explanation }: { explanation?: Explanation }) {
  if (!explanation) {
    return <p className="articleProse articleProse--none">Not written for this story.</p>;
  }
  const sections = sectionsOf(explanation.content);
  if (sections.length > 0) {
    return (
      <div className="articleProse">
        {sections.map((section) => (
          <section key={section.heading}>
            <h2 className="articleSectionHead">{section.heading}</h2>
            <Paragraphs html={section.html} text={section.text} />
          </section>
        ))}
      </div>
    );
  }
  return (
    <div className="articleProse">
      <Paragraphs html={explanation.html} text={explanation.plainText} />
    </div>
  );
}

function Paragraphs({ html, text }: { html?: string | null; text?: string | null }) {
  if (!text) {
    return <p className="articleProse--none">Not written for this story.</p>;
  }
  const paragraphs = text.split("\n").filter(Boolean);
  // Produced by lib/math on the server: prose escaped, formulas typeset by
  // KaTeX with trust disabled. Where none was produced the text is rendered as
  // text, never as markup.
  const rendered = html ? html.split("\n").filter(Boolean) : null;
  return (
    <>
      {paragraphs.map((paragraph, index) =>
        rendered?.[index] ? (
          <p dangerouslySetInnerHTML={{ __html: rendered[index] }} key={paragraph} />
        ) : (
          <p key={paragraph}>{paragraph}</p>
        ),
      )}
    </>
  );
}
