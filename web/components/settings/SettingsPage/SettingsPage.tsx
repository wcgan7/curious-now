'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';

import styles from './SettingsPage.module.css';
import { AuthGuard } from '@/components/auth/AuthGuard/AuthGuard';
import { Button } from '@/components/ui/Button/Button';
import { usePatchPrefs, usePrefs } from '@/lib/hooks/usePrefs';

export function SettingsPage() {
  return (
    <AuthGuard>
      <SettingsInner />
    </AuthGuard>
  );
}

function SettingsInner() {
  const prefs = usePrefs();
  const patch = usePatchPrefs();

  const initialMode = prefs.data?.prefs.reading_mode_default || 'intuition';
  const [draftMode, setDraftMode] = useState<'intuition' | 'deep'>(initialMode);
  const [touched, setTouched] = useState(false);

  const mode = touched ? draftMode : initialMode;
  const changed = useMemo(() => mode !== initialMode, [mode, initialMode]);

  return (
    <main className={styles.main}>
      <div className={styles.container}>
        <header className={styles.header}>
          <h1 className={styles.title}>Settings</h1>
          <p className={styles.subtitle}>Preferences for how you read and what you follow.</p>
        </header>

        {prefs.isLoading ? (
          <p className={styles.hint}>Loading…</p>
        ) : prefs.isError ? (
          <p className={styles.error}>Failed to load preferences.</p>
        ) : !prefs.data ? null : (
          <div className={styles.sections}>
            <section className={styles.section} aria-labelledby="reading-mode-heading">
              <h2 id="reading-mode-heading" className={styles.h2}>
                Reading mode
              </h2>
              <p className={styles.p}>Choose the default view for story pages.</p>

              <div className={styles.radioGroup}>
                <label className={styles.radioRow}>
                  <input
                    type="radio"
                    name="reading_mode_default"
                    value="intuition"
                    checked={mode === 'intuition'}
                    onChange={() => {
                      setTouched(true);
                      setDraftMode('intuition');
                    }}
                  />
                  <span className={styles.radioLabel}>Intuition (short)</span>
                </label>
                <label className={styles.radioRow}>
                  <input
                    type="radio"
                    name="reading_mode_default"
                    value="deep"
                    checked={mode === 'deep'}
                    onChange={() => {
                      setTouched(true);
                      setDraftMode('deep');
                    }}
                  />
                  <span className={styles.radioLabel}>Deep (full)</span>
                </label>
              </div>

              <div className={styles.row}>
                <Button
                  variant="primary"
                  disabled={!changed || patch.isPending}
                  isLoading={patch.isPending}
                  onClick={() =>
                    patch.mutate(
                      { reading_mode_default: mode },
                      {
                        onSuccess: () => {
                          setTouched(false);
                        },
                      }
                    )
                  }
                >
                  Save
                </Button>
                {patch.isError ? <span className={styles.errorInline}>Save failed.</span> : null}
                {patch.isSuccess && changed ? (
                  <span className={styles.okInline}>Saved.</span>
                ) : null}
              </div>
            </section>

            <section className={styles.section} aria-labelledby="manage-heading">
              <h2 id="manage-heading" className={styles.h2}>
                Manage
              </h2>
              <div className={styles.links}>
                <Link className={styles.linkCard} href="/settings/topics">
                  <div className={styles.linkTitle}>Followed topics</div>
                  <div className={styles.linkDesc}>Choose what you see more of.</div>
                </Link>
                <Link className={styles.linkCard} href="/settings/sources">
                  <div className={styles.linkTitle}>Blocked sources</div>
                  <div className={styles.linkDesc}>Hide sources you don&apos;t trust.</div>
                </Link>
                <Link className={styles.linkCard} href="/settings/notifications">
                  <div className={styles.linkTitle}>Notifications</div>
                  <div className={styles.linkDesc}>Email/push settings (v0).</div>
                </Link>
              </div>
            </section>
          </div>
        )}
      </div>
    </main>
  );
}
