'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import styles from './SettingsPage.module.css';
import { Button } from '@/components/ui/Button/Button';
import { useMe } from '@/lib/hooks/useMe';
import { usePatchPrefs, usePrefs } from '@/lib/hooks/usePrefs';
import {
  getStoredFontPreference,
  setFontPreference,
  type FontPreference,
} from '@/lib/preferences/font';

export function SettingsPage() {
  return <SettingsInner />;
}

function SettingsInner() {
  const me = useMe();
  const authed = Boolean(me.data?.user);
  const prefs = usePrefs();
  const patch = usePatchPrefs();
  const [fontMode, setFontMode] = useState<FontPreference>('sans');

  useEffect(() => {
    setFontMode(getStoredFontPreference() || 'sans');
  }, []);

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

        <div className={styles.sections}>
          <section className={styles.section} aria-labelledby="appearance-heading">
            <h2 id="appearance-heading" className={styles.h2}>
              Appearance
            </h2>
            <p className={styles.p}>Choose your preferred reading font.</p>

            <div className={styles.fontToggle} role="group" aria-label="Font preference">
              <button
                type="button"
                className={fontMode === 'sans' ? styles.fontToggleBtnActive : styles.fontToggleBtn}
                aria-pressed={fontMode === 'sans'}
                onClick={() => {
                  setFontMode('sans');
                  setFontPreference('sans');
                }}
              >
                Sans-serif
              </button>
              <button
                type="button"
                className={fontMode === 'serif' ? styles.fontToggleBtnActive : styles.fontToggleBtn}
                aria-pressed={fontMode === 'serif'}
                onClick={() => {
                  setFontMode('serif');
                  setFontPreference('serif');
                }}
              >
                Serif
              </button>
            </div>
          </section>

          {!authed ? (
            <section className={styles.section} aria-labelledby="account-settings-heading">
              <h2 id="account-settings-heading" className={styles.h2}>
                Account settings
              </h2>
              <p className={styles.p}>
                Log in to manage reading mode, followed topics, blocked sources, and notifications.
              </p>
              <div className={styles.row}>
                <Link href="/auth/login?redirect=%2Fsettings">
                  <Button variant="primary">Log in</Button>
                </Link>
              </div>
            </section>
          ) : prefs.isLoading ? (
            <p className={styles.hint}>Loading…</p>
          ) : prefs.isError ? (
            <p className={styles.error}>Failed to load preferences.</p>
          ) : !prefs.data ? null : (
            <>
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
            </>
          )}
        </div>
      </div>
    </main>
  );
}
