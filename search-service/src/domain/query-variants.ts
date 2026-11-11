const EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,.";
const RU = "йцукенгшщзхъфывапролджэячсмитьбю";

const toRu = new Map([...EN].map((c, i) => [c, RU[i]] as const));
const toEn = new Map([...RU].map((c, i) => [c, EN[i]] as const));

const LAT_TO_CYR: Record<string, string> = {
  shch: "щ", sch: "щ", sh: "ш", ch: "ч", zh: "ж", ts: "ц", kh: "х",
  yu: "ю", ya: "я", yo: "е", ye: "е",
  a: "а", b: "б", c: "к", d: "д", e: "е", f: "ф", g: "г", h: "х", i: "и",
  j: "дж", k: "к", l: "л", m: "м", n: "н", o: "о", p: "п", q: "к", r: "р",
  s: "с", t: "т", u: "у", v: "в", w: "в", x: "кс", y: "и", z: "з",
};

const CYR_TO_LAT: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z",
  и: "i", й: "y", к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r",
  с: "s", т: "t", у: "u", ф: "f", х: "kh", ц: "ts", ч: "ch", ш: "sh",
  щ: "shch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya",
};

const latRe = new RegExp(
  Object.keys(LAT_TO_CYR).sort((a, b) => b.length - a.length).join("|"),
  "g",
);

const swapLayout = (s: string, map: Map<string, string>) =>
  [...s].map((c) => map.get(c) ?? c).join("");

const latinToCyrillic = (s: string) =>
  s.replace(/c(?=[eiy])/g, "ts").replace(latRe, (m) => LAT_TO_CYR[m]);

const cyrillicToLatin = (s: string) =>
  [...s].map((c) => CYR_TO_LAT[c] ?? c).join("");

const splitLettersAndDigits = (s: string) =>
  s.replace(/(\p{L})(\d)/gu, "$1 $2").replace(/(\d)(\p{L})/gu, "$1 $2");

export const queryVariants = (raw: string): string[] => {
  const q = raw.toLowerCase().replace(/\s+/g, " ").trim();
  const variants = [q];
  if (/[a-z]/.test(q)) variants.push(swapLayout(q, toRu), latinToCyrillic(q));
  if (/[а-яё]/.test(q)) variants.push(swapLayout(q, toEn), cyrillicToLatin(q));
  return [...new Set(variants.map(splitLettersAndDigits).map((v) => v.trim()).filter(Boolean))];
};
