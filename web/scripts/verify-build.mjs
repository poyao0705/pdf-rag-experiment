import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";

let spec;
try {
  spec = JSON.parse(await readFile(new URL("../src/generated/spec.json", import.meta.url), "utf8"));
} catch (cause) {
  throw new Error("Cannot verify OpenUI spec; run vp run generate first.", { cause });
}
assert.ok(spec.schema && typeof spec.root === "string", "Generated library spec is missing");
const directory = new URL("../dist/assets/", import.meta.url);
const files = (await readdir(directory)).filter((file) => file.endsWith(".css"));
const css = (
  await Promise.all(files.map((file) => readFile(new URL(file, directory), "utf8")))
).join("\n");
for (const name of ["h-screen", "w-screen", "overflow-hidden"]) {
  assert.ok(
    css.includes("." + name + "{") || css.includes("." + name + " {"),
    "Missing Tailwind utility: " + name,
  );
}
console.log("Verified generated OpenUI spec and production Tailwind utilities.");
