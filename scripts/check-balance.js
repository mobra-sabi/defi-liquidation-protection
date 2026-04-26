import { ethers } from "ethers";
import dotenv from "dotenv";

dotenv.config();

async function main() {
  const rpcUrl = process.env.MONAD_RPC_URL || "https://testnet-rpc.monad.xyz";
  const address = process.env.EXECUTOR_ADDRESS;
  
  if (!address) {
    console.log("❌ No wallet address found. Run: npx hardhat run scripts/generate-wallet.js");
    process.exit(1);
  }
  
  console.log("============================================");
  console.log("CHECKING WALLET BALANCE");
  console.log("============================================");
  console.log();
  console.log("Address:", address);
  console.log("RPC:", rpcUrl);
  console.log();
  
  try {
    const provider = new ethers.JsonRpcProvider(rpcUrl);
    const balance = await provider.getBalance(address);
    const balanceEth = ethers.formatEther(balance);
    
    console.log("Balance:", balanceEth, "MON");
    console.log();
    
    if (parseFloat(balanceEth) > 0) {
      console.log("✅ Sufficient balance for deploy!");
      console.log();
      console.log("Next step: npx hardhat run scripts/deploy.js --network monadTestnet");
    } else {
      console.log("❌ No balance. Get tokens from:");
      console.log("   https://testnet.monad.xyz/faucet");
      console.log();
      console.log("Enter this address:", address);
    }
  } catch (error) {
    console.log("❌ Error checking balance:", error.message);
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
