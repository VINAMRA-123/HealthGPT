import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, OnInit } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import {
  HealthProfileService,
  HealthProfile,
} from '../../core/services/health-profile';
import { SupabaseAuthService } from '../../core/services/supabase-auth';
import {
  MealService,
  DailyNutritionSummary,
  WeeklyNutritionSummary,
} from '../../core/services/meal';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css',
})
export class DashboardComponent implements OnInit {
  profile: HealthProfile | null = null;
  nutrition: DailyNutritionSummary | null = null;

  loading = true;
  nutritionLoading = true;
  error = '';
  nutritionError = '';
  readonly chartScale = 2500;
readonly Math = Math;

  weeklyNutrition: WeeklyNutritionSummary | null = null;
  weeklyLoading = true;
  weeklyError = '';


  constructor(
    private profileService: HealthProfileService,
    private mealService: MealService,
    private authService: SupabaseAuthService,
    private router: Router,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    void this.loadDashboard();
  }

  async loadDashboard(): Promise<void> {
  this.loading = true;
  this.error = '';

  try {
    this.profile = await this.profileService.getMyProfile();

await Promise.all([
  this.loadNutritionSummary(),
  this.loadWeeklySummary(),
]);
  } catch (err: unknown) {
    const e = err as {
      status?: number;
      error?: { detail?: string };
      message?: string;
    };

    if (e.status === 404) {
      await this.router.navigate(['/profile']);
      return;
    }

    if (e.status === 401) {
      await this.router.navigate(['/']);
      return;
    }

    console.error('Dashboard load failed:', err);
    this.error =
      e.error?.detail ?? e.message ?? 'Could not load your dashboard.';
  } finally {
  this.loading = false;
  this.cdr.detectChanges();
}
}


async loadNutritionSummary(): Promise<void> {
  this.nutritionLoading = true;
  this.nutritionError = '';

  try {
    this.nutrition = await this.mealService.getDailySummary();
  } catch (err: unknown) {
    const e = err as {
      status?: number;
      error?: { detail?: string };
      message?: string;
    };

    console.error('Nutrition summary load failed:', err);

    this.nutritionError =
      e.error?.detail ??
      e.message ??
      'Could not load today’s nutrition.';
  } finally {
    this.nutritionLoading = false;
    this.cdr.detectChanges();
  }
}


getProgressWidth(value: number | null | undefined): number {
  if (value == null || !Number.isFinite(value)) {
    return 0;
  }

  return Math.min(Math.max(value, 0), 100);
}

getBudgetRemaining(): number {
  const budget = Number(this.profile?.daily_budget ?? 0);
  const spent = Number(this.nutrition?.cost ?? 0);

  return Math.max(budget - spent, 0);
}

  async signOut(): Promise<void> {
    const { error } = await this.authService.signOut();

    if (error) {
      this.error = error.message;
      return;
    }

    await this.router.navigate(['/']);
  }

  editProfile(): void {
    void this.router.navigate(['/profile']);
  }


async loadWeeklySummary(): Promise<void> {
  this.weeklyLoading = true;
  this.weeklyError = '';

  try {
    this.weeklyNutrition = await this.mealService.getWeeklySummary();
  } catch (err: unknown) {
    const e = err as {
      error?: { detail?: string };
      message?: string;
    };

    console.error('Weekly nutrition load failed:', err);
    this.weeklyError =
      e.error?.detail ?? e.message ?? 'Could not load weekly nutrition.';
  } finally {
    this.weeklyLoading = false;
    this.cdr.detectChanges();
  }
}

getSpendingBarHeight(cost: number): number {
  if (!this.weeklyNutrition) {
    return 0;
  }

  const maxCost = Math.max(
    ...this.weeklyNutrition.days.map(day => day.cost),
    1,
  );

  return Math.max((cost / maxCost) * 100, 0);
}

getWeeklySpending(): number {
  return (
    this.weeklyNutrition?.days.reduce(
      (total, day) => total + day.cost,
      0,
    ) ?? 0
  );
}

getMacroBarHeight(
  value: number,
  macro: 'protein_g' | 'carbs_g' | 'fat_g',
): number {
  const days = this.weeklyNutrition?.days;

  if (!days?.length) return 0;

  const maxValue = Math.max(...days.map(day => day[macro]), 1);

  return Math.max((value / maxValue) * 100, 0);
}
}