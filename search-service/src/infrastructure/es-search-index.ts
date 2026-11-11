import { Client, errors, type estypes } from "@elastic/elasticsearch";
import type { AddressDocument, SearchIndex, SuggestQuery, Suggestion } from "../domain/ports.js";
import { queryVariants } from "../domain/query-variants.js";
import { ADDRESS_INDEX, addressIndexBody } from "./index-config.js";

const isConflictOrMissing = (e: unknown) =>
  e instanceof errors.ResponseError && (e.statusCode === 409 || e.statusCode === 404);

export class ElasticSearchIndex implements SearchIndex {
  constructor(private readonly client: Client) {}

  async ensure() {
    const exists = await this.client.indices.exists({ index: ADDRESS_INDEX });
    if (!exists) await this.client.indices.create({ index: ADDRESS_INDEX, ...addressIndexBody });
  }

  async upsert(doc: AddressDocument) {
    const { id, version, ...document } = doc;
    try {
      await this.client.index({
        index: ADDRESS_INDEX,
        id,
        document,
        version,
        version_type: "external",
      });
    } catch (e) {
      if (!isConflictOrMissing(e)) throw e;
    }
  }

  async remove(id: string, version: number) {
    try {
      await this.client.delete({ index: ADDRESS_INDEX, id, version, version_type: "external" });
    } catch (e) {
      if (!isConflictOrMissing(e)) throw e;
    }
  }

  async suggest({ q, limit, near }: SuggestQuery): Promise<Suggestion[]> {
    const sort: estypes.Sort = near
      ? [{ _score: { order: "desc" } }, { _geo_distance: { location: near, order: "asc", unit: "m" } }]
      : [{ _score: { order: "desc" } }];

    const variants = queryVariants(q).map((variant, i) => ({
      bool: {
        must: [
          { match: { label: { query: variant, operator: "and" as const, fuzziness: "AUTO", prefix_length: 0, max_expansions: 50 } } },
        ],
        should: [
          { match_phrase_prefix: { "label.exact": { query: variant, boost: 6 } } },
          { match_phrase: { label: { query: variant, boost: 3 } } },
        ],
        boost: i === 0 ? 2 : 1,
      },
    }));

    const res = await this.client.search<any>({
      index: ADDRESS_INDEX,
      size: limit,
      _source: ["label", "city", "location"],
      query: { bool: { should: variants, minimum_should_match: 1 } },
      sort,
    });
    return res.hits.hits.map((h) => ({
      id: h._id!,
      label: h._source.label,
      city: h._source.city,
      lat: h._source.location.lat,
      lon: h._source.location.lon,
    }));
  }
}
