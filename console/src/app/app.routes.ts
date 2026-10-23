import { Routes } from '@angular/router';

import { Dashboard } from './dashboard';
import { Users } from './users';

export const routes: Routes = [
  { path: '', component: Dashboard, title: 'Dashboard · Mesh Contingency' },
  { path: 'users', component: Users, title: 'Users · Mesh Contingency' },
  { path: '**', redirectTo: '' },
];
