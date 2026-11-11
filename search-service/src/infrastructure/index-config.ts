import type { estypes } from "@elastic/elasticsearch";

export const ADDRESS_INDEX = "addresses_v2";

const foldingFilters = ["lowercase", "fold_i", "fold_o", "drop_signs", "collapse_double", "non_empty"];

export const addressIndexBody: Omit<estypes.IndicesCreateRequest, "index"> = {
  settings: {
    number_of_shards: 1,
    number_of_replicas: 0,
    analysis: {
      filter: {
        autocomplete_edge: { type: "edge_ngram", min_gram: 1, max_gram: 20 },
        fold_i: { type: "pattern_replace", pattern: "[еёэыйи]", replacement: "и" },
        fold_o: { type: "pattern_replace", pattern: "о", replacement: "а" },
        drop_signs: { type: "pattern_replace", pattern: "[ъь]", replacement: "" },
        collapse_double: { type: "pattern_replace", pattern: "(\\p{L})\\1+", replacement: "$1" },
        non_empty: { type: "length", min: 1 },
      },
      analyzer: {
        autocomplete_index: {
          type: "custom",
          tokenizer: "standard",
          filter: [...foldingFilters, "autocomplete_edge"],
        },
        autocomplete_search: {
          type: "custom",
          tokenizer: "standard",
          filter: foldingFilters,
        },
      },
    },
  },
  mappings: {
    dynamic: "strict",
    properties: {
      city: { type: "keyword" },
      street: { type: "text", analyzer: "autocomplete_index", search_analyzer: "autocomplete_search" },
      house_number: { type: "keyword" },
      building: { type: "keyword" },
      postal_code: { type: "keyword" },
      label: {
        type: "text",
        analyzer: "autocomplete_index",
        search_analyzer: "autocomplete_search",
        fields: { exact: { type: "text", analyzer: "standard" } },
      },
      location: { type: "geo_point" },
    },
  },
};
