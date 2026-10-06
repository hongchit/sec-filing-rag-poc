import ArrowBack from '@mui/icons-material/ArrowBack';
import PolicyOutlined from '@mui/icons-material/PolicyOutlined';
import { Box, Button, Container, Divider, Link, Stack, Typography } from '@mui/material';
import type { ReactNode } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { PublicLayout } from '../components/PublicLayout';

const effectiveDate = 'October 6, 2026';

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
        ['information', 'Information we collect'],
        ['sharing', 'Service providers'],
        ['cookies', 'Cookies and analytics'],
        ['retention', 'Retention and security'],
        ['rights', 'Choices and rights'],
      ]}
    >
      <Section id="information" title="Information we collect and use">
        <Typography>
          We collect basic account information when you sign in, information you submit while using
          the service, and records created through that use. We use this information to provide the
          service, manage access, understand performance, address problems, and protect the project
          from misuse.
        </Typography>
      </Section>
      <Section id="sharing" title="Service providers">
        <Typography>
          This project relies on third-party services for sign-in, public filing access, AI-powered
          answers, analytics, and hosting. Information needed to provide a feature may be processed
          by the relevant provider under its own terms. Do not submit confidential, personal, or
          sensitive information in a research question.
        </Typography>
      </Section>
      <Section id="cookies" title="Cookies and analytics">
        <Typography>
          We use necessary cookies to operate the service securely and remember your choices. With
          your permission, optional analytics help us understand general traffic and feature usage.
          Analytics is not used for advertising and is configured to avoid sending account details
          or research content. You may decline or withdraw analytics consent without affecting the
          core service.
        </Typography>
      </Section>
      <Section id="retention" title="Retention and security">
        <Typography>
          We retain information for as long as reasonably needed to operate this portfolio project,
          resolve problems, and meet security or legal obligations. We use reasonable safeguards,
          but no online service can guarantee absolute security.
        </Typography>
      </Section>
      <Section id="rights" title="Your choices and rights">
        <Typography>
          You may manage optional cookies through Cookie settings and contact the application
          administrator with privacy questions or requests concerning your information. Additional
          rights may apply depending on your location. See also the{' '}
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
