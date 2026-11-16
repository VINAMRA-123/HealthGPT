
import { Routes } from '@angular/router';
import { Auth } from './features/auth/auth';
import { HealthProfileComponent } from './features/health-profile/health-profile';
import { DashboardComponent } from './features/dashboard/dashboard';
import { MealTrackingComponent } from './features/meal-tracking/meal-tracking';
import { ChatComponent } from './features/health-chat/health-chat';

export const routes: Routes = [
  { path: '', component: Auth },
  { path: 'dashboard', component: DashboardComponent },
  { path: 'profile', component: HealthProfileComponent },
  { path: 'meals', component: MealTrackingComponent },
  { path: 'chat', component: ChatComponent },
  { path: '**', redirectTo: '' },

];