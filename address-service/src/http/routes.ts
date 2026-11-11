import { Hono } from "hono";
import { zValidator } from "@hono/zod-validator";
import { z } from "zod";
import type { AddressService } from "../application/address-service.js";

const addressSchema = z.object({
  city: z.string().min(1),
  streetName: z.string().min(1),
  houseNumber: z.string(),
  building: z.string().nullish(),
  postalCode: z.string().nullish(),
  lat: z.number().min(-90).max(90),
  lon: z.number().min(-180).max(180),
});

const pageSchema = z.object({
  limit: z.coerce.number().int().min(1).max(200).default(50),
  offset: z.coerce.number().int().min(0).default(0),
});

const isUniqueViolation = (e: unknown) => (e as { code?: string })?.code === "23505";

export const addressRoutes = (service: AddressService) => {
  const app = new Hono();

  app.get("/addresses", zValidator("query", pageSchema), async (c) => {
    const { limit, offset } = c.req.valid("query");
    return c.json(await service.list(limit, offset));
  });

  app.get("/addresses/:id", async (c) => {
    const address = await service.get(c.req.param("id"));
    return address ? c.json(address) : c.json({ error: "not_found" }, 404);
  });

  app.post("/addresses", zValidator("json", addressSchema), async (c) => {
    try {
      return c.json(await service.create(c.req.valid("json")), 201);
    } catch (e) {
      if (isUniqueViolation(e)) return c.json({ error: "duplicate" }, 409);
      throw e;
    }
  });

  app.put("/addresses/:id", zValidator("json", addressSchema), async (c) => {
    try {
      const address = await service.update(c.req.param("id"), c.req.valid("json"));
      return address ? c.json(address) : c.json({ error: "not_found" }, 404);
    } catch (e) {
      if (isUniqueViolation(e)) return c.json({ error: "duplicate" }, 409);
      throw e;
    }
  });

  app.delete("/addresses/:id", async (c) => {
    const ok = await service.remove(c.req.param("id"));
    return ok ? c.body(null, 204) : c.json({ error: "not_found" }, 404);
  });

  app.patch("/streets/:id", zValidator("json", z.object({ name: z.string().min(1) })), async (c) => {
    const updated = await service.renameStreet(c.req.param("id"), c.req.valid("json").name);
    return c.json({ updated });
  });

  return app;
};
