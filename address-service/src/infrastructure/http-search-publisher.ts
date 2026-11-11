import type { AddressDocument, IndexPublisher } from "../domain/ports.js";

export class HttpSearchPublisher implements IndexPublisher {
  constructor(
    private readonly baseUrl: string,
    private readonly token: string,
  ) {}

  private headers() {
    return { "content-type": "application/json", "x-internal-token": this.token };
  }

  async upsert(doc: AddressDocument) {
    const res = await fetch(`${this.baseUrl}/internal/addresses/${doc.id}`, {
      method: "PUT",
      headers: this.headers(),
      body: JSON.stringify(doc),
    });
    if (!res.ok) throw new Error(`search upsert ${res.status}`);
  }

  async remove(id: string, version: number) {
    const res = await fetch(`${this.baseUrl}/internal/addresses/${id}?version=${version}`, {
      method: "DELETE",
      headers: this.headers(),
    });
    if (!res.ok) throw new Error(`search remove ${res.status}`);
  }
}
