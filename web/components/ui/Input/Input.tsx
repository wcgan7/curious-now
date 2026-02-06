'use client';

import { forwardRef } from 'react';
import clsx from 'clsx';

import styles from './Input.module.css';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, hint, id, className, ...props },
  ref
) {
  const inputId = id || props.name;
  const describedBy = error
    ? inputId
      ? `${inputId}-error`
      : undefined
    : hint
      ? inputId
        ? `${inputId}-hint`
        : undefined
      : undefined;

  return (
    <div className={clsx(styles.wrapper, className)}>
      {label ? (
        <label htmlFor={inputId} className={styles.label}>
          {label}
        </label>
      ) : null}
      <input
        ref={ref}
        id={inputId}
        className={clsx(styles.input, error && styles.error)}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        {...props}
      />
      {error && inputId ? (
        <p id={`${inputId}-error`} className={styles.errorText} role="alert">
          {error}
        </p>
      ) : null}
      {hint && !error && inputId ? (
        <p id={`${inputId}-hint`} className={styles.hint}>
          {hint}
        </p>
      ) : null}
    </div>
  );
});

