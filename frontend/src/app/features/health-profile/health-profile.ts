
import { CommonModule } from '@angular/common';
import {
  ChangeDetectorRef,
  Component,
  OnInit,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import {
  HealthProfileService,
  HealthProfile,
} from '../../core/services/health-profile';

@Component({
  selector: 'app-health-profile',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './health-profile.html',
  styleUrl: './health-profile.css',
})
export class HealthProfileComponent implements OnInit {
  goals = '';
  dietaryPreferences = '';
  dailyBudget: number | null = null;

  loadingProfile = false;
  saving = false;
  message = '';
  error = '';

  savedProfile: HealthProfile | null = null;

  constructor(
    private profileService: HealthProfileService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    void this.loadProfile();
  }

  async loadProfile(): Promise<void> {
    this.loadingProfile = true;
    this.error = '';
    this.message = '';

    try {
      const profile = await this.profileService.getMyProfile();

      this.savedProfile = profile;
      this.goals = profile.goals;
      this.dietaryPreferences = profile.dietary_preferences;
      this.dailyBudget = Number(profile.daily_budget);

      this.message = 'Your saved profile has been loaded.';
    } catch (err: unknown) {
      const e = err as {
        status?: number;
        error?: { detail?: string };
        message?: string;
      };

      if (e.status === 404) {
        this.message = 'No profile exists yet. Enter your details below.';
      } else {
        console.error('Profile load failed:', err);

        this.error =
          e.error?.detail ??
          e.message ??
          'Could not load profile. Check the API and try again.';
      }
    } finally {
      this.loadingProfile = false;
      this.cdr.markForCheck();
    }
  }

  async submit(): Promise<void> {
    this.error = '';
    this.message = '';

    if (
      !this.goals.trim() ||
      !this.dietaryPreferences.trim() ||
      this.dailyBudget === null ||
      !Number.isFinite(this.dailyBudget) ||
      this.dailyBudget <= 0
    ) {
      this.error = 'Enter all fields and a budget greater than zero.';
      return;
    }

    this.saving = true;
    this.cdr.markForCheck();

    try {
      this.savedProfile = await this.profileService.upsertMyProfile({
        goals: this.goals.trim(),
        dietary_preferences: this.dietaryPreferences.trim(),
        daily_budget: this.dailyBudget,
      });

      this.goals = this.savedProfile.goals;
      this.dietaryPreferences =
        this.savedProfile.dietary_preferences;
      this.dailyBudget = Number(this.savedProfile.daily_budget);

      this.message = 'Health profile saved successfully.';
    } catch (err: unknown) {
      const e = err as {
        status?: number;
        error?: { detail?: string };
        message?: string;
      };

      console.error('Profile save failed:', err);

      this.error =
        e.error?.detail ??
        e.message ??
        'Could not save profile. Check the API and try again.';
    } finally {
      this.saving = false;
      this.cdr.markForCheck();
    }
  }
}
