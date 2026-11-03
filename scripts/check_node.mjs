import { readFileSync } from "node:fs";
const expected = readFileSync(new URL("../.node-version", import.meta.url), "utf8").trim();
if (process.versions.node !== expected) {
  process.stderr.write(`Latch requires Node ${expected}; found ${process.versions.node}. Run scripts/bootstrap.sh.\n`);
  process.exit(1);
}
process.stdout.write(JSON.stringify({ status: "passed", node: process.versions.node }) + "\n");
