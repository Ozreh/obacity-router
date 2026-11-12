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

export interface SuggestQuery {
  q: string;
  limit: number;
  near?: { lat: number; lon: number };
}

export interface Suggestion {
  id: string;
  label: string;
  city: string;
  lat: number;
  lon: number;
}

export interface SearchIndex {
  ensure(): Promise<void>;
  upsert(doc: AddressDocument): Promise<void>;
  remove(id: string, version: number): Promise<void>;
  suggest(query: SuggestQuery): Promise<Suggestion[]>;
}
