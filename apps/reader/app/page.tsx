import { FeedStream } from "@/components/FeedStream";
import { getFeedPage } from "@/lib/data";
import { GROUPS, leavesForFields, parseFields } from "@/lib/fields";

export const dynamic = "force-dynamic";

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ fields?: string }>;
}) {
  const { fields } = await searchParams;
  const chosen = parseFields(fields);
  const wanted = leavesForFields(chosen);

  // The filter is in the query, not applied to a fetched page. Filtering twenty
  // rows afterwards left a reader who asked for space with an empty screen and
  // a "load more" button, because the head of the feed is homogeneous and every
  // other field is hundreds of rows down.
  const initialPage = await getFeedPage(null, 20, wanted);

  return (
    <>
      {/* No visible page heading. "What to read" named a page the reader was
          already looking at, and everything beside it was constant on every
          card at the top of the feed. It stays for a screen reader, which
          otherwise meets an unlabelled list of links. */}
      <h1 className="visuallyHidden">
        {chosen.length > 0
          ? GROUPS.filter((group) => chosen.includes(group.slug))
              .map((group) => group.label)
              .join(", ")
          : "Latest science"}
      </h1>
      <FeedStream fields={chosen} initialPage={initialPage} />
    </>
  );
}
