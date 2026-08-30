import ArrowBack from '@mui/icons-material/ArrowBack';
import PolicyOutlined from '@mui/icons-material/PolicyOutlined';
import { Box, Button, Container, Divider, Link, Stack, Typography } from '@mui/material';
import type { ReactNode } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { PublicLayout } from '../components/PublicLayout';

const effectiveDate = 'August 29, 2026';

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <Box component="section" id={id} sx={{ scrollMarginTop: 24 }}>
      <Typography variant="h2" sx={{ mb: 1.5 }}>
        {title}
      </Typography>
      {children}
    </Box>
  );
}

function PolicyPage({
  title,
  links,
  children,
}: {
  title: string;
  links: [string, string][];
  children: ReactNode;
}) {
  return (
    <PublicLayout>
      <Container component="main" maxWidth="md" sx={{ py: { xs: 4, md: 7 }, flex: 1 }}>
        <Stack spacing={3}>
          <PolicyOutlined color="primary" fontSize="large" />
          <Typography component="h1" variant="h1">
            {title}
          </Typography>
          <Typography color="text.secondary">Effective {effectiveDate}.</Typography>
          <Stack
            component="nav"
            aria-label={`${title} sections`}
            direction="row"
            gap={2}
            flexWrap="wrap"
          >
            {links.map(([id, label]) => (
              <Link key={id} href={`#${id}`}>
                {label}
              </Link>
            ))}
          </Stack>
          <Divider />
          <Stack spacing={5}>{children}</Stack>
          <Button
            component={RouterLink}
            to="/research"
            startIcon={<ArrowBack />}
            sx={{ alignSelf: 'flex-start' }}
          >
            Return to application
          </Button>
        </Stack>
      </Container>
    </PublicLayout>
  );
}

export function Privacy() {
  return (
    <PolicyPage
      title="Privacy Policy"
      links={[
        ['information', 'Information we use'],
        ['sharing', 'How data moves'],
        ['cookies', 'Cookies and analytics'],
        ['retention', 'Retention and control'],
        ['rights', 'Your rights'],
      ]}
    >
      <Section id="information" title="Information we use">
        <Typography paragraph>
          Google supplies your verified name, email address, identity issuer, and account identifier
          when you sign in. We use them to create your account, manage a secure session, apply
          lifetime allowances, and administer access. Sessions expire and may be revoked when you
          sign out, your account is suspended, or an administrator responds to abuse.
        </Typography>
        <Typography>
          We retain questions, research settings, generated answers, feedback, cost records, audit
          events, and operational metadata needed to provide and protect the service. Administrators
          may review these records for operations, support, security, and abuse prevention.
        </Typography>
      </Section>
      <Section id="sharing" title="How data moves">
        <Typography paragraph>
          Your verified name and email remain within this application and are not sent to SEC EDGAR.
          Public filing requests are made to SEC services without your profile.
        </Typography>
        <Typography>
          Your questions and selected public filing passages are sent to the configured model
          provider to generate an answer. Infrastructure, identity, model, and filing providers
          process data under their own terms. Do not submit confidential, personal, or sensitive
          information in a research question.
        </Typography>
      </Section>
      <Section id="cookies" title="Cookies and analytics">
        <Typography paragraph>
          <strong>Necessary cookies</strong> operate authentication, OAuth state, CSRF protection,
          security, and cookie preferences. Session and CSRF cookies typically last for the
          configured account-session period; OAuth state is short-lived; the first-party consent
          preference lasts 180 days.
        </Typography>
        <Typography paragraph>
          <strong>Preference cookies</strong> remember choices such as optional-cookie consent.{' '}
          <strong>Analytics cookies</strong> are optional Google cookies (commonly <code>_ga</code>,
          up to two years, and shorter-lived <code>_gid</code>/<code>_gat</code>) used only after
          opt-in.
        </Typography>
        <Typography paragraph>
          When configured, Google Analytics 4 is loaded directly or through Google Tag Manager—not
          both—and Google processes analytics data. Before consent, no Google analytics or
          tag-manager script is loaded. You may reject or later withdraw analytics in Cookie
          settings without affecting sign-in, research, or corpus access; known Google analytics
          cookies are then cleared.
        </Typography>
        <Typography>
          We send normalized route names and basic page views or explicitly approved product events.
          We do not send URLs with query strings, research or filing identifiers, questions,
          tickers, email addresses, user IDs, or research content. Advertising features, Google
          Signals, ad personalization, marketing tags, and cross-service enrichment are disabled.
        </Typography>
      </Section>
      <Section id="retention" title="Retention, security, and control">
        <Typography>
          Records are retained for the operational life of this proof of concept unless an
          administrator deletes them, legal or security needs require longer retention, or technical
          backups expire on their normal schedule. We use access controls, secure cookies, request
          forgery protection, and audit records, but no online service can promise absolute
          security.
        </Typography>
      </Section>
      <Section id="rights" title="Your rights and contact">
        <Typography>
          Depending on your location, you may request access, correction, deletion, restriction,
          portability, or object to processing, withdraw consent, and complain to a data-protection
          authority. Direct requests and privacy questions to the application administrator.
          Identity verification may be required. See also the{' '}
          <Link component={RouterLink} to="/terms">
            Terms of Service
          </Link>
          .
        </Typography>
      </Section>
    </PolicyPage>
  );
}

