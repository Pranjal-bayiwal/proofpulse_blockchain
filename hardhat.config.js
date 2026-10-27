// Hardhat is used ONLY to provide a local Ethereum-compatible JSON-RPC node (`npm run node`).
// Contracts are compiled by scripts/compile.js (solc-js) so no compiler download is needed.
module.exports = {
  solidity: "0.8.26",
  networks: {
    hardhat: { chainId: 31337, mining: { auto: true, interval: 0 } },
  },
};
