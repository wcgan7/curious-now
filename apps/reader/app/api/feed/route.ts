import { NextRequest, NextResponse } from "next/server";

import { decodeCursor, getFeedPage } from "@/lib/data";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const rawCursor = request.nextUrl.searchParams.get("cursor");
  const cursor = decodeCursor(rawCursor);
  if (rawCursor && !cursor) {
    return NextResponse.json({ error: "invalid cursor" }, { status: 400 });
  }

  const page = await getFeedPage(cursor);
  return NextResponse.json(page, {
    headers: {
      "Cache-Control": "public, s-maxage=60, stale-while-revalidate=300",
    },
  });
}
