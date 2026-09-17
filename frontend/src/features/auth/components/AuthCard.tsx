import type { ReactNode } from 'react';
import './auth.css';

interface AuthCardProps {
  title: string;
  description: string;
  children: ReactNode;
}

export function AuthCard({ title, description, children }: AuthCardProps) {
  return (
    <section className="auth-page">
      <div className="auth-card">
        <p className="auth-brand">
          <img src="/logo-mark.png" alt="" aria-hidden />
          MediSense
        </p>
        <h1>{title}</h1>
        <p className="auth-description">{description}</p>
        {children}
      </div>
    </section>
  );
}
