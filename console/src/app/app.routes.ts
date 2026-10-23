import { Routes } from '@angular/router';

import { Checkins } from './checkins';
import { Dashboard } from './dashboard';
import { History } from './history';
import { Inbox } from './inbox';
import { Users } from './users';

export const routes: Routes = [
  { path: '', component: Dashboard, title: 'Dashboard · Mesh Contingency' },
  { path: 'users', component: Users, title: 'Users · Mesh Contingency' },
  { path: 'checkins', component: Checkins, title: 'Check-ins · Mesh Contingency' },
  { path: 'inbox', component: Inbox, title: 'Inbox · Mesh Contingency' },
  { path: 'history', component: History, title: 'History · Mesh Contingency' },
  { path: '**', redirectTo: '' },
];
