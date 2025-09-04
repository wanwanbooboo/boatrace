CREATE TABLE IF NOT EXISTS orders (
id BIGSERIAL PRIMARY KEY,
race_id TEXT NOT NULL,
bet_type TEXT NOT NULL,
selection TEXT NOT NULL, -- —á: '1-2-3'
amount INTEGER NOT NULL, -- JPY
requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
status TEXT NOT NULL, -- requested/accepted/rejected/settled
provider_response JSONB,
idempotency_key TEXT NOT NULL,
UNIQUE (idempotency_key)
);