import { serve } from "@hono/node-server";
import { Hono } from "hono";
import { Client } from "@elastic/elasticsearch";
import { ElasticSearchIndex } from "./infrastructure/es-search-index.js";
import { searchRoutes } from "./http/routes.js";

const client = new Client({
  node: process.env.ELASTICSEARCH_URL!,
  auth: process.env.ELASTICSEARCH_API_KEY ? { apiKey: process.env.ELASTICSEARCH_API_KEY } : undefined,
});

const index = new ElasticSearchIndex(client);

for (let attempt = 1; ; attempt++) {
  try {
    await index.ensure();
    break;
  } catch (error) {
    if (attempt >= 30) throw error;
    await new Promise((r) => setTimeout(r, 2000));
  }
}

const app = new Hono();
app.get("/health", (c) => c.json({ ok: true }));
app.route("/", searchRoutes(index, process.env.INTERNAL_TOKEN!, process.env.ALLOWED_ORIGIN ?? "*"));

serve({ fetch: app.fetch, port: Number(process.env.PORT ?? 3002) });
