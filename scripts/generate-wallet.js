import { ethers } from "ethers";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Generate new wallet for Monad testnet
 * 
 * WARNING: This is for testnet only - no real funds
 */
async function main() {
  console.log("=".repeat(70));
  console.log("GENERATING NEW WALLET FOR MONAD TESTNET");
  console.log("=".repeat(70));
  console.log();

  // Generate random wallet
  const wallet = ethers.Wallet.createRandom();
  
  console.log("Wallet Generated!");
  console.log();
  console.log("Address:", wallet.address);
  console.log();
  console.log("=".repeat(70));
  console.log("PRIVATE KEY (TESTNET ONLY - KEEP SECURE)");
  console.log("=".repeat(70));
  console.log();
  console.log(wallet.privateKey);
  console.log();
  console.log("=".repeat(70));
  console.log("IMPORTANT INSTRUCTIONS");
  console.log("=".repeat(70));
  console.log();
  console.log("1. Copy the private key above");
  console.log("2. Add to .env file: EXECUTOR_PRIVATE_KEY=<key>");
  console.log("3. Get testnet MONAD tokens from: https://testnet.monad.xyz/faucet");
  console.log("4. Never use this address for mainnet or real funds");
  console.log();
  console.log("=".repeat(70));
  
  // Save to file (with warning)
  const walletData = {
    address: wallet.address,
    privateKey: wallet.privateKey,
    network: "monad-testnet",
    created: new Date().toISOString(),
    warning: "TESTNET ONLY - DO NOT USE FOR REAL FUNDS"
  };
  
  const outputPath = path.join(__dirname, "..", "testnet-wallet.json");
  fs.writeFileSync(outputPath, JSON.stringify(walletData, null, 2));
  
  console.log();
  console.log(`✅ Wallet info saved to: ${outputPath}`);
  console.log();
  console.log("Next steps:");
  console.log("  1. Add private key to .env: EXECUTOR_PRIVATE_KEY=" + wallet.privateKey);
  console.log("  2. Visit https://testnet.monad.xyz/faucet");
  console.log("  3. Request tokens for address: " + wallet.address);
  console.log("  4. Run: npx hardhat run scripts/deploy.js --network monadTestnet");
  console.log();
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
