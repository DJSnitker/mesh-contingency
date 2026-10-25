import { ChangeDetectionStrategy, Component, input } from '@angular/core';

// Stroke icons, 24x24, drawn in currentColor, as the marketing site's.
@Component({
  selector: 'mc-icon',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { 'aria-hidden': 'true' },
  styles: `
    :host {
      display: inline-flex;
      width: 1.25em;
      height: 1.25em;
      flex: none;
    }
    svg {
      width: 100%;
      height: 100%;
    }
  `,
  template: `
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.75"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      @switch (name()) {
        @case ('gauge') {
          <path d="M4.5 18a9 9 0 1 1 15 0" />
          <path d="m12 14 4-5" />
          <circle cx="12" cy="14" r="1.2" />
        }
        @case ('users') {
          <circle cx="9" cy="8" r="3.5" />
          <path d="M2.5 20a6.5 6.5 0 0 1 13 0" />
          <path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14a6.5 6.5 0 0 1 3.5 6" />
        }
        @case ('check') {
          <circle cx="12" cy="12" r="9" />
          <path d="m8 12.5 2.6 2.5L16 9.5" />
        }
        @case ('inbox') {
          <path d="M4 13V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v7" />
          <path d="M4 13h4l1.5 3h5L16 13h4v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z" />
        }
        @case ('radio') {
          <rect x="6" y="8" width="12" height="14" rx="2" />
          <path d="M9 8V2" />
          <path d="M9 13h6M9 17h6" />
        }
        @case ('alert') {
          <path
            d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"
          />
          <path d="M12 9v4M12 17h.01" />
        }
        @case ('archive') {
          <rect x="3" y="4" width="18" height="4" rx="1" />
          <path d="M5 8v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8M10 12h4" />
        }
        @case ('terminal') {
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <path d="m7 9 3 3-3 3M13 15h4" />
        }
        @case ('list') {
          <path d="M9 6h11M9 12h11M9 18h11" />
          <circle cx="4.5" cy="6" r="1" />
          <circle cx="4.5" cy="12" r="1" />
          <circle cx="4.5" cy="18" r="1" />
        }
        @case ('clock') {
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        }
        @case ('cloud') {
          <path d="M7 18h10a4 4 0 0 0 .5-7.97A6 6 0 0 0 6.1 9.5 4.25 4.25 0 0 0 7 18z" />
        }
        @case ('sliders') {
          <path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12" />
          <circle cx="16" cy="6" r="2" />
          <circle cx="10" cy="12" r="2" />
          <circle cx="18" cy="18" r="2" />
        }
        @case ('send') {
          <path d="M21 3 10 14" />
          <path d="m21 3-7 18-4-7-7-4z" />
        }
        @case ('chat') {
          <path d="M20 12a8 8 0 0 1-11.5 7.2L4 20l1-4.2A8 8 0 1 1 20 12z" />
          <path d="M8.5 12h.01M12 12h.01M15.5 12h.01" />
        }
        @case ('mail') {
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <path d="m3 7 9 6 9-6" />
        }
        @case ('book') {
          <path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2Z" />
          <path d="M4 21V5M19 19v2H6M12 7v6M9.5 9.5h5" />
        }
        @case ('star') {
          <path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9Z" />
        }
        @case ('star-filled') {
          <path
            d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9Z"
            fill="currentColor"
          />
        }
        @case ('lock') {
          <rect x="5" y="11" width="14" height="10" rx="2" />
          <path d="M8 11V8a4 4 0 0 1 8 0v3" />
          <circle cx="12" cy="16" r="1.2" />
        }
      }
    </svg>
  `,
})
export class Icon {
  readonly name = input.required<string>();
}
