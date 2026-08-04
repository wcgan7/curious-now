import taxonomy from "./fields.json";

/**
 * The fields a reader can choose between.
 *
 * Read from the same file the generation pass offers to the model, because a
 * taxonomy held in two places files a story under one field and shows it under
 * another. Nothing here is restated; the labels, the notes and the grouping all
 * come from config/v2/fields.json.
 *
 * `./fields.json` is a copy, and it is a copy reluctantly. Importing the real
 * path type-checks and then fails to bundle — the file sits outside the app
 * root, and neither Turbopack nor webpack will reach across it, nor follow a
 * symlink that does. That is a 500 tsc cannot see.
 *
 * So the copy is guarded instead of trusted: `test_v2_fields.py` asserts the
 * two files are byte-identical, and `scripts/v2_sync_reader_fields.py` refreshes
 * it. Editing the config and forgetting the copy fails the suite rather than
 * quietly filing stories under labels the reader does not show.
 *
 * ## Leaves are stored, groups are shown
 *
 * Every story carries a leaf — `mathematics`, `neuroscience`, `spaceflight` —
 * and this file groups 33 of them into 8. That split is the whole design: the
 * corpus cannot fill 33 categories today (mathematics holds about six stories),
 * but it will, and when it does, promoting one to the top level is an edit to
 * that config with no re-tagging. Every story already carries the finer answer.
 *
 * The top level must always partition: every story in exactly one visible
 * entry, never zero and never two. That is why promotion is a deliberate edit
 * rather than something a count threshold performs on its own — promoting
 * `mathematics` silently changes what "Physical sciences" means for everyone
 * already using it, including anyone with that selection saved.
 *
 * ## Why the field is read rather than inferred
 *
 * The first version derived the field from the source, which is free and covers
 * most of the corpus. Measured against a classifier over 150 random stories it
 * disagreed on a third of them, and the classifier was nearly always right:
 * arXiv's physical sciences feed carries geology, planetary science and
 * materials science; Google Research publishes on satellites and dermatology.
 * A venue is not a subject.
 */

export interface FieldLeaf {
  slug: string;
  label: string;
}

export interface FieldGroup {
  slug: string;
  label: string;
  /** What it means, where the name alone leaves a boundary in doubt. */
  note: string;
  leaves: FieldLeaf[];
}

export const GROUPS: readonly FieldGroup[] = taxonomy.groups;

export const TAXONOMY_VERSION: string = taxonomy.version;

const GROUP_OF_LEAF = new Map<string, string>(
  GROUPS.flatMap((group) => group.leaves.map((leaf) => [leaf.slug, group.slug])),
);

export function groupOfLeaf(leaf: string | null | undefined): string | null {
  return (leaf && GROUP_OF_LEAF.get(leaf)) ?? null;
}

export function groupBySlug(slug: string | undefined): FieldGroup | undefined {
  return GROUPS.find((group) => group.slug === slug);
}

/**
 * The chosen groups, parsed from a URL.
 *
 * An empty selection means everything rather than nothing. That is the only
 * reading that makes the control safe: a reader who unticks their last field
 * should get the whole feed back, not an empty page they have to work out how
 * to escape from.
 */
export function parseFields(value: string | undefined): string[] {
  if (!value) {
    return [];
  }
  const known = new Set(GROUPS.map((group) => group.slug));
  return [...new Set(value.split(",").map((part) => part.trim()))].filter((slug) =>
    known.has(slug),
  );
}

/** Written in the taxonomy's order, so one selection always makes one URL. */
export function serialiseFields(slugs: readonly string[]): string {
  return GROUPS.filter((group) => slugs.includes(group.slug))
    .map((group) => group.slug)
    .join(",");
}

/**
 * The leaves to restrict the feed query to, or null for no restriction.
 *
 * Choosing a group means any of its leaves. Null rather than every leaf,
 * because a story whose field was never established carries NULL and must still
 * appear under Everything — listing leaves would silently drop it.
 */
export function leavesForFields(slugs: readonly string[]): string[] | null {
  if (slugs.length === 0) {
    return null;
  }
  return GROUPS.filter((group) => slugs.includes(group.slug)).flatMap((group) =>
    group.leaves.map((leaf) => leaf.slug),
  );
}

/* countsByField summed a group from its leaves so the drawer could print a
   number beside each field. That number is a thing to know while building the
   corpus, not while reading it — see scripts/v2_field_counts.py. */

/* offerableLeaves and LEAF_THRESHOLD lived here, deciding which of a group's
   leaves were worth offering as a second level of selection. The drawer shows
   all of them instead, as the group's description — "Physics · Mathematics ·
   Materials science · Chemistry" says what Physical sciences contains better
   than a sentence about it does, and a leaf holding ten stories is still part
   of what the filter returns. They come back when a second level is really
   built; until then they were a threshold nothing consulted. */

/* describeSelection and describeSelectionShort lived here to label the bar's
   summary control. The drawer removed that control: the selection is shown by
   the ticked rows in the panel itself, and by a dot on the menu glyph, so a
   sentence naming it had nowhere left to go. */
