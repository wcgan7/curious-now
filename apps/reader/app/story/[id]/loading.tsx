/** What a tap on a card produces immediately.
 *
 * The story page is force-dynamic and does a database round trip, and without
 * this Next holds the feed on screen until the server answers. Locally that is
 * 10-24ms and invisible; on a slow connection it is seconds of a page that has
 * not acknowledged being tapped, which reads as a broken link — especially
 * while the feed is fetching its next page and the connection is already busy.
 *
 * It is a skeleton rather than a spinner because the shapes are known: every
 * story page opens with a meta line, a headline of one or two lines, and the
 * ladder. Matching them means the real page replaces this without moving
 * anything a reader has already started looking at.
 */
export default function LoadingStory() {
  return (
    <div aria-busy="true" className="article">
      <p className="visuallyHidden">Loading the story…</p>
      <div className="articleHead">
        <p className="articleMeta">
          <span className="skeleton skeleton--meta" />
        </p>
        <span className="skeleton skeleton--title" />
        <span className="skeleton skeleton--title skeleton--short" />
      </div>
      <div className="articleRungs">
        {["The idea", "Explain", "Technical"].map((label) => (
          <span className="articleRung" key={label}>
            {label}
          </span>
        ))}
      </div>
      <div className="articleProse">
        {[100, 96, 99, 92, 97, 70].map((width, index) => (
          <span
            className="skeleton skeleton--line"
            key={index}
            style={{ width: `${width}%` }}
          />
        ))}
      </div>
    </div>
  );
}
