
import { CommonModule } from '@angular/common';
import { Component,OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { SupabaseAuthService } from '../../core/services/supabase-auth';

@Component({
  selector: 'app-auth',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './auth.html',
  styleUrl: './auth.css',
})
export class Auth implements OnInit{
  isLogin = true;
  email = '';
  password = '';
  loading = false;
  message = '';
  error = '';
  needsEmailConfirmation = false;

  constructor(
    private authService: SupabaseAuthService,
    private router: Router
  ) {}

  toggleMode(): void {
    this.isLogin = !this.isLogin;
    this.message = '';
    this.error = '';
    this.needsEmailConfirmation = false;
  }
ngOnInit(): void {
  console.log('AUTH COMPONENT LOADED');
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

  try {
    if (this.isLogin) {
      const { data, error } = await this.authService.signIn(
        this.email.trim(),
        this.password
      );

      if (error) {
        const authError = error as {
          message?: string;
          code?: string;
        };
        const token = await this.authService.getAccessToken();
console.log('Access token:', token);

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

      this.message = 'Login successful! Redirecting...';

      const navigated = await this.router.navigateByUrl('/dashboard');

      console.log('Navigation result:', navigated);
      console.log('Current URL:', this.router.url);

      if (!navigated) {
        this.error = 'Navigation failed. Check the route configuration.';
      }

      return;
    }

    const { data, error } = await this.authService.signUp(
      this.email.trim(),
      this.password
    );

    if (error) {
      throw error;
    }

    this.message = data.session
      ? 'Account created successfully! Please sign in.'
      : 'Account created. Check your email to confirm your account.';
  } catch (err: unknown) {
    this.error =
      err instanceof Error
        ? err.message
        : 'Authentication failed.';
  } finally {
    this.loading = false;
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

    try {
      const { error } = await this.authService.resendConfirmation(
        this.email.trim()
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
    }
  }
}
