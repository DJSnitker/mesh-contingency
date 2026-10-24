import { Routes } from '@angular/router';

import { ChatList } from './chat/chat-list';
import { ChatScreen } from './chat/chat-screen';
import { CheckinsScreen } from './checkins/checkins-screen';
import { EmailScreen } from './email/email-screen';
import { MailboxScreen } from './mailbox/mailbox-screen';
import { NodeScreen } from './node/node-screen';
import { Planned } from './planned';
import { WeatherScreen } from './weather/weather-screen';

/**
 * The app's screens (docs/plans/mobile-app.md). Each is Planned until the PR
 * that builds it; its data says what it will do.
 */
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'node' },
  { path: 'node', component: NodeScreen, title: 'Node' },
  { path: 'mailbox', component: MailboxScreen, title: 'Mailbox' },
  { path: 'checkins', component: CheckinsScreen, title: 'Check-ins' },
  { path: 'chat', component: ChatList, title: 'Chat' },
  { path: 'chat/dm/:key', component: ChatScreen, title: 'Chat' },
  { path: 'chat/channel/:name', component: ChatScreen, title: 'Chat' },
  {
    path: 'radio',
    component: Planned,
    title: 'Radio',
    data: {
      icon: 'sliders',
      what: "Your own radio's name, power, position, clock, frequency and contacts.",
      pr: 'Radio',
    },
  },
  { path: 'email', component: EmailScreen, title: 'Email' },
  { path: 'weather', component: WeatherScreen, title: 'Weather and verse' },
  { path: '**', redirectTo: 'node' },
];

/** The tab bar, in order. Email and weather are reached from Node. */
export const TABS = [
  { path: '/node', label: 'Node', icon: 'radio' },
  { path: '/mailbox', label: 'Mailbox', icon: 'inbox' },
  { path: '/checkins', label: 'Check-ins', icon: 'check' },
  { path: '/chat', label: 'Chat', icon: 'chat' },
  { path: '/radio', label: 'Radio', icon: 'sliders' },
];
