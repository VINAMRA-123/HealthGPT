import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { DashboardCache } from '../../core/services/dashboard-cache';
import { SupabaseAuthService } from '../../core/services/supabase-auth';

@Component({
  selector: 'app-auth',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './auth.html',
  styleUrl: './auth.css',
})
export class Auth {
  isLogin = true;
  email = '';
  password = '';
  loading = false;
  message = '';
  error = '';
  needsEmailConfirmation = false;

  constructor(
    private authService: SupabaseAuthService,
    private router: Router,
    private cdr: ChangeDetectorRef,
    private dashboardCache: DashboardCache,
  ) {}

  toggleMode(): void {
    this.isLogin = !this.isLogin;
    this.message = '';
    this.error = '';
    this.needsEmailConfirmation = false;
  }

  async submit(): Promise<void> {
    this.message = '';
    this.error = '';
    this.needsEmailConfirmation = false;

    if (!this.email.trim() || !this.password) {
      this.error = 'Please enter your email and password.';
      return;
    }

    this.loading = true;
    this.cdr.markForCheck();

    try {
      if (this.isLogin) {
        const { data, error } = await this.authService.signIn(
          this.email.trim(),
          this.password,
        );

        if (error) {
          const authError = error as {
            message?: string;
            code?: string;
          };

          this.needsEmailConfirmation =
            authError.code === 'email_not_confirmed' ||
            authError.message
              ?.toLowerCase()
              .includes('email not confirmed') === true;

          throw error;
        }

        if (!data.session) {
          this.error = 'Login succeeded, but no session was returned.';
          return;
        }

        // Never show a previous user's dashboard numbers.
        this.dashboardCache.clear();

        this.message = 'Login successful! Redirecting...';
        this.cdr.markForCheck();

        const navigated = await this.router.navigateByUrl('/dashboard');

        if (!navigated) {
          this.error = 'Navigation failed. Check the route configuration.';
        }

        return;
      }

      const { data, error } = await this.authService.signUp(
        this.email.trim(),
        this.password,
      );

      if (error) {
        throw error;
      }

      this.message = data.session
        ? 'Account created successfully! Please sign in.'
        : 'Account created. Check your email to confirm your account.';
    } catch (err: unknown) {
      this.error =
        err instanceof Error ? err.message : 'Authentication failed.';
    } finally {
      this.loading = false;
      this.cdr.markForCheck();
    }
  }

  async resendConfirmation(): Promise<void> {
    this.error = '';
    this.message = '';

    if (!this.email.trim()) {
      this.error = 'Enter your email address first.';
      return;
    }

    this.loading = true;
    this.cdr.markForCheck();

    try {
      const { error } = await this.authService.resendConfirmation(
        this.email.trim(),
      );

      if (error) {
        throw error;
      }

      this.message =
        'If a confirmation email can be sent, it will arrive shortly. Check your inbox and spam folder, and use the newest link.';
    } catch (err: unknown) {
      this.error =
        err instanceof Error
          ? err.message
          : 'Unable to request a confirmation email.';
    } finally {
      this.loading = false;
      this.cdr.markForCheck();
    }
  }
}
