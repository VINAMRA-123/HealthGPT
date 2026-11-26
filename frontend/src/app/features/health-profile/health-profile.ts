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
import { DashboardCache } from '../../core/services/dashboard-cache';

/** Turns an API value (string, number or null) into a form-friendly number. */
function toNumberOrNull(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

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

  // Optional daily targets. Empty means "no target".
  caloriesTarget: number | null = null;
  proteinTarget: number | null = null;
  carbsTarget: number | null = null;
  fatTarget: number | null = null;

  loadingProfile = false;
  saving = false;
  message = '';
  error = '';

  savedProfile: HealthProfile | null = null;

  constructor(
    private profileService: HealthProfileService,
    private cdr: ChangeDetectorRef,
    private dashboardCache: DashboardCache,
  ) {}

  ngOnInit(): void {
    void this.loadProfile();
  }

  async loadProfile(): Promise<void> {
    this.loadingProfile = true;
    this.error = '';
    this.message = '';
    this.cdr.markForCheck();

    try {
      const profile = await this.profileService.getMyProfile();

      this.applyProfile(profile);
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

  private applyProfile(profile: HealthProfile): void {
    this.savedProfile = profile;
    this.goals = profile.goals;
    this.dietaryPreferences = profile.dietary_preferences;
    this.dailyBudget = Number(profile.daily_budget);
    this.caloriesTarget = toNumberOrNull(profile.daily_calories_target);
    this.proteinTarget = toNumberOrNull(profile.daily_protein_target_g);
    this.carbsTarget = toNumberOrNull(profile.daily_carbs_target_g);
    this.fatTarget = toNumberOrNull(profile.daily_fat_target_g);
  }

  /** Optional fields must be empty or a positive number. */
  private invalidTarget(value: number | null): boolean {
    return (
      value !== null &&
      (!Number.isFinite(value) || value <= 0 || value > 99999999)
    );
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

    // An emptied number input gives null (or an empty string) in Angular.
    const targets = [
      this.caloriesTarget,
      this.proteinTarget,
      this.carbsTarget,
      this.fatTarget,
    ].map(value => toNumberOrNull(value));

    if (targets.some(value => this.invalidTarget(value))) {
      this.error =
        'Daily targets must be a number greater than zero, or left empty.';
      return;
    }

    const [calories, protein, carbs, fat] = targets;

    this.saving = true;
    this.cdr.markForCheck();

    try {
      const saved = await this.profileService.upsertMyProfile({
        goals: this.goals.trim(),
        dietary_preferences: this.dietaryPreferences.trim(),
        daily_budget: this.dailyBudget,
        daily_calories_target: calories,
        daily_protein_target_g: protein,
        daily_carbs_target_g: carbs,
        daily_fat_target_g: fat,
      });

      this.applyProfile(saved);

      // The dashboard must not show numbers calculated from old targets.
      this.dashboardCache.clear();

      this.message = 'Health profile saved successfully.';
    } catch (err: unknown) {
      const e = err as {
        status?: number;
        error?: { detail?: string };
        message?: string;
      };

      console.error('Profile save failed:', err);

      this.error =
        e.status === 422
          ? 'Some values are invalid. Check the numbers and try again.'
          : e.error?.detail ??
            e.message ??
            'Could not save profile. Check the API and try again.';
    } finally {
      this.saving = false;
      this.cdr.markForCheck();
    }
  }
}
