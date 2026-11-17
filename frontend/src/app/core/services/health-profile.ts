
import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { SupabaseAuthService } from './supabase-auth';
import { environment } from '../../../environments/environments';

export interface HealthProfile {
  id: number;
  goals: string;
  dietary_preferences: string;
  daily_budget: string | number;
}

export interface HealthProfileInput {
  goals: string;
  dietary_preferences: string;
  daily_budget: number;
}

@Injectable({
  providedIn: 'root',
})
export class HealthProfileService {
  private readonly apiUrl =
  `${environment.apiBaseUrl}/api/v1/health/profile`;

  constructor(
    private http: HttpClient,
    private authService: SupabaseAuthService
  ) {}

  async createProfile(
    profile: HealthProfileInput
  ): Promise<HealthProfile> {
    const token = await this.authService.getAccessToken();

    if (!token) {
      throw new Error('Please sign in before saving your profile.');
    }

    const headers = new HttpHeaders({
      Authorization: `Bearer ${token}`,
    });

    return firstValueFrom(
      this.http.post<HealthProfile>(
        this.apiUrl,
        profile,
        { headers }
      )
    );
  }
  async getMyProfile(): Promise<HealthProfile> {
  const token = await this.authService.getAccessToken();

  if (!token) {
    throw new Error('Please sign in first.');
  }

  const headers = new HttpHeaders({
    Authorization: `Bearer ${token}`,
  });

  return firstValueFrom(
    this.http.get<HealthProfile>(
      `${this.apiUrl}/me`,
      { headers }
    )
  );
}
async upsertMyProfile(
  profile: HealthProfileInput
): Promise<HealthProfile> {
  const token = await this.authService.getAccessToken();

  if (!token) {
    throw new Error('Please sign in first.');
  }

  const headers = new HttpHeaders({
    Authorization: `Bearer ${token}`,
  });

  return firstValueFrom(
    this.http.put<HealthProfile>(
      `${this.apiUrl}/me`,
      profile,
      { headers }
    )
  );
}
}
