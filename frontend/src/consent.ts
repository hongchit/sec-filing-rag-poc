import * as CookieConsent from 'vanilla-cookieconsent';
import 'vanilla-cookieconsent/dist/cookieconsent.css';
import { disableAnalytics, enableAnalytics } from './analytics';

const analyticsCookies = [{ name: /^_ga/ }, { name: '_gid' }, { name: '_gat' }];

export function initializeConsent(): void {
  const applyConsent = () => {
    if (CookieConsent.acceptedCategory('analytics')) enableAnalytics();
    else if (disableAnalytics()) window.location.reload();
  };
  void CookieConsent.run({
    revision: 1,
    cookie: { name: 'sec_research_consent', expiresAfterDays: 180, sameSite: 'Lax' },
    guiOptions: {
      consentModal: {
        layout: 'box',
        position: 'bottom center',
        equalWeightButtons: true,
        flipButtons: false,
      },
      preferencesModal: { layout: 'box', equalWeightButtons: true, flipButtons: false },
    },
    categories: {
      necessary: { enabled: true, readOnly: true },
      analytics: { enabled: false, readOnly: false, autoClear: { cookies: analyticsCookies } },
    },
    onConsent: applyConsent,
    onChange: applyConsent,
    language: {
      default: 'en',
      translations: {
        en: {
          consentModal: {
            title: 'Your cookie choices',
            description:
              'We use necessary cookies to operate securely. With your permission, analytics cookies help us understand basic site use. Optional cookies never affect sign-in or research.',
            acceptAllBtn: 'Accept all',
            acceptNecessaryBtn: 'Reject optional',
            showPreferencesBtn: 'Manage preferences',
          },
          preferencesModal: {
            title: 'Cookie preferences',
            acceptAllBtn: 'Accept all',
            acceptNecessaryBtn: 'Reject optional',
            savePreferencesBtn: 'Save preferences',
            closeIconLabel: 'Close preferences',
            sections: [
              {
                title: 'About these choices',
                description:
                  'These controls provide a choice and script-blocking mechanism; they do not by themselves guarantee legal compliance.',
              },
              {
                title: 'Necessary cookies',
                description:
                  'Required for secure sessions, CSRF protection, and remembering your cookie choice.',
                linkedCategory: 'necessary',
              },
              {
                title: 'Analytics cookies',
                description:
                  'Optional Google Analytics 4 or Google Tag Manager measurement using normalized routes and approved product events only.',
                linkedCategory: 'analytics',
              },
            ],
          },
        },
      },
    },
  });
}

export function showCookiePreferences(): void {
  CookieConsent.showPreferences();
}
