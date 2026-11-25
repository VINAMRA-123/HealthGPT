import { CommonModule } from '@angular/common';
import {
  ChangeDetectorRef,
  Component,
  OnDestroy,
  OnInit,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import {
  HealthProfileService,
  HealthProfile,
} from '../../core/services/health-profile';
import { SupabaseAuthService } from '../../core/services/supabase-auth';
import { DashboardCache } from '../../core/services/dashboard-cache';
import {
  MealService,
  DailyNutritionSummary,
  WeeklyNutritionSummary,
} from '../../core/services/meal';

type ChartMetric = 'calories' | 'cost' | 'protein_g' | 'carbs_g' | 'fat_g';

interface MetricOption {
  key: ChartMetric;
  label: string;
  color: string;
  digits: number;
}

interface ChartBar {
  date: string;
  heightPct: number;
  dayLabel: string;
  display: string;
  title: string;
  isToday: boolean;
}

interface MacroRow {
  label: string;
  cls: string;
  consumed: number;
  target: number | null;
  pct: number;
  note: string;
}

/** Data older than this is re-fetched when the tab becomes visible again. */
const STALE_AFTER_MS = 30_000;

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css',
})
export class DashboardComponent implements OnInit, OnDestroy {
  profile: HealthProfile | null = null;
  nutrition: DailyNutritionSummary | null = null;
  weeklyNutrition: WeeklyNutritionSummary | null = null;

  loading = true;
  nutritionLoading = true;
  weeklyLoading = true;
  refreshing = false;

  error = '';
  nutritionError = '';
  weeklyError = '';

  // ---- Calorie ring ------------------------------------------------------
  readonly ringRadius = 52;
  readonly ringCircumference = 2 * Math.PI * 52;

  // ---- Weekly chart ------------------------------------------------------
  readonly metrics: MetricOption[] = [
    { key: 'calories', label: 'Calories', color: 'var(--c-cal)', digits: 0 },
    { key: 'protein_g', label: 'Protein', color: 'var(--c-protein)', digits: 1 },
    { key: 'carbs_g', label: 'Carbs', color: 'var(--c-carbs)', digits: 1 },
    { key: 'fat_g', label: 'Fat', color: 'var(--c-fat)', digits: 1 },
    { key: 'cost', label: 'Spending', color: 'var(--c-cost)', digits: 0 },
  ];

  activeMetric: ChartMetric = 'calories';
  chartBars: ChartBar[] = [];
  chartTarget: number | null = null;
  chartTargetPct: number | null = null;
  chartSummary = '';
  chartHasData = false;

  macros: MacroRow[] = [];

  private lastLoadedAt = 0;
  private readonly numberFormats = new Map<number, Intl.NumberFormat>();

  constructor(
    private profileService: HealthProfileService,
    private mealService: MealService,
    private authService: SupabaseAuthService,
    private router: Router,
    private cdr: ChangeDetectorRef,
    private cache: DashboardCache,
  ) {}

  // ---- Lifecycle ---------------------------------------------------------

  ngOnInit(): void {
    // Paint the last known data immediately, then refresh in the background.
    if (this.cache.profile) {
      this.profile = this.cache.profile;
      this.nutrition = this.cache.nutrition;
      this.weeklyNutrition = this.cache.weekly;
      this.loading = false;
      this.nutritionLoading = false;
      this.weeklyLoading = false;
      this.rebuildMacros();
      this.rebuildChart();
    }

    document.addEventListener('visibilitychange', this.onVisibilityChange);
    void this.loadDashboard(true);
  }

  ngOnDestroy(): void {
    document.removeEventListener('visibilitychange', this.onVisibilityChange);
  }

  /** Coming back to the tab refreshes numbers that may have gone stale. */
  private readonly onVisibilityChange = (): void => {
    if (
      document.visibilityState === 'visible' &&
      this.profile &&
      Date.now() - this.lastLoadedAt > STALE_AFTER_MS
    ) {
      void this.loadDashboard(true);
    }
  };

  // ---- Loading -----------------------------------------------------------

  async refresh(): Promise<void> {
    if (this.refreshing) {
      return;
    }

    this.refreshing = true;
    this.cdr.markForCheck();

    try {
      await this.loadDashboard(true);
    } finally {
      this.refreshing = false;
      this.cdr.markForCheck();
    }
  }

