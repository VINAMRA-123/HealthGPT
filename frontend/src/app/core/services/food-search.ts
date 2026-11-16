
import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

export interface FoodSearchResult {
  code: string | null;
  name: string;
  brands: string | null;
  quantity: string | null;
  basis: string;
  calories: number | null;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
}

export interface FoodSearchResponse {
  query: string;
  count: number;
  results: FoodSearchResult[];
}

@Injectable({
  providedIn: 'root',
})
export class FoodSearchService {
  private readonly apiUrl =
    'http://127.0.0.1:8000/api/v1/foods/search';

  constructor(private readonly http: HttpClient) {}

  async searchFoods(query: string): Promise<FoodSearchResult[]> {
    const params = new HttpParams().set('q', query.trim());

    const response = await firstValueFrom(
      this.http.get<FoodSearchResponse>(this.apiUrl, { params }),
    );

    return response.results;
  }
}
