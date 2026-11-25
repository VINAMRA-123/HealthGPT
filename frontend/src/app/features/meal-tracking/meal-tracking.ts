import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectorRef, Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  FoodSearchService,
  FoodSearchResult,
} from '../../core/services/food-search';
import {
  MealService,
  MealInput,
  Meal,
  DailyNutritionSummary,
} from '../../core/services/meal';

@Component({
  selector: 'app-meal-tracking',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './meal-tracking.html',
  styleUrl: './meal-tracking.css',
})
export class MealTrackingComponent implements OnInit {
  meals: Meal[] = [];
  summary: DailyNutritionSummary | null = null;

  loading = false;
  saving = false;
  error = '';
  message = '';
  editingMealId: number | null = null;
  form: MealInput = this.createEmptyForm();

  // ---- Food search -------------------------------------------------------
  foodQuery = '';
  foodResults: FoodSearchResult[] = [];
  selectedFood: FoodSearchResult | null = null;

  foodSearchLoading = false;
  foodLoadingMore = false;
  foodSearchError = '';
  foodSearchMessage = '';
  portionGrams = 100;

  /** Pages are fetched from the server one at a time. */
  readonly foodPageSize = 10;
  foodPage = 1;
  foodHasMore = false;

  private activeFoodQuery = '';
  /** Incremented per search so slow, outdated responses are ignored. */
  private foodSearchToken = 0;

  constructor(
    private readonly mealService: MealService,
    private readonly foodSearchService: FoodSearchService,
    private readonly cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    void this.loadData();
  }

  private createEmptyForm(): MealInput {
    return {
      food_name: '',
      meal_type: 'breakfast',
      portion: '1 serving',
      calories: 0,
      protein_g: 0,
      carbs_g: 0,
      fat_g: 0,
      cost: 0,
    };
  }

  // ---- Meals + daily summary ---------------------------------------------

  async loadData(): Promise<void> {
    this.loading = true;
    this.error = '';
    this.cdr.markForCheck();

    try {
      const [meals, summary] = await Promise.all([
        this.mealService.getMeals(),
        this.mealService.getDailySummary(),
      ]);

      this.meals = meals;
      this.summary = summary;
    } catch (err: unknown) {
      this.error = this.getErrorMessage(err);
    } finally {
      this.loading = false;
      this.cdr.markForCheck();
    }
  }

  /** Re-fetch only today's totals; the meal list is updated locally. */
  private async refreshSummary(): Promise<void> {
    try {
      this.summary = await this.mealService.getDailySummary();
    } catch {
      // Keep the numbers already on screen if the background refresh fails.
    } finally {
      this.cdr.markForCheck();
    }
  }

  async addMeal(): Promise<void> {
    this.error = '';
    this.message = '';

    const foodName = this.form.food_name.trim();
    const portion = this.form.portion.trim();

    if (!foodName || !portion) {
      this.error = 'Please enter both the food name and portion.';
      return;
    }

    const numericValues = [
      this.form.calories,
      this.form.protein_g,
      this.form.carbs_g,
      this.form.fat_g,
      this.form.cost,
    ];

    if (
      numericValues.some(
        value => !Number.isFinite(value) || value < 0 || value > 99999999,
      )
    ) {
      this.error = 'Enter valid, non-negative nutrition and cost values.';
      return;
    }

    const payload: MealInput = {
      ...this.form,
      food_name: foodName,
      portion,
    };

    this.saving = true;
    this.cdr.markForCheck();

    try {
      if (this.editingMealId !== null) {
        const updated = await this.mealService.updateMeal(
          this.editingMealId,
          payload,
        );

        // Update the row in place so the list changes immediately.
        this.meals = this.meals.map(meal =>
          meal.id === updated.id ? updated : meal,
        );
        this.message = 'Meal updated successfully.';
        this.editingMealId = null;
      } else {
        const saved = await this.mealService.addMeal(payload);

        // Show the new meal at the top without waiting for a full reload.
        this.meals = [saved, ...this.meals];
        this.message = 'Meal saved successfully!';
      }

      this.form = this.createEmptyForm();
      this.clearSelectedFood();

      // Refresh the totals in the background.
      void this.refreshSummary();
    } catch (err: unknown) {
      this.error = this.getErrorMessage(err);
    } finally {
      this.saving = false;
      this.cdr.markForCheck();
    }
  }

