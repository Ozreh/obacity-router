import { readFile } from "node:fs/promises";

const API = process.env.ADDRESS_API ?? "http://localhost:3001";
const CITY = "Obama";
const CONCURRENCY = 4;

const file = new URL("../data/obama-addresses.json", import.meta.url);
const items = JSON.parse(await readFile(file, "utf8"));

let created = 0;
let skipped = 0;
let failed = 0;
let next = 0;

const worker = async () => {
  while (next < items.length) {
    const item = items[next++];
    try {
      const res = await fetch(`${API}/addresses`, {
        method: "POST",
        headers: { "content-type": "application/json; charset=utf-8" },
        body: JSON.stringify({
          city: CITY,
          streetName: item.street,
          houseNumber: item.house,
          lat: item.lat,
          lon: item.lon,
        }),
      });
      if (res.status === 201) created++;
      else if (res.status === 409) skipped++;
      else {
        failed++;
        console.error(res.status, item.street, await res.text());
      }
    } catch (error) {
      failed++;
      console.error("request failed", item.street, String(error));
    }
    if ((created + skipped + failed) % 100 === 0) {
      console.log(`${created + skipped + failed}/${items.length}`);
    }
  }
};

await Promise.all(Array.from({ length: CONCURRENCY }, worker));
console.log(`done: created ${created}, skipped ${skipped}, failed ${failed}`);
