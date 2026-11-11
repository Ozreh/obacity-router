import { Hono } from "hono";
import { cors } from "hono/cors";
import { zValidator } from "@hono/zod-validator";
import { z } from "zod";
import type { SearchIndex } from "../domain/ports.js";

const documentSchema = z.object({
  id: z.string().uuid(),
  version: z.number().int().positive(),
  city: z.string(),
  street: z.string(),
  house_number: z.string(),
  building: z.string().nullable(),
  postal_code: z.string().nullable(),
  label: z.string(),
  location: z.object({ lat: z.number(), lon: z.number() }),
});

const searchSchema = z.object({
  q: z.string().trim().min(1).max(100),
  limit: z.coerce.number().int().min(1).max(20).default(8),
  lat: z.coerce.number().optional(),
  lon: z.coerce.number().optional(),
});

export const searchRoutes = (index: SearchIndex, internalToken: string, allowedOrigin: string) => {
  const app = new Hono();

  app.use("/search", cors({ origin: allowedOrigin }));

  app.get("/search", zValidator("query", searchSchema), async (c) => {
    const { q, limit, lat, lon } = c.req.valid("query");
    const near = lat !== undefined && lon !== undefined ? { lat, lon } : undefined;
    return c.json(await index.suggest({ q, limit, near }));
  });

  app.use("/internal/*", async (c, next) => {
    if (c.req.header("x-internal-token") !== internalToken) return c.json({ error: "forbidden" }, 403);
    await next();
  });

  app.put("/internal/addresses/:id", zValidator("json", documentSchema), async (c) => {
    const doc = c.req.valid("json");
    if (doc.id !== c.req.param("id")) return c.json({ error: "id_mismatch" }, 400);
    await index.upsert(doc);
    return c.body(null, 204);
  });

  app.delete(
    "/internal/addresses/:id",
    zValidator("query", z.object({ version: z.coerce.number().int().positive() })),
    async (c) => {
      await index.remove(c.req.param("id"), c.req.valid("query").version);
      return c.body(null, 204);
    },
  );

  return app;
};
