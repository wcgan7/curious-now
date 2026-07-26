"use client";

export default function ErrorPage({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <section className="messagePage">
      <p className="sectionKicker">A temporary pause</p>
      <h1>The reader could not reach its source shelf.</h1>
      <p>The collection pipeline is separate, so no science has been lost.</p>
      <button className="primaryButton" onClick={reset} type="button">
        Try again
      </button>
    </section>
  );
}
