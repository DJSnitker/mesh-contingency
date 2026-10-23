import { Routes } from '@angular/router';

import { AreaWeather } from './area-weather';
import { Checkins } from './checkins';
import { Dashboard } from './dashboard';
import { History } from './history';
import { Inbox } from './inbox';
import { Radio } from './radio';
import { Send } from './send';
import { Users } from './users';

export const routes: Routes = [
  { path: '', component: Dashboard, title: 'Dashboard · Mesh Contingency' },
  { path: 'weather', component: AreaWeather, title: 'Area Weather · Mesh Contingency' },
  { path: 'users', component: Users, title: 'Users · Mesh Contingency' },
  { path: 'checkins', component: Checkins, title: 'Check-ins · Mesh Contingency' },
  { path: 'inbox', component: Inbox, title: 'Inbox · Mesh Contingency' },
  { path: 'history', component: History, title: 'History · Mesh Contingency' },
  { path: 'send', component: Send, title: 'Send · Mesh Contingency' },
  { path: 'radio', component: Radio, title: 'Radio · Mesh Contingency' },
  { path: '**', redirectTo: '' },
];
