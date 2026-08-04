"use client";

import { useRef, useState } from "react";

import { StoryImage } from "@/components/StoryImage";
import { sourceLinkLabel, vettingSource } from "@/lib/provenance";
import type { Explanation, ExplanationDepth, StoryDetail } from "@/lib/types";

const RUNGS: { depth: ExplanationDepth; label: string }[] = [
  { depth: "glance", label: "The idea" },
  { depth: "explain", label: "Explain" },
  { depth: "technical", label: "Technical" },
];

/** The story page.
 *
 * The order is settled: picture, headline, the explanation at a chosen depth,
 * what it rests on, what it builds on. What the page that shipped had wrong was
 * not a matter of taste — the source shelf sat under the headline, so the first
 * thing after the title told the reader to go elsewhere; Technical was a
 * promotional box at the foot rather than a rung, so the product's whole claim
 * rendered as two depths and an advertisement; and it was set in a serif
 * nothing else in the reader uses.
 *
 * The depth control is pinned. It costs 50px of permanent chrome and buys the
 * ability to change depth from anywhere in a 7,000-word walkthrough, which
 * matters because the depths are wildly different lengths.
 */
export function StoryDraft({ story }: { story: StoryDetail }) {
  const available = new Set(story.availableDepths);
  // Only the rungs this story earned. A greyed-out control invites a tap that
  // does nothing, and there is nothing a reader can do about a paper that
  // carried no walkthrough.
  const rungs = RUNGS.filter((rung) => available.has(rung.depth));
  const [depth, setDepth] = useState<ExplanationDepth>(
    rungs[0]?.depth ?? "glance",
  );
  const bar = useRef<HTMLDivElement>(null);
  const source = vettingSource(story.sources);
  const chosen = story.explanations.find((entry) => entry.depth === depth);
  /** Nothing goes below the prose, and this is the third section to go.
   *
   * Two were cut as duplication: the paper's own results and its own
   * limitations, both already said by the ladder — the technical rung's
   * headings include 'results', 'evidence' and 'limitations', and 63% of
   * glances and 76% of explains state a limit in the prose without being asked.
   *
   * The third, lineage, was kept one round longer on the argument that a link
   * to a cited paper is navigation rather than explanation, and that no rung
   * offers it. Reading what it actually rendered ended that. Papers do not
   * write the sentence "this agrees with X" for readers; they write it for
   * referees, inside the methods —
   *
   *   "We use the mean over all tokens: in our setting, the last token
   *    concentrates probe signal in very early layers, inconsistent with the
   *    established finding that semantic representations…"
   *   "Here, we replicate the \(5\times 5\) grid shortest path experiments of
   *    Elmachtoub and Grigas ( 2022 )"
   *
   * — so a panel of lifted citing sentences reads as a methodology section
   * because it is one. After the title and relation filters it reached 178
   * edges on 110 of 974 stories, a median of one apiece. The question it was
   * meant to answer, whether a result stands alone or fits with what else is
   * known, is answered better and 3.7× more often by the technical rung's
   * 'relation to prior work' section: 412 stories, in prose written for a
   * reader rather than lifted from one written for a referee.
   *
   * The citation graph keeps earning its place upstream. It is how a story
   * knows what work it descends from; it is not something to print.
   */

  return (
    <article className="draft">
      {/* First, above the headline, which is where v1 had it and where every
          publication that runs pictures puts them. A reader who arrived by
          tapping a card saw this picture on the card; anywhere lower and it
          reads as having gone missing on the way. */}
      <StoryImage source={source} title={story.title} />

      <header className="draftHead">
        <p className="draftMeta">
          {/* The publisher's name is the link. It costs no row, because the
              word was already on the page: a reader was reading "Nature", and
              now that word is the way to Nature. A filled pill on its own row
              was tried first and read as an interruption — the loudest object
              on the page, between the headline and the explanation, telling
              someone who had just arrived to leave. */}
          {source ? (
            <a
              className="draftByline"
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
        <h1 className="draftTitle">{story.title}</h1>
      </header>

      <div className="draftRungs draftRungs--pinned" ref={bar} role="tablist">
        {rungs.map((rung) => (
          <button
            aria-selected={depth === rung.depth}
            className={depth === rung.depth ? "draftRung draftRung--on" : "draftRung"}
            key={rung.depth}
            onClick={() => {
              setDepth(rung.depth);
              // The depths are wildly different lengths — the idea runs
              // 1,800px and the walkthrough 7,000 — so changing depth from
              // halfway down would leave a reader past the end of a shorter
              // text, staring at the sources. Every change starts the new text
              // at its beginning.
              bar.current?.scrollIntoView({ block: "start" });
            }}
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

          It shows the source's own title as well as ours. 629 of the corpus's
          titles were rewritten because the original was unreadable without a
          doctorate, which is right for a feed and leaves a reader unable to
          recognise the paper when they arrive at it. */}
      {story.sources.map((entry) => (
        <aside className="draftOriginal" key={entry.itemId}>
          <p className="draftOriginalName">{entry.sourceName}</p>
          <p className="draftOriginalTitle">{entry.title}</p>
          <a
            className="draftSourceCta"
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
 * The technical walkthrough arrives already divided — problem, approach,
 * evidence, results, limitations — and those headings are the reader's map
 * through several thousand words. Flattening them into one column throws the
 * map away.
 */
function Body({ explanation }: { explanation?: Explanation }) {
  if (!explanation) {
    return <p className="draftProse draftProse--none">Not written for this story.</p>;
  }
  const sections = sectionsOf(explanation.content);
  if (sections.length > 0) {
    return (
      <div className="draftProse">
        {sections.map((section) => (
          <section key={section.heading}>
            <h2 className="draftSectionHead">{section.heading}</h2>
            <Paragraphs html={section.html} text={section.text} />
          </section>
        ))}
      </div>
    );
  }
  return (
    <div className="draftProse">
      <Paragraphs html={explanation.html} text={explanation.plainText} />
    </div>
  );
}

function Paragraphs({ html, text }: { html?: string | null; text?: string | null }) {
  if (!text) {
    return <p className="draftProse--none">Not written for this story.</p>;
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
