import { Routes } from '@angular/router';
import { authGuard, guestGuard } from './core/guards/auth.guard';

/**
 * Each page is loaded on demand, so the login screen downloads only its own
 * code instead of the whole app. This makes the first visit noticeably faster.
 */
export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    canActivate: [guestGuard],
    loadComponent: () =>
      import('./features/auth/auth').then(m => m.Auth),
  },
  {
    path: 'dashboard',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/dashboard/dashboard').then(
        m => m.DashboardComponent,
      ),
  },
  {
    path: 'profile',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/health-profile/health-profile').then(
        m => m.HealthProfileComponent,
      ),
  },
  {
    path: 'meals',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/meal-tracking/meal-tracking').then(
        m => m.MealTrackingComponent,
      ),
  },
  {
    path: 'chat',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/health-chat/health-chat').then(
        m => m.ChatComponent,
      ),
  },
  { path: '**', redirectTo: '' },
];
