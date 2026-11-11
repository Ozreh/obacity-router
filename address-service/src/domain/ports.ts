export interface Address {
  id: string;
  streetId: string;
  streetName: string;
  city: string;
  houseNumber: string;
  building: string | null;
  postalCode: string | null;
  lat: number;
  lon: number;
  version: number;
  deletedAt: Date | null;
}

export interface AddressInput {
  city: string;
  streetName: string;
  houseNumber: string;
  building?: string | null;
  postalCode?: string | null;
  lat: number;
  lon: number;
}

export interface AddressWriter {
  insert(input: AddressInput): Promise<Address>;
  update(id: string, input: AddressInput): Promise<Address | null>;
  softDelete(id: string): Promise<Address | null>;
  renameStreet(streetId: string, name: string): Promise<string[]>;
}

export interface AddressReader {
  findById(id: string): Promise<Address | null>;
  findByIdAny(id: string): Promise<Address | null>;
  list(limit: number, offset: number): Promise<Address[]>;
}

export interface DomainEvent {
  type: "address.changed";
  aggregateId: string;
}

export interface EventRecorder {
  record(event: DomainEvent): Promise<void>;
}

export interface TxContext {
  addresses: AddressWriter;
  events: EventRecorder;
}

export interface UnitOfWork {
  run<T>(work: (tx: TxContext) => Promise<T>): Promise<T>;
}

export interface AddressDocument {
  id: string;
  version: number;
  city: string;
  street: string;
  house_number: string;
  building: string | null;
  postal_code: string | null;
  label: string;
  location: { lat: number; lon: number };
}

export interface IndexPublisher {
  upsert(doc: AddressDocument): Promise<void>;
  remove(id: string, version: number): Promise<void>;
}

export interface OutboxEvent {
  id: number;
  aggregateId: string;
  type: string;
}

export interface OutboxQueue {
  drain(limit: number, handle: (event: OutboxEvent) => Promise<void>): Promise<number>;
}
