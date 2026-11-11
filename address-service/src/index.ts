import { serve } from "@hono/node-server";
import { Hono } from "hono";
import { AddressService } from "./application/address-service.js";
import { HttpSearchPublisher } from "./infrastructure/http-search-publisher.js";
import { OutboxRelay } from "./infrastructure/outbox-relay.js";
import { PgOutboxQueue, PgUnitOfWork } from "./infrastructure/pg-outbox.js";
import { PgAddressRepository } from "./infrastructure/pg-repository.js";
import { pool } from "./infrastructure/pg.js";
import { addressRoutes } from "./http/routes.js";

const reader = new PgAddressRepository(pool);
const service = new AddressService(new PgUnitOfWork(pool), reader);

const relay = new OutboxRelay(
  new PgOutboxQueue(pool),
  reader,
  new HttpSearchPublisher(process.env.SEARCH_SERVICE_URL!, process.env.INTERNAL_TOKEN!),
);
relay.start();

const app = new Hono();
app.get("/health", (c) => c.json({ ok: true }));
app.route("/", addressRoutes(service));

serve({ fetch: app.fetch, port: Number(process.env.PORT ?? 3001) });

process.on("SIGTERM", () => {
  relay.stop();
  void pool.end();
});
