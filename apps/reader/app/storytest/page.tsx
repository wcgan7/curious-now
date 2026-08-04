import { notFound } from "next/navigation";

import { StoryDraft } from "@/components/StoryDraft";
import { getStory } from "@/lib/data";

/** The story page, while the last question is settled.
 *
 * Temporary, and deleted once the source link has a home.
 *
 * The depth control is decided — pinned, so a reader can change depth from
 * anywhere in a walkthrough that runs 7,000px — and unearned rungs are dropped
 * rather than greyed, so a two-rung story shows two.
 *
 * The link to the original is settled too, and it is in two places. At the top
 * the publisher's name is the link, which costs no row because the word was
 * already there. At the foot it is a block a reader cannot miss, which costs
 * nothing either because there is nothing after it.
 *
 * What is left varies the picture, because 21% of published stories carry a
 * photograph, 29% carry a figure from the paper, 48% carry nothing, and the
 * page has to look deliberate in all three.
 */
const LADDER = "d90d77d8-fd96-4f5d-b3ca-6e88a9be1d3a";
const FIGURE = "012e779f-653f-41b6-a785-57324f1fc2d9";
const PHOTO = "06f02bad-24d1-4bbf-913f-995d1e484eab";

export default async function StoryTest() {
  const [ladder, figure, photo] = await Promise.all([
    getStory(LADDER),
    getStory(FIGURE),
    getStory(PHOTO),
  ]);
  if (!ladder || !figure || !photo) {
    notFound();
  }

  return (
    <>
      <div className="draftRow">
        <p className="draftNote">
          The picture, in the three states it occurs in.
        </p>
        <figure className="draftCell">
          <figcaption>
            Figure · 29%
            <span>the paper&rsquo;s own, tap to open</span>
          </figcaption>
          <div className="draftFrame">
            <StoryDraft story={figure} />
          </div>
        </figure>
        <figure className="draftCell">
          <figcaption>
            Photograph · 21%
            <span>two rungs, not three greyed</span>
          </figcaption>
          <div className="draftFrame">
            <StoryDraft story={photo} />
          </div>
        </figure>
        <figure className="draftCell">
          <figcaption>
            Nothing · 48%
            <span>the most common case</span>
          </figcaption>
          <div className="draftFrame">
            <StoryDraft story={ladder} />
          </div>
        </figure>
      </div>
    </>
  );
}
