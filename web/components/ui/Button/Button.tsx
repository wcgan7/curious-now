'use client';

import { forwardRef } from 'react';
import clsx from 'clsx';

import styles from './Button.module.css';

type ButtonVariant = 'primary' | 'secondary' | 'tertiary';
type ButtonSize = 'sm' | 'md';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'primary',
    size = 'md',
    isLoading = false,
    disabled,
    leftIcon,
    rightIcon,
    className,
    children,
    ...props
  },
  ref
) {
  return (
    <button
      ref={ref}
      disabled={disabled || isLoading}
      aria-busy={isLoading}
      className={clsx(styles.button, styles[variant], styles[size], className)}
      {...props}
    >
      {isLoading ? <span className={styles.spinner} aria-hidden="true" /> : null}
      {!isLoading && leftIcon ? <span className={styles.icon}>{leftIcon}</span> : null}
      <span className={styles.label}>{children}</span>
      {!isLoading && rightIcon ? <span className={styles.icon}>{rightIcon}</span> : null}
    </button>
  );
});

