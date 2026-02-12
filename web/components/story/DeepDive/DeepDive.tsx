import styles from './DeepDive.module.css';

type StructuredDeepDive = {
  what_happened?: string;
  why_it_matters?: string;
  background?: string;
  limitations?: string[];
  whats_next?: string;
  related_concepts?: string[];
  source_count?: number;
  generated_at?: string;
};

type MarkdownList = {
  ordered: boolean;
  start?: number;
  items: MarkdownListItem[];
};

type MarkdownListItem = {
  text: string;
  children: MarkdownList[];
  trailingText: string[];
};

type MarkdownBlock =
  | { type: 'heading'; level: number; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'list'; list: MarkdownList };

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function asStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const arr = value.map((x) => (typeof x === 'string' ? x.trim() : '')).filter(Boolean);
  return arr.length ? arr : undefined;
}

function parseStructuredDeepDive(raw: string): StructuredDeepDive | null {
  const text = raw.trim();
  if (!(text.startsWith('{') && text.endsWith('}'))) return null;

  try {
    const parsed = JSON.parse(text) as unknown;
    if (!isPlainObject(parsed)) return null;

    const dd: StructuredDeepDive = {
      what_happened: asString(parsed.what_happened),
      why_it_matters: asString(parsed.why_it_matters),
      background: asString(parsed.background),
      limitations: asStringArray(parsed.limitations),
      whats_next: asString(parsed.whats_next),
      related_concepts: asStringArray(parsed.related_concepts),
    };

    // Basic signal that this is actually structured content.
    if (
      !dd.what_happened &&
      !dd.why_it_matters &&
      !dd.background &&
      !dd.whats_next &&
      !dd.limitations?.length &&
      !dd.related_concepts?.length
    ) {
      return null;
    }

    if (typeof parsed.source_count === 'number') dd.source_count = parsed.source_count;
    if (typeof parsed.generated_at === 'string') dd.generated_at = parsed.generated_at;

    return dd;
  } catch {
    return null;
  }
}