  /**
   * Loads the profile, today's totals and the weekly trend at the same time.
   * With `silent` set and data already on screen, nothing flashes to a
   * loading state; the numbers simply update when they arrive.
   */
  async loadDashboard(silent = false): Promise<void> {
    const hasData = this.profile !== null;
    const quiet = silent && hasData;

    if (!quiet) {
      this.loading = true;
    }

    this.error = '';
    this.cdr.markForCheck();

    // Start all three requests together instead of one after the other.
    const nutritionDone = this.loadNutritionSummary(quiet);
    const weeklyDone = this.loadWeeklySummary(quiet);

    try {
      this.profile = await this.profileService.getMyProfile();
      this.cache.profile = this.profile;
    } catch (err: unknown) {
      const e = err as { status?: number };

      if (e.status === 404) {
        await this.router.navigate(['/profile']);
        return;
      }

      if (e.status === 401) {
        await this.router.navigate(['/']);
        return;
      }

      console.error('Dashboard load failed:', err);

      // If older data is already showing, keep it rather than an error.
      if (!hasData) {
        this.error = this.errorDetail(err, 'Could not load your dashboard.');
      }
    } finally {
      this.loading = false;
      this.cdr.markForCheck();
    }

    await Promise.all([nutritionDone, weeklyDone]);
    this.lastLoadedAt = Date.now();
  }

  async loadNutritionSummary(quiet = false): Promise<void> {
    if (!quiet) {
      this.nutritionLoading = true;
    }

    this.nutritionError = '';
    this.cdr.markForCheck();

    try {
      this.nutrition = await this.mealService.getDailySummary();
      this.cache.nutrition = this.nutrition;
      this.rebuildMacros();
    } catch (err: unknown) {
      console.error('Nutrition summary load failed:', err);

      if (!this.nutrition) {
        this.nutritionError = this.errorDetail(
          err,
          'Could not load today’s nutrition.',
        );
      }
    } finally {
      this.nutritionLoading = false;
      this.cdr.markForCheck();
    }
  }

  async loadWeeklySummary(quiet = false): Promise<void> {
    if (!quiet) {
      this.weeklyLoading = true;
    }

    this.weeklyError = '';
    this.cdr.markForCheck();

    try {
      this.weeklyNutrition = await this.mealService.getWeeklySummary();
      this.cache.weekly = this.weeklyNutrition;
      this.rebuildChart();
    } catch (err: unknown) {
      console.error('Weekly nutrition load failed:', err);

      if (!this.weeklyNutrition) {
        this.weeklyError = this.errorDetail(
          err,
          'Could not load weekly nutrition.',
        );
      }
    } finally {
      this.weeklyLoading = false;
      this.cdr.markForCheck();
    }
  }

  private errorDetail(err: unknown, fallback: string): string {
    const e = err as {
      status?: number;
      error?: { detail?: string };
      message?: string;
    };

    if (e.status === 0) {
      return 'Cannot reach the HealthGPT server. It may be waking up, so please try again in a few seconds.';
    }

    return e.error?.detail ?? e.message ?? fallback;
  }

  // ---- Navigation --------------------------------------------------------

  async signOut(): Promise<void> {
    const { error } = await this.authService.signOut();

    if (error) {
      this.error = error.message;
      this.cdr.markForCheck();
      return;
    }

    this.cache.clear();
    await this.router.navigate(['/']);
  }

  editProfile(): void {
    void this.router.navigate(['/profile']);
  }

  // ---- Display helpers ---------------------------------------------------

  get greeting(): string {
    const hour = new Date().getHours();

    if (hour < 12) {
      return 'Good morning';
    }

    return hour < 17 ? 'Good afternoon' : 'Good evening';
  }

  /** Formats a number for display; null/undefined become an em dash. */
  fmt(value: number | string | null | undefined, digits = 0): string {
    if (value === null || value === undefined || value === '') {
      return '—';
    }

    const num = Number(value);

    if (!Number.isFinite(num)) {
      return '—';
    }

    let formatter = this.numberFormats.get(digits);

    if (!formatter) {
      formatter = new Intl.NumberFormat('en-IN', {
        maximumFractionDigits: digits,
      });
      this.numberFormats.set(digits, formatter);
    }

    return formatter.format(num);
  }

  getProgressWidth(value: number | null | undefined): number {
    if (value == null || !Number.isFinite(Number(value))) {
      return 0;
    }

    return Math.min(Math.max(Number(value), 0), 100);
  }

  // ---- Calories ----------------------------------------------------------

  get calorieRingOffset(): number {
    const pct = this.getProgressWidth(
      this.nutrition?.progress_percent.calories,
    );

    return this.ringCircumference * (1 - pct / 100);
  }

  get calorieTarget(): number | null {
    const target = this.nutrition?.targets.calories;
    return target != null && Number(target) > 0 ? Number(target) : null;
  }

  get isOverCalories(): boolean {
    const target = this.calorieTarget;
    return target !== null && Number(this.nutrition?.consumed.calories) > target;
  }

  get calorieStatus(): string {
    const target = this.calorieTarget;

    if (target === null || !this.nutrition) {
      return 'No calorie target set';
    }

    const diff = target - Number(this.nutrition.consumed.calories);

    return diff >= 0
      ? `${this.fmt(diff)} kcal left`
      : `${this.fmt(-diff)} kcal over`;
  }

