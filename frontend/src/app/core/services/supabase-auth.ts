
import { Injectable } from '@angular/core';
import { createClient, SupabaseClient, Session, AuthChangeEvent } from '@supabase/supabase-js';
import { environment } from '../../../environments/environments';

@Injectable({
  providedIn: 'root',
})
export class SupabaseAuthService {
  private readonly supabase: SupabaseClient = createClient(
    environment.supabaseUrl,
    environment.supabasePublishableKey
  );

  async signUp(email: string, password: string) {
    return this.supabase.auth.signUp({
      email,
      password,
    });
  }

  async signIn(email: string, password: string) {
    return this.supabase.auth.signInWithPassword({
      email,
      password,
    });
  }


async resendConfirmation(email: string) {
  return this.supabase.auth.resend({
    type: 'signup',
    email,
    options: {
      emailRedirectTo: window.location.origin,
    },
  });
}


  async signOut() {
    return this.supabase.auth.signOut();
  }

  async getSession(): Promise<Session | null> {
    const { data, error } = await this.supabase.auth.getSession();

    if (error) {
      throw error;
    }

    return data.session;
  }

  onAuthStateChange(
    callback: (event: AuthChangeEvent, session: Session | null) => void
  ) {
    return this.supabase.auth.onAuthStateChange(callback);
  }

  getAccessToken(): Promise<string | null> {
    return this.getSession().then((session) => session?.access_token ?? null);
  }
  async debugAccessToken(): Promise<void> {
  const session = await this.getSession();

  console.log('Session exists:', !!session);
  console.log('Access token exists:', !!session?.access_token);
}
}
