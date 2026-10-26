import { Routes } from '@angular/router';

import { AreaWeather } from './area-weather';
import { Bible } from './bible';
import { ChannelThread } from './channel';
import { Channels } from './channels';
import { Checkins } from './checkins';
import { Contacts } from './contacts';
import { Dashboard } from './dashboard';
import { History } from './history';
import { Mailbox } from './mailbox';
import { More } from './more';
import { Radio } from './radio';
import { Users } from './users';

export const routes: Routes = [
  { path: '', component: Dashboard, title: 'Dashboard · Mesh Contingency' },
  { path: 'mailbox', component: Mailbox, title: 'Mailbox · Mesh Contingency' },
  { path: 'checkins', component: Checkins, title: 'Check-ins · Mesh Contingency' },
  { path: 'contacts', pathMatch: 'full', redirectTo: 'contacts/channels' },
  { path: 'contacts/channels', component: Channels, title: 'Channels · Mesh Contingency' },
  {
    path: 'contacts/channel/:slot',
    component: ChannelThread,
    title: 'Channels · Mesh Contingency',
  },
  { path: 'contacts/list', component: Contacts, title: 'Contacts · Mesh Contingency' },
  { path: 'weather', component: AreaWeather, title: 'Weather · Mesh Contingency' },
  { path: 'bible', component: Bible, title: 'Bible · Mesh Contingency' },
  { path: 'radio', component: Radio, title: 'Radio · Mesh Contingency' },
  { path: 'users', component: Users, title: 'Users · Mesh Contingency' },
  { path: 'history', component: History, title: 'History · Mesh Contingency' },
  { path: 'more', component: More, title: 'More · Mesh Contingency' },
  // The pages before the console was laid out like the phone app.
  { path: 'inbox', redirectTo: 'mailbox' },
  { path: 'send', redirectTo: 'contacts/channels' },
  { path: '**', redirectTo: '' },
];
