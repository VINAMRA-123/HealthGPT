import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { environment } from '../environments/environments';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  constructor() {
    this.wakeUpApi();
  }

  /**
   * Free hosting tiers put the API to sleep when idle, and the first request
   * can then take 30-60 seconds. Pinging /health as soon as the app opens
   * starts the wake-up while the user is still on the login screen.
   */
  private wakeUpApi(): void {
    if (typeof fetch !== 'function') {
      return;
    }

    fetch(`${environment.apiBaseUrl}/health`, {
      mode: 'no-cors',
      cache: 'no-store',
    }).catch(() => undefined);
  }
}
