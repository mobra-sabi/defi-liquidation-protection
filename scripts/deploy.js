import hardhat from 'hardhat';
const { ethers } = hardhat;
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function main() {
  const [deployer] = await ethers.getSigners();
  
  console.log("======================================================================");
  console.log("DEPLOYING DEFI PROTECTION PROTOCOL TO MONAD TESTNET");
  console.log("======================================================================");
  console.log("Deployer address:", deployer.address);
  
  const balance = await deployer.provider.getBalance(deployer.address);
  console.log("Deployer balance:", ethers.formatEther(balance), "MON");
  console.log();
  
  // Deploy PositionRegistry
  console.log("1. Deploying PositionRegistry...");
  const PositionRegistry = await ethers.getContractFactory("PositionRegistry");
  const registry = await PositionRegistry.deploy();
  await registry.waitForDeployment();
  const registryAddress = await registry.getAddress();
  console.log("✅ PositionRegistry deployed:", registryAddress);
  
  // Deploy FeeCollector
  console.log("\n2. Deploying FeeCollector...");
  const FeeCollector = await ethers.getContractFactory("FeeCollector");
  // Governance address = deployer for now
  const feeCollector = await FeeCollector.deploy(deployer.address);
  await feeCollector.waitForDeployment();
  const feeCollectorAddress = await feeCollector.getAddress();
  console.log("✅ FeeCollector deployed:", feeCollectorAddress);
  
  // Deploy ProtectionExecutor
  console.log("\n3. Deploying ProtectionExecutor...");
  const ProtectionExecutor = await ethers.getContractFactory("ProtectionExecutor");
  const executor = await ProtectionExecutor.deploy(registryAddress, feeCollectorAddress);
  await executor.waitForDeployment();
  const executorAddress = await executor.getAddress();
  console.log("✅ ProtectionExecutor deployed:", executorAddress);
  
  // Configure contracts
  console.log("\n4. Configuring contracts...");
  
  // Set ProtectionExecutor as AI Executor in PositionRegistry
  const tx1 = await registry.addAIExecutor(executorAddress);
  await tx1.wait();
  console.log("✅ Added ProtectionExecutor as AI Executor");
  
  // Set ProtectionExecutor in FeeCollector
  const tx2 = await feeCollector.setProtectionExecutor(executorAddress);
  await tx2.wait();
  console.log("✅ Set ProtectionExecutor in FeeCollector");
  
  // Save deployment info
  const deploymentInfo = {
    network: "monadTestnet",
    chainId: 10143,
    deployer: deployer.address,
    deploymentTime: new Date().toISOString(),
    contracts: {
      PositionRegistry: {
        address: registryAddress,
        name: "PositionRegistry"
      },
      ProtectionExecutor: {
        address: executorAddress,
        name: "ProtectionExecutor"
      },
      FeeCollector: {
        address: feeCollectorAddress,
        name: "FeeCollector"
      }
    }
  };
  
  const deploymentPath = path.join(__dirname, '..', 'deployments', 'monadTestnet.json');
  fs.mkdirSync(path.dirname(deploymentPath), { recursive: true });
  fs.writeFileSync(deploymentPath, JSON.stringify(deploymentInfo, null, 2));
  
  // Update .env with deployed addresses
  const envPath = path.join(__dirname, '..', '.env');
  let envContent = fs.readFileSync(envPath, 'utf8');
  
  // Append or replace contract addresses
  const addressLines = `
# Deployed Contract Addresses (Monad Testnet)
POSITION_REGISTRY_ADDRESS=${registryAddress}
PROTECTION_EXECUTOR_ADDRESS=${executorAddress}
FEE_COLLECTOR_ADDRESS=${feeCollectorAddress}
`;
  
  if (envContent.includes('POSITION_REGISTRY_ADDRESS=')) {
    // Replace existing
    envContent = envContent.replace(
      /POSITION_REGISTRY_ADDRESS=.*/,
      `POSITION_REGISTRY_ADDRESS=${registryAddress}`
    );
    envContent = envContent.replace(
      /PROTECTION_EXECUTOR_ADDRESS=.*/,
      `PROTECTION_EXECUTOR_ADDRESS=${executorAddress}`
    );
    envContent = envContent.replace(
      /FEE_COLLECTOR_ADDRESS=.*/,
      `FEE_COLLECTOR_ADDRESS=${feeCollectorAddress}`
    );
  } else {
    // Append
    envContent += addressLines;
  }
  
  fs.writeFileSync(envPath, envContent);
  
  console.log("\n" + "======================================================================");
  console.log("DEPLOYMENT COMPLETE!");
  console.log("======================================================================");
  console.log("\nContract Addresses:");
  console.log("  PositionRegistry:   ", registryAddress);
  console.log("  ProtectionExecutor: ", executorAddress);
  console.log("  FeeCollector:       ", feeCollectorAddress);
  console.log("\nDeployment info saved to:", deploymentPath);
  console.log("Environment updated with contract addresses");
  console.log("\nNext steps:");
  console.log("  1. Verify contracts on Monad explorer");
  console.log("  2. Start risk monitor: python monitor/risk_monitor.py");
  console.log("  3. Test protection flow");
  console.log("======================================================================");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
