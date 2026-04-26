import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const RPC_URL = 'https://testnet-rpc.monad.xyz';
const DEPLOYMENT_FILE = path.join(process.cwd(), '..', 'deployments', 'monadTestnet.json');
const METRICS_FILE = path.join(process.cwd(), '..', 'monitor', 'metrics.json');
const EVENTS_FILE = path.join(process.cwd(), '..', 'monitor', 'events.jsonl');

async function rpcCall(method: string, params: any[] = []) {
  const response = await fetch(RPC_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
  });
  const data = await response.json();
  return data.result;
}

export async function GET() {
  try {
    // Get blockchain status
    const blockHex = await rpcCall('eth_blockNumber');
    const block = parseInt(blockHex, 16);
    const gasPriceHex = await rpcCall('eth_gasPrice');
    const gasPrice = parseInt(gasPriceHex, 16) / 1e9; // gwei

    // Load deployment
    let deployment: any = null;
    try {
      deployment = JSON.parse(fs.readFileSync(DEPLOYMENT_FILE, 'utf8'));
    } catch (e) {}

    // Get wallet balance (from env)
    const wallet = process.env.EXECUTOR_ADDRESS || '0x8Bc0a39981A5B259696a0854EA6984FDE81A3232';
    const balanceHex = await rpcCall('eth_getBalance', [wallet, 'latest']);
    const balance = parseInt(balanceHex, 16) / 1e18;

    // Load metrics
    let metrics: any = null;
    try {
      metrics = JSON.parse(fs.readFileSync(METRICS_FILE, 'utf8'));
    } catch (e) {}

    // Load recent events
    let events: any[] = [];
    try {
      const lines = fs.readFileSync(EVENTS_FILE, 'utf8').trim().split('\n');
      events = lines.slice(-20).reverse().map((line) => JSON.parse(line));
    } catch (e) {}

    // Check monitor status
    let monitorActive = false;
    let monitorLastUpdate = 0;
    if (metrics?.last_update) {
      const lastUpdate = new Date(metrics.last_update).getTime();
      monitorLastUpdate = (Date.now() - lastUpdate) / 1000;
      monitorActive = monitorLastUpdate < 30;
    }

    return NextResponse.json({
      timestamp: new Date().toISOString(),
      blockchain: {
        connected: true,
        block,
        chainId: 10143,
        gasPrice: gasPrice.toFixed(2),
        explorer: 'https://testnet.monadexplorer.com',
      },
      wallet: {
        address: wallet,
        balance: balance.toFixed(4),
      },
      contracts: deployment?.contracts || {},
      monitor: {
        active: monitorActive,
        lastUpdateSeconds: monitorLastUpdate,
        metrics,
      },
      events,
    });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message },
      { status: 500 }
    );
  }
}
