import type { Address, AddressDocument, AddressReader, IndexPublisher, OutboxEvent, OutboxQueue } from "../domain/ports.js";

export const toDocument = (a: Address): AddressDocument => ({
  id: a.id,
  version: a.version,
  city: a.city,
  street: a.streetName,
  house_number: a.houseNumber,
  building: a.building,
  postal_code: a.postalCode,
  label: [a.streetName, a.houseNumber, a.building ? `к${a.building}` : ""].filter(Boolean).join(" "),
  location: { lat: a.lat, lon: a.lon },
});

export class OutboxRelay {
  private timer: NodeJS.Timeout | null = null;
  private running = false;

  constructor(
    private readonly queue: OutboxQueue,
    private readonly reader: AddressReader,
    private readonly publisher: IndexPublisher,
    private readonly intervalMs = 1000,
    private readonly batchSize = 50,
  ) {}

  start() {
    this.timer = setInterval(() => void this.tick(), this.intervalMs);
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
  }

  private async tick() {
    if (this.running) return;
    this.running = true;
    try {
      while ((await this.queue.drain(this.batchSize, (e) => this.handle(e))) === this.batchSize);
    } catch (error) {
      console.error("relay error", error);
    } finally {
      this.running = false;
    }
  }

  private async handle(event: OutboxEvent) {
    const address = await this.reader.findByIdAny(event.aggregateId);
    if (!address) return;
    if (address.deletedAt) await this.publisher.remove(address.id, address.version);
    else await this.publisher.upsert(toDocument(address));
  }
}
