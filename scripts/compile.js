// Compiles contracts/ProofPulse.sol with solc-js and writes backend/app/contract/ProofPulse.json
const fs = require("fs");
const path = require("path");
const solc = require("solc");

const root = path.join(__dirname, "..");
const src = fs.readFileSync(path.join(root, "contracts", "ProofPulse.sol"), "utf8");

const input = {
  language: "Solidity",
  sources: { "ProofPulse.sol": { content: src } },
  settings: {
    optimizer: { enabled: true, runs: 200 },
    evmVersion: "paris",
    outputSelection: { "*": { "*": ["abi", "evm.bytecode.object"] } },
  },
};

const out = JSON.parse(solc.compile(JSON.stringify(input)));
let failed = false;
for (const e of out.errors || []) {
  console.log(`${e.severity.toUpperCase()}: ${e.formattedMessage}`);
  if (e.severity === "error") failed = true;
}
if (failed) process.exit(1);

const c = out.contracts["ProofPulse.sol"]["ProofPulse"];
const dir = path.join(root, "backend", "app", "contract");
fs.mkdirSync(dir, { recursive: true });
fs.writeFileSync(
  path.join(dir, "ProofPulse.json"),
  JSON.stringify({ contractName: "ProofPulse", abi: c.abi, bytecode: "0x" + c.evm.bytecode.object }, null, 2)
);
console.log("Compiled OK ->", path.join("backend", "app", "contract", "ProofPulse.json"));
