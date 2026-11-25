import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environments';

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
  source?: string;
  is_estimate?: boolean;
}

export interface FoodSearchResponse {
  query: string;
  page: number;
  page_size: number;
  count: number;
  has_more: boolean;
  /** True when the online food database could not be reached. */
  degraded: boolean;
  results: FoodSearchResult[];
}

@Injectable({
  providedIn: 'root',
})
export class FoodSearchService {
  private readonly apiUrl =
    `${environment.apiBaseUrl}/api/v1/foods/search`;

  constructor(private readonly http: HttpClient) {}

  /** Fetch one page of results. Page numbers start at 1. */
  searchFoodsPage(
    query: string,
    page = 1,
    pageSize = 10,
  ): Promise<FoodSearchResponse> {
    const params = new HttpParams()
      .set('q', query.trim())
      .set('page', page)
      .set('page_size', pageSize);

    return firstValueFrom(
      this.http.get<FoodSearchResponse>(this.apiUrl, { params }),
    );
  }

  /** Kept for backwards compatibility with older callers. */
  async searchFoods(query: string): Promise<FoodSearchResult[]> {
    const response = await this.searchFoodsPage(query, 1, 10);
    return response.results;
  }
}
