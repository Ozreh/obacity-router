import type { Pool, PoolClient } from "pg";
import type { DomainEvent, EventRecorder, OutboxEvent, OutboxQueue, TxContext, UnitOfWork } from "../domain/ports.js";
import { PgAddressRepository } from "./pg-repository.js";

export class PgEventRecorder implements EventRecorder {
  constructor(private readonly db: PoolClient) {}

  async record(event: DomainEvent) {
    await this.db.query(`INSERT INTO outbox (aggregate_id, event_type) VALUES ($1, $2)`, [
      event.aggregateId,
      event.type,
    ]);
  }
}

export class PgUnitOfWork implements UnitOfWork {
  constructor(private readonly pool: Pool) {}

  async run<T>(work: (tx: TxContext) => Promise<T>): Promise<T> {
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      const result = await work({
        addresses: new PgAddressRepository(client),
        events: new PgEventRecorder(client),
      });
      await client.query("COMMIT");
      return result;
    } catch (error) {
      await client.query("ROLLBACK");
      throw error;
    } finally {
      client.release();
    }
  }
}

export class PgOutboxQueue implements OutboxQueue {
  constructor(private readonly pool: Pool) {}

  async drain(limit: number, handle: (event: OutboxEvent) => Promise<void>) {
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      const { rows } = await client.query(
        `SELECT id, aggregate_id, event_type FROM outbox
         WHERE processed_at IS NULL AND available_at <= now()
         ORDER BY id LIMIT $1 FOR UPDATE SKIP LOCKED`,
        [limit],
      );
      for (const row of rows) {
        try {
          await handle({ id: row.id, aggregateId: row.aggregate_id, type: row.event_type });
          await client.query(`UPDATE outbox SET processed_at = now() WHERE id = $1`, [row.id]);
        } catch (error) {
          await client.query(
            `UPDATE outbox
             SET attempts = attempts + 1, last_error = $2,
                 available_at = now() + (least(power(2, attempts), 300) || ' seconds')::interval
             WHERE id = $1`,
            [row.id, String(error).slice(0, 500)],
          );
        }
      }
      await client.query("COMMIT");
      return rows.length;
    } catch (error) {
      await client.query("ROLLBACK");
      throw error;
    } finally {
      client.release();
    }
  }
}