  editMeal(meal: Meal): void {
    this.editingMealId = meal.id;

    this.form = {
      food_name: meal.food_name,
      meal_type: meal.meal_type,
      portion: meal.portion,
      calories: Number(meal.calories),
      protein_g: Number(meal.protein_g),
      carbs_g: Number(meal.carbs_g),
      fat_g: Number(meal.fat_g),
      cost: Number(meal.cost),
    };

    this.clearSelectedFood();
    this.message = '';
    this.error = '';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  cancelEdit(): void {
    this.editingMealId = null;
    this.form = this.createEmptyForm();
    this.clearSelectedFood();
    this.error = '';
    this.message = '';
  }

  async deleteMeal(meal: Meal): Promise<void> {
    const confirmed = window.confirm(
      `Delete "${meal.food_name}"? This action cannot be undone.`,
    );

    if (!confirmed) {
      return;
    }

    this.error = '';
    this.message = '';

    try {
      await this.mealService.deleteMeal(meal.id);

      this.meals = this.meals.filter(item => item.id !== meal.id);
      this.message = 'Meal deleted successfully.';
      void this.refreshSummary();
    } catch (err: unknown) {
      this.error = this.getErrorMessage(err);
    } finally {
      this.cdr.markForCheck();
    }
  }

  // ---- Food search (server-side pagination) ------------------------------

  onFoodQueryEnter(event: Event): void {
    // Without this, Enter submits the surrounding meal form.
    event.preventDefault();
    void this.searchFoods();
  }

  async searchFoods(): Promise<void> {
    const query = this.foodQuery.trim();

    this.foodSearchError = '';
    this.foodSearchMessage = '';
    this.foodResults = [];
    this.foodPage = 1;
    this.foodHasMore = false;
    this.foodLoadingMore = false;

    if (query.length < 2) {
      this.foodSearchError = 'Enter at least 2 characters to search.';
      this.cdr.markForCheck();
      return;
    }

    const token = ++this.foodSearchToken;
    this.activeFoodQuery = query;
    this.foodSearchLoading = true;
    this.cdr.markForCheck();

    try {
      const response = await this.foodSearchService.searchFoodsPage(
        query,
        1,
        this.foodPageSize,
      );

      // A newer search has started; drop this outdated answer.
      if (token !== this.foodSearchToken) {
        return;
      }

      this.foodResults = response.results;
      this.foodHasMore = response.has_more;

      if (response.results.length === 0) {
        this.foodSearchMessage = response.degraded
          ? 'The online food database is slow or busy right now. Please try again in a moment.'
          : 'No matching foods found. Try another search.';
      } else if (response.degraded) {
        this.foodSearchMessage =
          'Showing built-in foods only because the online food database did not respond.';
      }
    } catch (err: unknown) {
      if (token === this.foodSearchToken) {
        this.foodSearchError = this.getErrorMessage(err);
      }
    } finally {
      if (token === this.foodSearchToken) {
        this.foodSearchLoading = false;
        this.cdr.markForCheck();
      }
    }
  }

  async loadMoreFoods(): Promise<void> {
    if (
      !this.foodHasMore ||
      this.foodLoadingMore ||
      this.foodSearchLoading
    ) {
      return;
    }

    const token = this.foodSearchToken;
    const nextPage = this.foodPage + 1;

    this.foodLoadingMore = true;
    this.foodSearchError = '';
    this.cdr.markForCheck();

    try {
      const response = await this.foodSearchService.searchFoodsPage(
        this.activeFoodQuery,
        nextPage,
        this.foodPageSize,
      );

      if (token !== this.foodSearchToken) {
        return;
      }

      const seen = new Set(this.foodResults.map(food => this.foodKey(food)));
      const fresh = response.results.filter(
        food => !seen.has(this.foodKey(food)),
      );

      this.foodResults = [...this.foodResults, ...fresh];
      this.foodPage = nextPage;
      this.foodHasMore = response.has_more;
    } catch (err: unknown) {
      if (token === this.foodSearchToken) {
        this.foodSearchError = this.getErrorMessage(err);
      }
    } finally {
      if (token === this.foodSearchToken) {
        this.foodLoadingMore = false;
        this.cdr.markForCheck();
      }
    }
  }

  /** Load the next page automatically when the list is scrolled near its end. */
  onFoodScroll(event: Event): void {
    const element = event.target as HTMLElement;
    const distanceFromBottom =
      element.scrollHeight - element.scrollTop - element.clientHeight;

    if (distanceFromBottom < 80) {
      void this.loadMoreFoods();
    }
  }

  foodKey(food: FoodSearchResult): string {
    return food.code
      ? `barcode:${food.code}`
      : `name:${food.name.toLowerCase()}`;
  }

  trackFood = (_: number, food: FoodSearchResult): string =>
    this.foodKey(food);

  trackMeal = (_: number, meal: Meal): number => meal.id;

  selectFood(food: FoodSearchResult): void {
    this.selectedFood = food;
    this.portionGrams = 100;

    this.form.food_name = food.name;
    this.form.portion = '100 g';

    this.updateNutritionForPortion();

    const missing = [
      food.calories,
      food.protein_g,
      food.carbs_g,
      food.fat_g,
    ].some(value => value === null || value === undefined);

    this.foodSearchMessage = missing
      ? 'Some nutrition data is missing. Verify those values before saving.'
      : 'Food selected. Nutrition values are for 100 g.';

    this.foodSearchError = '';
    this.message = '';
  }

  private clearSelectedFood(): void {
    this.selectedFood = null;
    this.portionGrams = 100;
  }

  updateNutritionForPortion(): void {
    if (!this.selectedFood) {
      return;
    }

    const grams = Number(this.portionGrams);

    if (!Number.isFinite(grams) || grams <= 0 || grams > 100000) {
      this.foodSearchError = 'Enter a portion between 1 and 100,000 grams.';
      return;
    }

    this.foodSearchError = '';
    this.form.portion = `${grams} g`;

    const factor = grams / 100;
    const food = this.selectedFood;

    if (food.calories !== null) {
      this.form.calories = Number((food.calories * factor).toFixed(2));
    }

    if (food.protein_g !== null) {
      this.form.protein_g = Number((food.protein_g * factor).toFixed(2));
    }

    if (food.carbs_g !== null) {
      this.form.carbs_g = Number((food.carbs_g * factor).toFixed(2));
    }

    if (food.fat_g !== null) {
      this.form.fat_g = Number((food.fat_g * factor).toFixed(2));
    }
  }

  private getErrorMessage(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      if (err.status === 401) {
        return 'Your session may have expired. Please sign in again.';
      }

      if (err.status === 0) {
        return 'Cannot reach the HealthGPT server. It may be waking up, so please try again in a few seconds.';
      }

      if (err.status === 422) {
        return 'Some details are invalid. Check the values and try again.';
      }

      if (err.status >= 500) {
        return 'The server could not process your request. Please try again.';
      }

      return err.error?.detail ?? 'The request failed. Please try again.';
    }

    if (err instanceof Error) {
      return err.message;
    }

    return 'Something went wrong. Please try again.';
  }
}
