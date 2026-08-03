import { FeedStream } from "@/components/FeedStream";
import { getFeedPage } from "@/lib/data";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const initialPage = await getFeedPage();

  return (
    <>
      <section className="hero">
        <div className="heroInner">
          <p className="eyebrow">
            <span aria-hidden="true" />
            Continuously collected
          </p>
          <h1>
            A better thing
            <br />
            to <em>scroll.</em>
          </h1>
          <p className="heroCopy">
            New research, careful science reporting, and frontier-lab work—
            grouped into stories and explained at the depth you need.
          </p>
          <div className="depthLegend" aria-label="Reading depths">
            <span>The idea</span>
            <i aria-hidden="true" />
            <span>Explain</span>
            <i aria-hidden="true" />
            <span>Technical</span>
          </div>
        </div>
      </section>

      <section className="feedSection" aria-labelledby="latest-heading">
        <div className="sectionHeading">
          <div>
            <p className="sectionKicker">The live shelf</p>
            <h2 id="latest-heading">What to read</h2>
          </div>
          <p className="sectionNote">
            No outrage score. No engagement bait. Ordered by what the work
            establishes, and how recently.
          </p>
        </div>
        <FeedStream initialPage={initialPage} />
      </section>
    </>
  );
}