  // ---- Macros ------------------------------------------------------------

  private rebuildMacros(): void {
    const today = this.nutrition;

    if (!today) {
      this.macros = [];
      return;
    }

    const defs = [
      { key: 'protein_g', label: 'Protein', cls: 'protein' },
      { key: 'carbs_g', label: 'Carbs', cls: 'carbs' },
      { key: 'fat_g', label: 'Fat', cls: 'fat' },
    ] as const;

    this.macros = defs.map(def => {
      const consumed = Number(today.consumed[def.key]);
      const rawTarget = today.targets[def.key];
      const target =
        rawTarget != null && Number(rawTarget) > 0 ? Number(rawTarget) : null;
      const remaining = today.remaining[def.key];

      let note = 'Set a target in your profile';

      if (target !== null) {
        note =
          remaining != null && consumed <= target
            ? `${this.fmt(remaining, 1)} g remaining`
            : `${this.fmt(consumed - target, 1)} g over target`;
      }

      return {
        label: def.label,
        cls: def.cls,
        consumed,
        target,
        pct: this.getProgressWidth(today.progress_percent[def.key]),
        note,
      };
    });
  }

  // ---- Budget ------------------------------------------------------------

  get dailyBudget(): number {
    return Number(this.profile?.daily_budget ?? 0);
  }

  get spentToday(): number {
    return Number(this.nutrition?.cost ?? 0);
  }

  get budgetPct(): number {
    const budget = this.dailyBudget;

    return budget > 0
      ? this.getProgressWidth((this.spentToday / budget) * 100)
      : 0;
  }

  get budgetOver(): boolean {
    return this.dailyBudget > 0 && this.spentToday > this.dailyBudget;
  }

  get budgetNote(): string {
    const budget = this.dailyBudget;

    if (budget <= 0) {
      return 'Set a daily budget in your profile';
    }

    const diff = budget - this.spentToday;

    return diff >= 0
      ? `₹${this.fmt(diff, 2)} left of ₹${this.fmt(budget, 2)}`
      : `₹${this.fmt(-diff, 2)} over your ₹${this.fmt(budget, 2)} budget`;
  }

  // ---- Weekly chart ------------------------------------------------------

  get activeOption(): MetricOption {
    return (
      this.metrics.find(metric => metric.key === this.activeMetric) ??
      this.metrics[0]
    );
  }

  setMetric(key: ChartMetric): void {
    if (this.activeMetric === key) {
      return;
    }

    this.activeMetric = key;
    this.rebuildChart();
  }

  private rebuildChart(): void {
    const days = this.weeklyNutrition?.days ?? [];
    const option = this.activeOption;
    const isCost = option.key === 'cost';
    const values = days.map(day => Number(day[option.key]) || 0);

    // Only calories have a target line.
    const rawTarget =
      option.key === 'calories'
        ? days[days.length - 1]?.calorie_target ?? null
        : null;
    const target =
      rawTarget != null && Number(rawTarget) > 0 ? Number(rawTarget) : null;

    // Scale to the data itself so small and large values both look right.
    const scaleMax = Math.max(...values, target ?? 0, 1) * 1.1;

    this.chartBars = days.map((day, index) => {
      const value = values[index];
      const date = new Date(`${day.date}T00:00:00`);
      const shown = this.fmt(value, option.digits);

      return {
        date: day.date,
        heightPct: value > 0 ? Math.max((value / scaleMax) * 100, 2) : 0,
        dayLabel: date.toLocaleDateString('en-IN', { weekday: 'short' }),
        display: isCost ? `₹${shown}` : shown,
        title: `${date.toLocaleDateString('en-IN', {
          weekday: 'long',
          day: 'numeric',
          month: 'short',
        })}: ${isCost ? '₹' : ''}${shown}${
          option.key === 'calories'
            ? ' kcal'
            : isCost
              ? ''
              : ' g'
        }`,
        isToday: index === days.length - 1,
      };
    });

    this.chartTarget = target;
    this.chartTargetPct = target !== null ? (target / scaleMax) * 100 : null;
    this.chartHasData = values.some(value => value > 0);

    const total = values.reduce((sum, value) => sum + value, 0);
    const average = days.length > 0 ? total / days.length : 0;

    if (isCost) {
      this.chartSummary = `₹${this.fmt(total, 2)} spent this week`;
    } else if (option.key === 'calories') {
      this.chartSummary = `Average ${this.fmt(average)} kcal per day`;
    } else {
      this.chartSummary = `Average ${this.fmt(average, 1)} g per day`;
    }
  }

  trackByLabel = (_: number, item: { label: string }): string => item.label;

  trackByDate = (_: number, bar: ChartBar): string => bar.date;
}
