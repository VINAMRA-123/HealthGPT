import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { SupabaseAuthService } from '../services/supabase-auth';

/** Private pages: signed-out visitors are sent to the login screen. */
export const authGuard: CanActivateFn = async () => {
  const auth = inject(SupabaseAuthService);
  const router = inject(Router);

  try {
    if (await auth.getSession()) {
      return true;
    }
  } catch {
    // Treat an unreadable session as signed out.
  }

  return router.createUrlTree(['/']);
};

/** Login page: signed-in users skip straight to their dashboard. */
export const guestGuard: CanActivateFn = async () => {
  const auth = inject(SupabaseAuthService);
  const router = inject(Router);

  try {
    if (await auth.getSession()) {
      return router.createUrlTree(['/dashboard']);
    }
  } catch {
    // Fall through to the login page.
  }

  return true;
};
