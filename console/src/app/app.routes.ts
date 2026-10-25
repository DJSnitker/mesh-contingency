import { Routes } from '@angular/router';

import { AreaWeather } from './area-weather';
import { Bible } from './bible';
import { ChannelThread } from './channel';
import { Chat } from './chat';
import { Checkins } from './checkins';
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
  { path: 'chat', component: Chat, title: 'Chat · Mesh Contingency' },
  { path: 'chat/channel/:slot', component: ChannelThread, title: 'Chat · Mesh Contingency' },
  { path: 'weather', component: AreaWeather, title: 'Weather · Mesh Contingency' },
  { path: 'bible', component: Bible, title: 'Bible · Mesh Contingency' },
  { path: 'radio', component: Radio, title: 'Radio · Mesh Contingency' },
  { path: 'users', component: Users, title: 'Users · Mesh Contingency' },
  { path: 'history', component: History, title: 'History · Mesh Contingency' },
  { path: 'more', component: More, title: 'More · Mesh Contingency' },
  // The pages before the console was laid out like the phone app.
  { path: 'inbox', redirectTo: 'mailbox' },
  { path: 'send', redirectTo: 'chat' },
  { path: '**', redirectTo: '' },
];