function parseMarkdownBlocks(raw: string): MarkdownBlock[] {
  const lines = raw.replace(/\r\n/g, '\n').split('\n');
  const blocks: MarkdownBlock[] = [];
  let i = 0;

  function indentWidth(s: string): number {
    return s.replace(/\t/g, '  ').length;
  }

  function parseList(
    start: number,
    ordered: boolean,
    baseIndent: number,
    startNumber?: number
  ): { list: MarkdownList; next: number } {
    const items: MarkdownListItem[] = [];
    let cursor = start;
    let lastItem: MarkdownListItem | null = null;

    while (cursor < lines.length) {
      const line = lines[cursor];
      const ul = line.match(/^(\s*)[-*+]\s+(.+)$/);
      const ol = line.match(/^(\s*)(\d+)\.\s+(.+)$/);
      const isOrderedLine = Boolean(ol);
      const match = ol || ul;
      if (!match) {
        const trimmed = line.trim();
        if (!trimmed) {
          // Keep list continuity across blank lines between list items.
          cursor += 1;
          continue;
        }
        const indent = indentWidth((line.match(/^(\s*)/)?.[1] ?? ''));
        if (lastItem && indent > baseIndent) {
          if (lastItem.children.length > 0) {
            lastItem.trailingText.push(trimmed);
          } else {
            lastItem.text = `${lastItem.text} ${trimmed}`.trim();
          }
          cursor += 1;
          continue;
        }
        break;
      }

      const indent = indentWidth(match[1]);
      const text = (ol ? ol[3] : ul?.[2] ?? '').trim();
      if (indent < baseIndent) break;

      if (indent > baseIndent) {
        if (!lastItem) break;
        const nested = parseList(
          cursor,
          isOrderedLine,
          indent,
          ol ? Number.parseInt(ol[2] ?? '1', 10) : undefined
        );
        if (nested.list.items.length) {
          lastItem.children.push(nested.list);
        }
        cursor = nested.next;
        continue;
      }

      if (isOrderedLine !== ordered) break;

      const item: MarkdownListItem = { text, children: [], trailingText: [] };
      items.push(item);
      lastItem = item;
      cursor += 1;
    }

    return { list: { ordered, start: ordered ? startNumber ?? 1 : undefined, items }, next: cursor };
  }

  while (i < lines.length) {
    const line = lines[i].trim();
    if (!line) {
      i += 1;
      continue;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      blocks.push({
        type: 'heading',
        level: headingMatch[1].length,
        text: headingMatch[2].trim(),
      });
      i += 1;
      continue;
    }

    const raw = lines[i];
    const ul = raw.match(/^(\s*)[-*+]\s+(.+)$/);
    if (ul) {
      const parsed = parseList(i, false, indentWidth(ul[1]));
      if (parsed.list.items.length) blocks.push({ type: 'list', list: parsed.list });
      i = parsed.next;
      continue;
    }

    const ol = raw.match(/^(\s*)(\d+)\.\s+(.+)$/);
    if (ol) {
      const parsed = parseList(i, true, indentWidth(ol[1]), Number.parseInt(ol[2], 10));
      if (parsed.list.items.length) blocks.push({ type: 'list', list: parsed.list });
      i = parsed.next;
      continue;
    }

    const paragraph: string[] = [];
    while (i < lines.length) {
      const next = lines[i].trim();
      if (!next) break;
      if (/^(#{1,6})\s+/.test(next)) break;
      if (/^[-*+]\s+/.test(next)) break;
      if (/^\d+\.\s+/.test(next)) break;
      paragraph.push(next);
      i += 1;
    }
    if (paragraph.length) {
      blocks.push({ type: 'paragraph', text: paragraph.join(' ') });
    }
  }

  return blocks;
}

function renderList(list: MarkdownList, key: string): React.ReactElement {
  const children = list.items.map((item, idx) => (
    <li key={`${key}-${idx}`}>
      {renderInline(item.text)}
      {item.children.map((child, childIdx) => renderList(child, `${key}-${idx}-${childIdx}`))}
      {item.trailingText.map((line, lineIdx) => (
        <div key={`${key}-${idx}-tail-${lineIdx}`}>{renderInline(line)}</div>
      ))}
    </li>
  ));

  if (list.ordered) {
    return (
      <ol key={key} className={styles.list} start={list.start && list.start > 1 ? list.start : undefined}>
        {children}
      </ol>
    );
  }

  return (
    <ul key={key} className={styles.list}>
      {children}
    </ul>
  );
}

function renderInline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const regex =
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|`([^`]+)`|\*\*([^*]+)\*\*|__([^_]+)__|\*([^*]+)\*|_([^_]+)_/g;
  let last = 0;
  let m: RegExpExecArray | null;

  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) {
      nodes.push(text.slice(last, m.index));
    }
    if (m[1] && m[2]) {
      nodes.push(
        <a
          key={`${m.index}-link`}
          href={m[2]}
          target="_blank"
          rel="noopener noreferrer"
          className={styles.link}
        >
          {m[1]}
        </a>
      );
    } else if (m[3]) {
      nodes.push(
        <code key={`${m.index}-code`} className={styles.code}>
          {m[3]}
        </code>
      );
    } else if (m[4] || m[5]) {
      nodes.push(
        <strong key={`${m.index}-strong`} className={styles.strong}>
          {m[4] || m[5]}
        </strong>
      );
    } else if (m[6] || m[7]) {
      nodes.push(
        <em key={`${m.index}-em`} className={styles.em}>
          {m[6] || m[7]}
        </em>
      );
    }
    last = regex.lastIndex;
  }
  if (last < text.length) {
    nodes.push(text.slice(last));
  }
  return nodes;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className={styles.section} aria-label={title}>
      <h3 className={styles.h3}>{title}</h3>
      <div className={styles.body}>{children}</div>
    </section>
  );
}

export function DeepDive({ value }: { value: string }) {
  const structured = parseStructuredDeepDive(value);
  if (structured) {
    return (
      <div className={styles.structured}>
        {structured.what_happened ? (
          <Section title="What happened">
            <p className={styles.prose}>{structured.what_happened}</p>
          </Section>
        ) : null}
        {structured.why_it_matters ? (
          <Section title="Why it matters">
            <p className={styles.prose}>{structured.why_it_matters}</p>
          </Section>
        ) : null}
        {structured.background ? (
          <Section title="Background">
            <p className={styles.prose}>{structured.background}</p>
          </Section>
        ) : null}
        {structured.limitations?.length ? (
          <Section title="Limitations">
            <ul className={styles.list}>
              {structured.limitations.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </Section>
        ) : null}
        {structured.whats_next ? (
          <Section title="What’s next">
            <p className={styles.prose}>{structured.whats_next}</p>
          </Section>
        ) : null}
        {structured.related_concepts?.length ? (
          <Section title="Related concepts">
            <div className={styles.chips}>
              {structured.related_concepts.map((c) => (
                <span key={c} className={styles.chip}>
                  {c}
                </span>
              ))}
            </div>
          </Section>
        ) : null}
        {structured.source_count || structured.generated_at ? (
          <div className={styles.footer}>
            {typeof structured.source_count === 'number' ? (
              <span>{structured.source_count} paper(s)</span>
            ) : null}
            {structured.generated_at ? (
              <>
                {typeof structured.source_count === 'number' ? (
                  <span aria-hidden="true">&middot;</span>
                ) : null}
                <time dateTime={structured.generated_at}>
                  {new Date(structured.generated_at).toLocaleString()}
                </time>
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }

  const blocks = parseMarkdownBlocks(value);
  return (
    <div className={styles.markdown}>
      {blocks.map((block, idx) => {
        if (block.type === 'heading') {
          const Comp = block.level <= 2 ? 'h3' : 'h4';
          return (
            <Comp key={`${block.type}-${idx}`} className={styles.mdHeading}>
              {renderInline(block.text)}
            </Comp>
          );
        }
        if (block.type === 'paragraph') {
          return (
            <p key={`${block.type}-${idx}`} className={styles.prose}>
              {renderInline(block.text)}
            </p>
          );
        }
        return renderList(block.list, `list-${idx}`);
      })}
    </div>
  );
}
