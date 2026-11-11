import type { Address, AddressInput, AddressReader, UnitOfWork } from "../domain/ports.js";

export class AddressService {
  constructor(
    private readonly uow: UnitOfWork,
    private readonly reader: AddressReader,
  ) {}

  create(input: AddressInput): Promise<Address> {
    return this.uow.run(async ({ addresses, events }) => {
      const address = await addresses.insert(input);
      await events.record({ type: "address.changed", aggregateId: address.id });
      return address;
    });
  }

  update(id: string, input: AddressInput): Promise<Address | null> {
    return this.uow.run(async ({ addresses, events }) => {
      const address = await addresses.update(id, input);
      if (address) await events.record({ type: "address.changed", aggregateId: id });
      return address;
    });
  }

  remove(id: string): Promise<boolean> {
    return this.uow.run(async ({ addresses, events }) => {
      const address = await addresses.softDelete(id);
      if (!address) return false;
      await events.record({ type: "address.changed", aggregateId: id });
      return true;
    });
  }

  renameStreet(streetId: string, name: string): Promise<number> {
    return this.uow.run(async ({ addresses, events }) => {
      const ids = await addresses.renameStreet(streetId, name);
      for (const id of ids) await events.record({ type: "address.changed", aggregateId: id });
      return ids.length;
    });
  }

  get(id: string): Promise<Address | null> {
    return this.reader.findById(id);
  }

  list(limit: number, offset: number): Promise<Address[]> {
    return this.reader.list(limit, offset);
  }
}
