"use client";

import { useEffect, useState } from "react";

type Choice = "system" | "light" | "dark";

const STORAGE_KEY = "cn-theme";

/** The script that runs before the first paint.
 *
 * Without it the page renders in the system theme, React hydrates, and the
 * reader's stored choice snaps into place a frame later — a white flash on the
 * way into a dark page, which is the one bug every theme toggle ships with.
 * Inlined in the document head, it sets the attribute before anything is
 * drawn.
 */
export const THEME_SCRIPT = `(function(){try{
var q=new URLSearchParams(location.search).get('theme');
var c=q||localStorage.getItem(${JSON.stringify(STORAGE_KEY)});
if(c==='light'||c==='dark'){document.documentElement.dataset.theme=c}
}catch(e){}})()`;

function apply(choice: Choice) {
  const root = document.documentElement;
  if (choice === "system") {
    delete root.dataset.theme;
  } else {
    root.dataset.theme = choice;
  }
  try {
    if (choice === "system") {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, choice);
    }
  } catch {
    // Private browsing refuses storage. The choice still applies to this page,
    // it just will not be remembered, which is better than not working.
  }
}

/** Light and dark, with the system as a first-class third option.
 *
 * Two states would be simpler and would strand anyone whose phone switches at
 * dusk: once they have touched the control, the page stops following. So the
 * cycle returns to "system" rather than ending at a fixed choice, and that is
 * the state it starts in.
 *
 * `labelled` renders it as three named choices instead of one cycling glyph.
 * A glyph works in a masthead, where space is the constraint and the reader is
 * mid-task; in a settings sheet there is room to say what the options are, and
 * a control you meet once should not have to be discovered by pressing it.
 */
export function ThemeToggle({ labelled = false }: { labelled?: boolean }) {
  // "system" is both the default and the correct first render for anyone who
  // has not chosen, so the control paints immediately and only the glyph
  // changes once storage has been read. An earlier version hid the button
  // until then, which cost a reflow in the masthead to avoid one frame of a
  // glyph that was usually right anyway.
  const [choice, setChoice] = useState<Choice>("system");

  // Read back what the pre-paint script resolved, rather than reading storage
  // again. The script consults the URL as well as storage, so asking storage
  // directly left the glyph saying "system" on a page the script had already
  // put into dark — the control disagreeing with the thing it controls.
  useEffect(() => {
    const applied = document.documentElement.dataset.theme;
    if (applied === "light" || applied === "dark") {
      setChoice(applied);
    }
  }, []);

  const next: Record<Choice, Choice> = {
    system: "dark",
    dark: "light",
    light: "system",
  };

  const label: Record<Choice, string> = {
    system: "Theme: following the system",
    dark: "Theme: dark",
    light: "Theme: light",
  };

  if (labelled) {
    return (
      <div aria-label="Appearance" className="themeChoices" role="radiogroup">
        {(["system", "light", "dark"] as const).map((option) => (
          <button
            aria-checked={choice === option}
            className={
              choice === option ? "themeChoice m-themeChoice--on" : "themeChoice"
            }
            key={option}
            onClick={() => {
              setChoice(option);
              apply(option);
            }}
            role="radio"
            type="button"
          >
            <span aria-hidden="true" className="themeGlyph" data-choice={option} />
            {option === "system" ? "System" : option === "light" ? "Light" : "Dark"}
          </button>
        ))}
      </div>
    );
  }

  return (
    <button
      aria-label={label[choice]}
      className="theme"
      onClick={() => {
        const chosen = next[choice];
        setChoice(chosen);
        apply(chosen);
      }}
      title={label[choice]}
      type="button"
    >
      <span aria-hidden="true" className="themeGlyph" data-choice={choice} />
    </button>
  );
}
