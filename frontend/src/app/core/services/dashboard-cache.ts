import { Injectable } from '@angular/core';
import { HealthProfile } from './health-profile';
import { DailyNutritionSummary, WeeklyNutritionSummary } from './meal';

/**
 * Remembers the last dashboard data in memory so the page can paint
 * instantly when you come back to it, while fresh data loads in the
 * background (stale-while-revalidate). Cleared on sign-in and sign-out so
 * one user's numbers are never shown to another.
 */
@Injectable({
  providedIn: 'root',
})
export class DashboardCache {
  profile: HealthProfile | null = null;
  nutrition: DailyNutritionSummary | null = null;
  weekly: WeeklyNutritionSummary | null = null;

  clear(): void {
    this.profile = null;
    this.nutrition = null;
    this.weekly = null;
  }
}
