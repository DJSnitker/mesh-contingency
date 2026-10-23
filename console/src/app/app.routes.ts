import { Routes } from '@angular/router';

import { Dashboard } from './dashboard';

export const routes: Routes = [
  { path: '', component: Dashboard, title: 'Dashboard · Mesh Contingency' },
  { path: '**', redirectTo: '' },
];
