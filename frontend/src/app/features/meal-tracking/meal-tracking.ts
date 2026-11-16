import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit } from '@angular/core';
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
  foodQuery = '';
  foodResults: FoodSearchResult[] = [];
  selectedFood: FoodSearchResult | null = null;

  foodSearchLoading = false;
  foodSearchError = '';
  foodSearchMessage = '';
  portionGrams = 100;

  constructor(private readonly mealService: MealService,private readonly foodSearchService: FoodSearchService) {}

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

  async loadData(): Promise<void> {
    this.loading = true;
    this.error = '';

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

  try {
    if (this.editingMealId !== null) {
      await this.mealService.updateMeal(this.editingMealId, payload);
      this.message = 'Meal updated successfully.';
      this.editingMealId = null;
    } else {
      await this.mealService.addMeal(payload);
      this.message = 'Meal saved successfully!';
    }

    this.form = this.createEmptyForm();
    await this.loadData();
  } catch (err: unknown) {
    this.error = this.getErrorMessage(err);
  } finally {
    this.saving = false;
  }
}

  private getErrorMessage(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      if (err.status === 401) {
        return 'Your session may have expired. Please sign in again.';
      }

      if (err.status === 0) {
        return 'Cannot connect to HealthGPT API. Check that FastAPI is running on port 8000.';
      }

      if (err.status === 422) {
        return 'Some meal details are invalid. Check the values and try again.';
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

  this.message = '';
  this.error = '';
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

cancelEdit(): void {
  this.editingMealId = null;
  this.form = this.createEmptyForm();
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
    this.message = 'Meal deleted successfully.';
    await this.loadData();
  } catch (err: unknown) {
    this.error = this.getErrorMessage(err);
  }
}
async searchFoods(): Promise<void> {
  const query = this.foodQuery.trim();

  this.foodSearchError = '';
  this.foodSearchMessage = '';
  this.foodResults = [];

  if (query.length < 2) {
    this.foodSearchError = 'Enter at least 2 characters to search.';
    return;
  }

  this.foodSearchLoading = true;

  try {
    this.foodResults = await this.foodSearchService.searchFoods(query);

    if (this.foodResults.length === 0) {
      this.foodSearchMessage = 'No matching foods found. Try another search.';
    }
  } catch (err: unknown) {
    this.foodSearchError = this.getErrorMessage(err);
  } finally {
    this.foodSearchLoading = false;
  }
}

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
}