export function Terms() {
  return (
    <PolicyPage
      title="Terms of Service"
      links={[
        ['account', 'Your account'],
        ['use', 'Acceptable use'],
        ['research', 'Research limitations'],
        ['proof-of-concept', 'Proof of concept'],
        ['disclaimer', 'No warranties'],
        ['liability', 'Liability'],
        ['service', 'Service terms'],
        ['changes', 'Changes'],
      ]}
    >
      <Section id="account" title="Your account and allowance">
        <Typography>
          You must use a verified Google account, provide accurate account information, protect
          access to it, and be legally able to accept these Terms. Access includes a configured
          lifetime cost allowance, not a recurring entitlement. The service may reject work when
          that allowance is exhausted.
        </Typography>
      </Section>
      <Section id="use" title="Acceptable use">
        <Typography>
          Use the service lawfully and only for authorized research. Do not evade allowances or
          access controls, disrupt the service, automate abusive traffic, probe other users’ data,
          upload secrets or personal data, infringe rights, or use outputs to facilitate harm.
          Administrators may investigate abuse and suspend or terminate access.
        </Typography>
      </Section>
      <Section id="research" title="Research limitations">
        <Typography paragraph>
          The service is an aid for inspecting public filings. It does not provide investment,
          legal, tax, accounting, or other professional advice. Verify every important statement
          against cited filings and qualified advisers before acting.
        </Typography>
        <Typography>
          Retrieval and language models can omit evidence, misunderstand text, or generate
          inaccurate conclusions. Filings can be incomplete or superseded. Sources, citations, and
          warnings help review; they do not guarantee correctness.
        </Typography>
      </Section>
      <Section id="proof-of-concept" title="Proof-of-concept status and assumption of risk">
        <Typography paragraph>
          This platform is an experimental proof of concept, not a finished production service.
          Important improvements—including additional testing, security hardening, accessibility,
          reliability, data governance, monitoring, and broader filing coverage—may still need to be
          designed or implemented. Features and results may change without notice.
        </Typography>
        <Typography>
          You are solely responsible for deciding whether the platform and its outputs are suitable
          for your purposes. You use the platform, rely on its outputs, and make any resulting
          decisions entirely at your own risk.
        </Typography>
      </Section>
      <Section id="disclaimer" title="No warranties or guarantees">
        <Typography paragraph>
          To the fullest extent permitted by applicable law, the platform and all outputs, sources,
          features, and services are provided “as is” and “as available,” without warranties,
          representations, conditions, or guarantees of any kind, whether express, implied, or
          statutory.
        </Typography>
        <Typography>
          In particular, neither the creator nor the operator guarantees completeness, accuracy,
          reliability, timeliness, availability, security, non-infringement, merchantability,
          fitness for a particular purpose, or that errors will be corrected. Citations and links
          may be missing, incorrect, unavailable, incomplete, or superseded. No information or
          assistance provided through the platform creates a warranty not expressly stated in these
          Terms.
        </Typography>
      </Section>
      <Section id="liability" title="Limitation of liability">
        <Typography paragraph>
          To the fullest extent permitted by applicable law, the creator, operator, contributors,
          and service providers will not be liable under any legal theory for losses or consequences
          arising from or related to your access to, use of, reliance on, or inability to use the
          platform or its outputs—even if advised that such harm was possible.
        </Typography>
        <Typography>
          This exclusion includes direct, indirect, incidental, special, exemplary, punitive, and
          consequential damages; lost profits, revenue, data, opportunities, goodwill, or business;
          and decisions or actions taken using platform output. Nothing in these Terms excludes or
          limits liability that applicable law does not permit to be excluded or limited.
        </Typography>
      </Section>
      <Section id="service" title="Third parties and availability">
        <Typography>
          Google identity, SEC EDGAR, EdgarTools, model providers, infrastructure, and other
          dependencies have separate terms and may fail or change. The service is provided as
          available without guaranteed uptime, completeness, fitness, or continued access. Features,
          allowances, and access may be changed, suspended, or discontinued for operations,
          security, abuse prevention, or legal reasons.
        </Typography>
      </Section>
      <Section id="changes" title="Policy changes">
        <Typography>
          We may revise these Terms and the Privacy Policy. Material changes will be presented
          through the service with a new effective date. Continued use after notice constitutes
          acceptance where permitted by law. If you disagree, stop using the service. Review the{' '}
          <Link component={RouterLink} to="/privacy">
            Privacy Policy
          </Link>{' '}
          for data practices.
        </Typography>
      </Section>
    </PolicyPage>
  );
}
