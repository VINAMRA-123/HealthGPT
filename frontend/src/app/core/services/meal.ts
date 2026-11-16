
import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import { SupabaseAuthService } from '../../core/services/supabase-auth';

export type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack';



export interface WeeklyNutritionDay {
  date: string;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  cost: number;
  meal_count: number;
  calorie_target: number | null;
  calorie_progress_percent: number | null;
}

export interface WeeklyNutritionSummary {
  timezone: string;
  days: WeeklyNutritionDay[];
}

export interface MealInput {
  food_name: string;
  meal_type: MealType;
  portion: string;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  cost: number;
}

export interface Meal extends MealInput {
  id: number;
  consumed_at: string;
  created_at: string;
}


export interface DailyNutritionSummary {
  date: string;
  timezone: string;
  meal_count: number;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  cost: number;

  consumed: {
    calories: number;
    protein_g: number;
    carbs_g: number;
    fat_g: number;
  };

  targets: {
    calories: number | null;
    protein_g: number | null;
    carbs_g: number | null;
    fat_g: number | null;
  };

  remaining: {
    calories: number | null;
    protein_g: number | null;
    carbs_g: number | null;
    fat_g: number | null;
  };

  progress_percent: {
    calories: number | null;
    protein_g: number | null;
    carbs_g: number | null;
    fat_g: number | null;
  };
}


@Injectable({
  providedIn: 'root',
})
export class MealService {
  private readonly apiUrl = 'http://127.0.0.1:8000/api/v1/meals';

  constructor(
    private readonly http: HttpClient,
    private readonly authService: SupabaseAuthService,
  ) {}

  private async getHeaders(): Promise<HttpHeaders> {
    const token = await this.authService.getAccessToken();

    if (!token) {
      throw new Error('Please sign in to manage your meals.');
    }

    return new HttpHeaders({
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    });
  }

  async addMeal(meal: MealInput): Promise<Meal> {
    const headers = await this.getHeaders();

    return firstValueFrom(
      this.http.post<Meal>(this.apiUrl, meal, { headers }),
    );
  }

  async getMeals(limit = 50): Promise<Meal[]> {
    const headers = await this.getHeaders();

    return firstValueFrom(
      this.http.get<Meal[]>(this.apiUrl, {
        headers,
        params: { limit },
      }),
    );
  }

  async getDailySummary(): Promise<DailyNutritionSummary> {
    const headers = await this.getHeaders();

    return firstValueFrom(
      this.http.get<DailyNutritionSummary>(
        `${this.apiUrl}/daily-summary`,
        { headers },
      ),
    );
  }


async getWeeklySummary(): Promise<WeeklyNutritionSummary> {
  const headers = await this.getHeaders();

  return firstValueFrom(
    this.http.get<WeeklyNutritionSummary>(
      `${this.apiUrl}/weekly-summary`,
      { headers },
    ),
  );
}

  async updateMeal(id: number, meal: MealInput): Promise<Meal> {
  const headers = await this.getHeaders();

  return firstValueFrom(
    this.http.put<Meal>(`${this.apiUrl}/${id}`, meal, { headers }),
  );
}

async deleteMeal(id: number): Promise<void> {
  const headers = await this.getHeaders();

  return firstValueFrom(
    this.http.delete<void>(`${this.apiUrl}/${id}`, { headers }),
  );
}
}
