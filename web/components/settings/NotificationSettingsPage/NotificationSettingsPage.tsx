'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';

import styles from './NotificationSettingsPage.module.css';
import { AuthGuard } from '@/components/auth/AuthGuard/AuthGuard';
import { Button } from '@/components/ui/Button/Button';
import { usePatchPrefs, usePrefs } from '@/lib/hooks/usePrefs';

export function NotificationSettingsPage() {
  return (
    <AuthGuard>
      <NotificationSettingsInner />
    </AuthGuard>
  );
}

function NotificationSettingsInner() {
  const prefs = usePrefs();
  const patch = usePatchPrefs();

  const initial = useMemo(() => {
    return prefs.data?.prefs.notification_settings || {};
  }, [prefs.data]);

  const [raw, setRaw] = useState('');
  const [touched, setTouched] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);

  const text = touched ? raw : JSON.stringify(initial, null, 2);
  const canSave = !!prefs.data && !patch.isPending;

  return (
    <main className={styles.main}>
      <div className={styles.container}>
        <header className={styles.header}>
          <div className={styles.topRow}>
            <h1 className={styles.title}>Notifications</h1>
            <Link href="/settings" className={styles.back}>
              Back
            </Link>
          </div>
          <p className={styles.subtitle}>
            v0 stores notification settings as a flexible JSON object.
          </p>
        </header>

        {prefs.isLoading ? (
          <p className={styles.hint}>Loading…</p>
        ) : prefs.isError ? (
          <p className={styles.error}>Failed to load preferences.</p>
        ) : !prefs.data ? null : (
          <section className={styles.section}>
            <label className={styles.label} htmlFor="notification-json">
              notification_settings (JSON)
            </label>
            <textarea
              id="notification-json"
              className={styles.textarea}
              value={text}
              onChange={(e) => {
                setRaw(e.target.value);
                setTouched(true);
                setParseError(null);
              }}
              rows={12}
              spellCheck={false}
            />

            {parseError ? <p className={styles.errorInline}>{parseError}</p> : null}
            {patch.isError ? <p className={styles.errorInline}>Save failed.</p> : null}

            <div className={styles.row}>
              <Button
                variant="primary"
                isLoading={patch.isPending}
                disabled={!canSave}
                onClick={() => {
                  try {
                    const parsed = JSON.parse(text);
                    patch.mutate(
                      { notification_settings: parsed },
                      {
                        onSuccess: () => {
                          setTouched(false);
                          setRaw('');
                        },
                      }
                    );
                  } catch {
                    setParseError('Invalid JSON.');
                  }
                }}
              >
                Save
              </Button>
              <Button
                variant="secondary"
                disabled={!canSave}
                onClick={() => {
                  setTouched(false);
                  setRaw('');
                  setParseError(null);
                }}
              >
                Reset
              </Button>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
