import { describe, expect, it } from "vitest";

import {
  MAX_FRAME_ASPECT,
  MIN_FRAME_ASPECT,
  PHOTO_ASPECT,
  captionFor,
  emptyFraction,
  frameFor,
} from "@/lib/imagery";

describe("photographs", () => {
  it("always fill the frame", () => {
    // Their edges are background, so cropping costs nothing and blank space
    // would be pure loss.
    for (const [w, h] of [
      [4000, 3000],
      [1200, 1200],
      [3000, 1100],
    ]) {
      const frame = frameFor("photo", w, h);
      expect(frame.fit).toBe("cover");
      expect(frame.aspect).toBe(PHOTO_ASPECT);
    }
  });

  it("share one frame, so a run of them reads as a column", () => {
    expect(frameFor("photo", 4000, 3000).aspect).toBe(
      frameFor("photo", 1000, 900).aspect,
    );
  });
});

describe("figures", () => {
  it("are never cropped", () => {
    // The complaint this exists to answer: a fixed frame cut axis labels and
    // panel titles in half, because a figure's edges are where its words are.
    for (const [w, h] of [
      [500, 900],
      [900, 500],
      [4650, 1000],
      [540, 1000],
      [1, 1],
    ]) {
      expect(frameFor("figure", w, h).fit).toBe("contain");
    }
  });

  it("get a frame shaped to themselves, when the layout can carry it", () => {
    // 2.2:1 sits inside the permitted range, so the frame matches exactly and
    // there is neither a crop nor a gap.
    const frame = frameFor("figure", 2200, 1000);
    expect(frame.aspect).toBeCloseTo(2.2, 5);
    expect(emptyFraction(2.2, frame)).toBeCloseTo(0, 10);
  });

  it("stop at the floor rather than owning the screen", () => {
    // A square figure would otherwise take a 390px-tall frame on a 390px-wide
    // phone. The floor holds it to 195.
    const frame = frameFor("figure", 1000, 1000);
    expect(frame.aspect).toBeCloseTo(MIN_FRAME_ASPECT, 5);
  });

  it("stop at the ceiling rather than becoming a slit", () => {
    const frame = frameFor("figure", 4650, 1000);
    expect(frame.aspect).toBeCloseTo(MAX_FRAME_ASPECT, 5);
  });

  it("never take a frame outside what the layout permits", () => {
    for (let w = 200; w <= 5000; w += 311) {
      for (let h = 200; h <= 5000; h += 407) {
        const { aspect } = frameFor("figure", w, h);
        expect(aspect).toBeGreaterThanOrEqual(MIN_FRAME_ASPECT);
        expect(aspect).toBeLessThanOrEqual(MAX_FRAME_ASPECT);
      }
    }
  });

  it("keeps a figure legible even at the corpus extremes", () => {
    // 0.54 and 4.65 are the tallest and widest figures we hold. A tall one in
    // a 2:1 frame shows across 27% of the width — the price of a floor that
    // keeps every frame under 200px, and the reason that floor cannot go
    // lower. Anything past three quarters ground stops being a picture.
    for (const natural of [0.54, 4.65]) {
      const frame = frameFor("figure", natural * 1000, 1000);
      expect(emptyFraction(natural, frame)).toBeLessThan(0.75);
    }
    // The band the frame can match exactly costs nothing at all.
    for (const natural of [2.0, 2.2, 2.6]) {
      const frame = frameFor("figure", natural * 1000, 1000);
      expect(emptyFraction(natural, frame)).toBeCloseTo(0, 10);
    }
  });

  it("contain rather than cover before the image has reported its size", () => {
    // A figure briefly letterboxed settles into place; a figure briefly
    // cropped has already cut a label by the time it does.
    expect(frameFor("figure", 0, 0).fit).toBe("contain");
    expect(frameFor("figure", Number.NaN, 100).fit).toBe("contain");
  });
});

describe("emptyFraction", () => {
  it("is zero when the frame matches the image", () => {
    expect(emptyFraction(1.8, { aspect: 1.8, fit: "contain" })).toBeCloseTo(0, 10);
  });

  it("is zero for a cover fit, which fills by definition", () => {
    expect(emptyFraction(1.0, { aspect: 1.9, fit: "cover" })).toBe(0);
  });

  it("does not care which way the mismatch runs", () => {
    expect(emptyFraction(2, { aspect: 1, fit: "contain" })).toBeCloseTo(
      emptyFraction(1, { aspect: 2, fit: "contain" }),
      10,
    );
  });

  it("reports nothing empty for degenerate input rather than throwing", () => {
    expect(emptyFraction(0, { aspect: 1.9, fit: "contain" })).toBe(0);
    expect(emptyFraction(1.9, { aspect: 0, fit: "contain" })).toBe(0);
  });
});

describe("captionFor", () => {
  it("keeps the title sentence and drops the apparatus", () => {
    expect(
      captionFor(
        "Erased knowledge partially returns. NLL of concept A, erased at cut " +
          "step 1, as two unrelated concepts are subsequently cut in Arm 2.",
      ),
    ).toBe("Erased knowledge partially returns.");
  });

  it("keeps a caption that is only a title sentence", () => {
    expect(captionFor("Conceptual comparison of post-training paradigms.")).toBe(
      "Conceptual comparison of post-training paradigms.",
    );
  });

  it("breaks where the panels begin, which is lower case", () => {
    // The commonest caption in the corpus: a title sentence, then "a)".
    expect(
      captionFor(
        "Experimental scheme. a) Schematic of an icosahedral Ar/Ne cluster " +
          "doped with a phthalocyanine molecule. b) Femtosecond pump probe.",
      ),
    ).toBe("Experimental scheme.");
    expect(
      captionFor("Overview of the pipeline. (a) Encoder. (b) Decoder."),
    ).toBe("Overview of the pipeline.");
  });

  it("does not break at a decimal point", () => {
    // "0.5" is not the end of a sentence, and splitting there would leave a
    // caption reading "Cells were fixed at 0."
    expect(captionFor("Growth halts above 0.5 M NaCl in every strain.")).toBe(
      "Growth halts above 0.5 M NaCl in every strain.",
    );
  });

  it("does not break at an abbreviation", () => {
    expect(captionFor("Adapted from Laland et al. Nature, 2004.")).toBe(
      "Adapted from Laland et al. Nature, 2004.",
    );
    expect(captionFor("As in Fig. 2 but for the cold arm.")).toBe(
      "As in Fig. 2 but for the cold arm.",
    );
  });

  it("gives nothing when the first sentence is itself the apparatus", () => {
    // A caption cut mid-clause promises more and offers no way to reach it.
    expect(
      captionFor(
        "On the Math dataset using the Qwen3-0.6B model, KGPS obtains " +
          "comparable performance to evaluation-based selection with 71.00% " +
          "fewer rollouts, although the gap widens once the budget is halved.",
      ),
    ).toBeNull();
  });

  it("gives nothing when the sentence is partly mathematics", () => {
    // This is alt text now, so it has to survive being read aloud, and
    // "\(Q_{x}\)" read aloud is markup rather than a description.
    expect(
      captionFor("Level scheme of the \\(Q_{x}\\)-transition in H 2 Pc."),
    ).toBeNull();
    expect(captionFor("Error falls as $O(n^{-1/2})$ in every arm.")).toBeNull();
  });

  it("gives nothing for a figure that carries no caption", () => {
    expect(captionFor(null)).toBeNull();
    expect(captionFor("   ")).toBeNull();
  });
});
