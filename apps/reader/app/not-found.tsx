import Link from "next/link";

export default function NotFound() {
  return (
    <section className="messagePage">
      <p className="sectionKicker">Nothing here</p>
      <h1>This story could not be found.</h1>
      <p>It may have been merged, hidden, or never existed.</p>
      <Link className="primaryLink" href="/">
        Return to the feed
      </Link>
    </section>
  );
}
