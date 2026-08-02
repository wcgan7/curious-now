import { describe, expect, it } from "vitest";

import { decodeCursor } from "@/lib/data";

function encode(value: unknown): string {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

const VALID = {
  sortAt: "2026-08-01T12:00:00.000Z",
  id: "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
};

describe("decodeCursor", () => {
  it("accepts a cursor it minted", () => {
    expect(decodeCursor(encode(VALID))).toEqual(VALID);
  });

  it("rejects a cursor from before the ranking change", () => {
    // Old cursors carried a numeric score and no longer describe a position.
    // Refusing them starts the reader at the top, which is the right
    // degradation; accepting one would page from a meaningless offset.
    const old = decodeCursor(encode({ ...VALID, score: 0.42 }));

    expect(old).toEqual(VALID);
  });

  it("refuses an id that is not a UUID", () => {
    // The value arrives from a URL, so it reaches a SQL parameter.
    expect(decodeCursor(encode({ ...VALID, id: "1 OR 1=1" }))).toBeNull();
    expect(decodeCursor(encode({ ...VALID, id: "../../etc/passwd" }))).toBeNull();
  });

  it("refuses a timestamp that is not a date", () => {
    expect(decodeCursor(encode({ ...VALID, sortAt: "not a date" }))).toBeNull();
  });

  it("refuses missing fields", () => {
    expect(decodeCursor(encode({ id: VALID.id }))).toBeNull();
    expect(decodeCursor(encode({ sortAt: VALID.sortAt }))).toBeNull();
  });

  it("refuses values of the wrong type", () => {
    expect(decodeCursor(encode({ sortAt: 12345, id: VALID.id }))).toBeNull();
    expect(decodeCursor(encode({ ...VALID, id: null }))).toBeNull();
  });

  it("refuses input that is not a cursor at all", () => {
    expect(decodeCursor("not base64 at all !!")).toBeNull();
    expect(decodeCursor(encode("a bare string"))).toBeNull();
    expect(decodeCursor(encode([1, 2, 3]))).toBeNull();
    expect(decodeCursor(Buffer.from("{ broken json").toString("base64url"))).toBeNull();
  });

  it("treats an absent cursor as the first page", () => {
    expect(decodeCursor(null)).toBeNull();
    expect(decodeCursor("")).toBeNull();
  });
});
