import type { Pool, PoolClient } from "pg";
import type { Address, AddressInput, AddressReader, AddressWriter } from "../domain/ports.js";

type Queryable = Pool | PoolClient;

const SELECT = `
  SELECT a.id, a.street_id, s.name AS street_name, s.city, a.house_number,
         a.building, a.postal_code, a.lat, a.lon, a.version, a.deleted_at
  FROM addresses a JOIN streets s ON s.id = a.street_id`;

const toAddress = (r: any): Address => ({
  id: r.id,
  streetId: r.street_id,
  streetName: r.street_name,
  city: r.city,
  houseNumber: r.house_number,
  building: r.building,
  postalCode: r.postal_code,
  lat: r.lat,
  lon: r.lon,
  version: Number(r.version),
  deletedAt: r.deleted_at,
});

export class PgAddressRepository implements AddressReader, AddressWriter {
  constructor(private readonly db: Queryable) {}

  async findById(id: string) {
    const { rows } = await this.db.query(`${SELECT} WHERE a.id = $1 AND a.deleted_at IS NULL`, [id]);
    return rows[0] ? toAddress(rows[0]) : null;
  }

  async findByIdAny(id: string) {
    const { rows } = await this.db.query(`${SELECT} WHERE a.id = $1`, [id]);
    return rows[0] ? toAddress(rows[0]) : null;
  }

  async list(limit: number, offset: number) {
    const { rows } = await this.db.query(
      `${SELECT} WHERE a.deleted_at IS NULL ORDER BY s.name, a.house_number LIMIT $1 OFFSET $2`,
      [limit, offset],
    );
    return rows.map(toAddress);
  }

  private async ensureStreet(city: string, name: string): Promise<string> {
    const { rows } = await this.db.query(
      `INSERT INTO streets (city, name) VALUES ($1, $2)
       ON CONFLICT (city, name) DO UPDATE SET name = EXCLUDED.name
       RETURNING id`,
      [city, name],
    );
    return rows[0].id;
  }

  async insert(input: AddressInput) {
    const streetId = await this.ensureStreet(input.city, input.streetName);
    const { rows } = await this.db.query(
      `INSERT INTO addresses (street_id, house_number, building, postal_code, lat, lon)
       VALUES ($1, $2, $3, $4, $5, $6) RETURNING id`,
      [streetId, input.houseNumber, input.building ?? null, input.postalCode ?? null, input.lat, input.lon],
    );
    return (await this.findById(rows[0].id))!;
  }

  async update(id: string, input: AddressInput) {
    const streetId = await this.ensureStreet(input.city, input.streetName);
    const res = await this.db.query(
      `UPDATE addresses
       SET street_id = $2, house_number = $3, building = $4, postal_code = $5,
           lat = $6, lon = $7, version = version + 1, updated_at = now()
       WHERE id = $1 AND deleted_at IS NULL`,
      [id, streetId, input.houseNumber, input.building ?? null, input.postalCode ?? null, input.lat, input.lon],
    );
    return res.rowCount ? this.findById(id) : null;
  }

  async softDelete(id: string) {
    const res = await this.db.query(
      `UPDATE addresses SET deleted_at = now(), version = version + 1, updated_at = now()
       WHERE id = $1 AND deleted_at IS NULL`,
      [id],
    );
    return res.rowCount ? this.findByIdAny(id) : null;
  }

  async renameStreet(streetId: string, name: string) {
    await this.db.query(`UPDATE streets SET name = $2, updated_at = now() WHERE id = $1`, [streetId, name]);
    const { rows } = await this.db.query(
      `UPDATE addresses SET version = version + 1, updated_at = now()
       WHERE street_id = $1 AND deleted_at IS NULL RETURNING id`,
      [streetId],
    );
    return rows.map((r) => r.id as string);
  }
}
