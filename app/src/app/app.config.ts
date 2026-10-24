import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter, withComponentInputBinding, withHashLocation } from '@angular/router';

import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // The app is opened from its own files on the phone, where only the
    // hash part of an address is the app's to change.
    provideRouter(routes, withHashLocation(), withComponentInputBinding()),
  ],
};
