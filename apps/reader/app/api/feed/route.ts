import { NextRequest, NextResponse } from "next/server";

import { decodeCursor, getFeedPage } from "@/lib/data";
import { leavesForFields, parseFields } from "@/lib/fields";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const rawCursor = request.nextUrl.searchParams.get("cursor");
  const cursor = decodeCursor(rawCursor);
  if (rawCursor && !cursor) {
    return NextResponse.json({ error: "invalid cursor" }, { status: 400 });
  }

  // The filter has to travel with the cursor. Without it, scrolling a filtered
  // feed quietly returns to everything at the second page.
  const chosen = parseFields(request.nextUrl.searchParams.get("fields") ?? undefined);
  const page = await getFeedPage(cursor, 20, leavesForFields(chosen));
  return NextResponse.json(page, {
    headers: {
      // Varies by field, and the URL carries it, so a shared cache is safe.
      "Cache-Control": "public, s-maxage=60, stale-while-revalidate=300",
    },
  });
}
