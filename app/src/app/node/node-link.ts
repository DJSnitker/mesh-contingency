import { DestroyRef, inject, Injectable, signal } from '@angular/core';

import { DirectMessage, Radio, RadioContact } from '../radio/radio';
import { Join, parseJoin, parseNotice, parseWhoami, reassemble, WhoAmI } from './replies';

/** How long the node has to start answering (ms): minutes, over several hops. */
export const FIRST_REPLY_MS = 180_000;
/** After a message that isn't numbered, how long to wait for more (ms). */
export const QUIET_MS = 10_000;
/** After a numbered part, how long to wait for the rest (ms). */
export const PARTS_MS = 90_000;
/** Where the chosen node is remembered. */
export const CHOSEN = 'mc.node';
/** Notices kept on the screen. */
export const MAX_NOTICES = 20;

/** The node, as the app remembers it: its full key and its name. */
export interface ChosenNode {
  publicKey: string;
  name: string;
}

export type Step = 'sending' | 'waiting' | 'answered' | 'not delivered' | 'no answer' | 'failed';

/** A command sent to the node, and how its answer is going. */
export interface Exchange {
  /** What the screen shows for the command (never a passphrase). */
  label: string;
  step: Step;
  attempt: number;
  /** The node's messages so far, as they came. */
  messages: string[];
  /** The reply put back together, once answered. */
  text: string | null;
}

/** A message from the node that isn't a reply. */
export interface NodeNotice {
  text: string;
  at: number;
}

/**
 * The node, reached through the user's radio by direct messages: the
 * commands the app sends it, one at a time, and what it sends back. Only
 * messages from the node's key are read as replies or notices.
 */
@Injectable({ providedIn: 'root' })
export class NodeLink {
  private readonly radio = inject(Radio);

  readonly node = signal<ChosenNode | null>(this.remembered());
  /** The command in flight, or the last one. */
  readonly exchange = signal<Exchange | null>(null);
  readonly notices = signal<NodeNotice[]>([]);
  /** What the last whoami said, if the app could read it. */
  readonly whoami = signal<WhoAmI | null>(null);
  /**
   * The last whoami got no answer: the node answers someone who isn't a
   * user only once every 5 minutes, so it's likely they aren't one.
   */
  readonly unanswered = signal(false);
  /** What the last join said, if the app could read it. */
  readonly joined = signal<Join | null>(null);

  private queue: Promise<unknown> = Promise.resolve();
  /** Hears the node's messages while a command waits for its answer. */
  private collector: ((text: string) => void) | null = null;

  constructor() {
    const subscription = this.radio.messages.subscribe((message) => this.heard(message));
    inject(DestroyRef).onDestroy(() => subscription.unsubscribe());
  }

  choose(contact: RadioContact): void {
    const node = { publicKey: contact.publicKey, name: contact.name };
    this.node.set(node);
    this.forgetAnswers();
    try {
      localStorage.setItem(CHOSEN, JSON.stringify(node));
    } catch {
      // Then it's picked again next time.
    }
  }

  /** Ask the node whether the user is one of its users. */
  async check(): Promise<void> {
    const exchange = await this.ask('whoami', { one: true });
    this.whoami.set(exchange.text ? parseWhoami(exchange.text) : null);
    this.unanswered.set(exchange.step === 'no answer');
  }

  /** Ask the admins to make the user a user. */
  async join(): Promise<void> {
    const exchange = await this.ask('join', { one: true });
    this.joined.set(exchange.text ? parseJoin(exchange.text) : null);
  }

  /** Pick a different node. */
  unchoose(): void {
    this.node.set(null);
    this.forgetAnswers();
    try {
      localStorage.removeItem(CHOSEN);
    } catch {
      // Nothing was stored, then.
    }
  }

  /**
   * Send the node a command and wait for its answer. `one`: the command
   * answers in one message, so there's no waiting for more. `label` is what
   * the screen shows for it, when the command itself shouldn't be.
   */
  ask(command: string, options: { one?: boolean; label?: string } = {}): Promise<Exchange> {
    const run = this.queue.then(() =>
      this.send(command, options.one ?? false, options.label ?? command),
    );
    this.queue = run.catch(() => undefined);
    return run;
  }

  private async send(command: string, one: boolean, label: string): Promise<Exchange> {
    const node = this.node();
    let exchange: Exchange = { label, step: 'sending', attempt: 1, messages: [], text: null };
    const update = (change: Partial<Exchange>) => {
      exchange = { ...exchange, ...change };
      this.exchange.set(exchange);
    };
    update({});
    if (!node) {
      update({ step: 'failed', text: 'Pick the node first.' });
      return exchange;
    }

    // Listen before sending: a near node can answer before the
    // acknowledgement is in.
    let finish: (step: Step) => void = () => undefined;
    const answered = new Promise<Step>((resolve) => (finish = resolve));
    let timer = setTimeout(
      () => finish(exchange.messages.length ? 'answered' : 'no answer'),
      FIRST_REPLY_MS,
    );
    const wait = (ms: number) => {
      clearTimeout(timer);
      timer = setTimeout(() => finish('answered'), ms);
    };
    this.collector = (text) => {
      update({ messages: [...exchange.messages, text] });
      const whole = reassemble(exchange.messages);
      if (whole.numbered) {
        if (whole.complete) {
          finish('answered');
        } else {
          wait(PARTS_MS);
        }
      } else if (one) {
        finish('answered');
      } else {
        wait(QUIET_MS);
      }
    };

    try {
      const delivered = await this.radio.sendText(node.publicKey, command, (attempt) =>
        update({ attempt }),
      );
      if (!delivered && !exchange.messages.length) {
        finish('not delivered');
      } else if (exchange.step === 'sending') {
        update({ step: 'waiting' });
      }
      const step = await answered;
      update({ step, text: exchange.messages.length ? reassemble(exchange.messages).text : null });
    } catch (error) {
      update({ step: 'failed', text: error instanceof Error ? error.message : String(error) });
    } finally {
      clearTimeout(timer);
      this.collector = null;
    }
    return exchange;
  }

  private forgetAnswers(): void {
    this.exchange.set(null);
    this.whoami.set(null);
    this.unanswered.set(false);
    this.joined.set(null);
  }

  private heard(message: DirectMessage): void {
    const node = this.node();
    if (!node || !node.publicKey.startsWith(message.from)) {
      return; // someone else: the Chat step's
    }
    const notice = parseNotice(message.text);
    if (this.collector && !notice) {
      this.collector(message.text);
    } else {
      if (notice?.notice === 'welcome') {
        // Approved: see what the node knows now.
        void this.check();
      }
      this.notices.update((notices) =>
        [{ text: message.text, at: message.receivedAt }, ...notices].slice(0, MAX_NOTICES),
      );
    }
  }

  private remembered(): ChosenNode | null {
    try {
      const stored = JSON.parse(localStorage.getItem(CHOSEN) ?? 'null');
      return typeof stored?.publicKey === 'string' && typeof stored?.name === 'string'
        ? stored
        : null;
    } catch {
      return null;
    }
  }
}
