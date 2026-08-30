BEGIN;

CREATE TYPE public.user_status AS ENUM ('active', 'disabled');
CREATE TYPE public.cost_action_kind AS ENUM ('research', 'corpus_preparation');
CREATE TYPE public.cost_action_status AS ENUM ('reserved', 'reconciled', 'indeterminate');

CREATE TABLE public.app_user (
  id uuid PRIMARY KEY,
  oidc_issuer text NOT NULL,
  oidc_subject text NOT NULL,
  email text,
  email_verified boolean NOT NULL DEFAULT false,
  display_name text,
  status public.user_status NOT NULL DEFAULT 'active',
  lifetime_budget_override_usd numeric(18,8)
    CHECK (lifetime_budget_override_usd IS NULL OR lifetime_budget_override_usd >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  last_login_at timestamptz,
  UNIQUE (oidc_issuer, oidc_subject)
);

INSERT INTO public.app_user(
  id, oidc_issuer, oidc_subject, display_name, status
) VALUES (
  '00000000-0000-0000-0000-000000000001', 'legacy', 'pre-authentication',
  'Legacy pre-authentication activity', 'disabled'
);

CREATE TABLE public.auth_session (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES public.app_user(id) ON DELETE CASCADE,
  token_sha256 char(64) NOT NULL UNIQUE,
  csrf_token_sha256 char(64) NOT NULL,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz
);
CREATE INDEX auth_session_user_active
  ON public.auth_session(user_id, expires_at DESC) WHERE revoked_at IS NULL;

ALTER TABLE public.research_request
  ADD COLUMN user_id uuid REFERENCES public.app_user(id);
UPDATE public.research_request
   SET user_id = '00000000-0000-0000-0000-000000000001'
 WHERE user_id IS NULL;
ALTER TABLE public.research_request ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.research_request DROP CONSTRAINT IF EXISTS research_request_idempotency_key_key;
CREATE UNIQUE INDEX research_request_user_idempotency
  ON public.research_request(user_id, idempotency_key) WHERE idempotency_key IS NOT NULL;

ALTER TABLE public.filing_batch
  ADD COLUMN user_id uuid REFERENCES public.app_user(id);
UPDATE public.filing_batch
   SET user_id = '00000000-0000-0000-0000-000000000001'
 WHERE user_id IS NULL;
ALTER TABLE public.filing_batch ALTER COLUMN user_id SET NOT NULL;

CREATE TABLE public.cost_action (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES public.app_user(id),
  kind public.cost_action_kind NOT NULL,
  status public.cost_action_status NOT NULL DEFAULT 'reserved',
  reserved_usd numeric(18,8) NOT NULL CHECK (reserved_usd >= 0),
  charged_usd numeric(18,8) CHECK (charged_usd IS NULL OR charged_usd >= 0),
  pricing_snapshot jsonb,
  research_id uuid UNIQUE REFERENCES public.research_request(id),
  filing_batch_id uuid UNIQUE REFERENCES public.filing_batch(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  reconciled_at timestamptz,
  CHECK (
    (kind = 'research' AND research_id IS NOT NULL AND filing_batch_id IS NULL)
    OR
    (kind = 'corpus_preparation' AND research_id IS NULL AND filing_batch_id IS NOT NULL)
  )
);
CREATE INDEX cost_action_user_created ON public.cost_action(user_id, created_at DESC);

CREATE TABLE public.audit_event (
  id bigserial PRIMARY KEY,
  actor_user_id uuid REFERENCES public.app_user(id),
  event_type text NOT NULL,
  outcome text NOT NULL,
  target_type text,
  target_id text,
  request_id text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_event_actor_created ON public.audit_event(actor_user_id, created_at DESC);
CREATE INDEX audit_event_created ON public.audit_event(created_at DESC);

COMMIT;
