CREATE TABLE streets (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  city       text NOT NULL,
  name       text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (city, name)
);

CREATE TABLE addresses (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  street_id    uuid NOT NULL REFERENCES streets(id) ON DELETE RESTRICT,
  house_number text NOT NULL,
  building     text,
  postal_code  text,
  lat          double precision NOT NULL CHECK (lat BETWEEN -90 AND 90),
  lon          double precision NOT NULL CHECK (lon BETWEEN -180 AND 180),
  version      bigint NOT NULL DEFAULT 1,
  deleted_at   timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX addresses_unique_idx
  ON addresses (street_id, lower(house_number), coalesce(building, ''))
  WHERE deleted_at IS NULL;

CREATE INDEX addresses_street_idx ON addresses (street_id);
CREATE INDEX addresses_geo_idx ON addresses (lat, lon);

CREATE TABLE outbox (
  id           bigserial PRIMARY KEY,
  aggregate_id uuid NOT NULL,
  event_type   text NOT NULL,
  attempts     int NOT NULL DEFAULT 0,
  last_error   text,
  available_at timestamptz NOT NULL DEFAULT now(),
  created_at   timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz
);

CREATE INDEX outbox_pending_idx ON outbox (id) WHERE processed_at IS NULL;
