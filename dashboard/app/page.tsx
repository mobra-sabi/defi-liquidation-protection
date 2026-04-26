'use client';

import React, { useState, useEffect } from 'react';
import { Shield, Activity, AlertTriangle, Clock, Box, Zap, ExternalLink, Wifi, WifiOff } from 'lucide-react';

interface StatusData {
  timestamp: string;
  blockchain: {
    connected: boolean;
    block: number;
    chainId: number;
    gasPrice: string;
    explorer: string;
  };
  wallet: {
    address: string;
    balance: string;
  };
  contracts: Record<string, { address: string; name: string }>;
  monitor: {
    active: boolean;
    lastUpdateSeconds: number;
    metrics: {
      blocks_monitored: number;
      events_captured: number;
      uptime_seconds: number;
      started_at: string;
      last_block: number;
    } | null;
  };
  events: Array<{
    type: string;
    timestamp: string;
    block?: number;
    tx_hash?: string;
    contract?: string;
    from?: string;
    to?: string;
    value_mon?: number;
  }>;
}

const StatCard = ({ title, value, subtitle, icon: Icon, color = 'text-blue-400' }: any) => (
  <div className="bg-gray-900 rounded-lg p-6 border border-gray-800 hover:border-gray-700 transition-all">
    <div className="flex items-center justify-between mb-3">
      <h3 className="text-gray-400 text-sm font-medium">{title}</h3>
      <Icon className={`w-5 h-5 ${color}`} />
    </div>
    <div className="text-3xl font-bold text-white mb-1">{value}</div>
    <div className="text-sm text-gray-500">{subtitle}</div>
  </div>
);

const ContractCard = ({ name, address, explorer }: { name: string; address: string; explorer: string }) => (
  <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
    <div className="flex items-center justify-between mb-2">
      <h4 className="font-bold text-white">{name}</h4>
      <span className="px-2 py-0.5 bg-green-500/20 text-green-400 text-xs rounded-full border border-green-500/30">
        DEPLOYED
      </span>
    </div>
    <div className="font-mono text-xs text-gray-400 mb-2 break-all">{address}</div>
    <a
      href={`${explorer}/address/${address}`}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
    >
      View on Explorer <ExternalLink className="w-3 h-3" />
    </a>
  </div>
);

export default function Dashboard() {
  const [data, setData] = useState<StatusData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<Date>(new Date());

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch('/api/status');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        setData(json);
        setError(null);
        setLastFetch(new Date());
      } catch (e: any) {
        setError(e.message);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  if (!data && !error) {
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-4"></div>
          <p>Loading status...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <p className="text-red-400">Error: {error}</p>
        </div>
      </div>
    );
  }

  const uptimeFormat = (seconds: number) => {
    if (seconds < 60) return `${Math.floor(seconds)}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
    return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
  };

  return (
    <div className="min-h-screen bg-black text-white">
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
                <Shield className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                  DeFi Protection
                </h1>
                <p className="text-xs text-gray-500">Live on Monad Testnet</p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {data.blockchain.connected ? (
                <span className="inline-flex items-center gap-2 px-3 py-1 bg-green-500/20 text-green-400 rounded-full border border-green-500/30 text-xs">
                  <Wifi className="w-3 h-3" /> CONNECTED
                </span>
              ) : (
                <span className="inline-flex items-center gap-2 px-3 py-1 bg-red-500/20 text-red-400 rounded-full border border-red-500/30 text-xs">
                  <WifiOff className="w-3 h-3" /> DISCONNECTED
                </span>
              )}
              {data.monitor.active ? (
                <span className="inline-flex items-center gap-2 px-3 py-1 bg-green-500/20 text-green-400 rounded-full border border-green-500/30 text-xs">
                  <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>
                  MONITOR ACTIVE
                </span>
              ) : (
                <span className="inline-flex items-center gap-2 px-3 py-1 bg-yellow-500/20 text-yellow-400 rounded-full border border-yellow-500/30 text-xs">
                  MONITOR IDLE
                </span>
              )}
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="text-xs text-gray-500 mb-6">
          Last update: {lastFetch.toLocaleTimeString()}
        </div>

        {/* Top Stats */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <StatCard
            title="Current Block"
            value={data.blockchain.block.toLocaleString()}
            subtitle={`Chain ID: ${data.blockchain.chainId}`}
            icon={Box}
            color="text-blue-400"
          />
          <StatCard
            title="Wallet Balance"
            value={`${parseFloat(data.wallet.balance).toFixed(4)} MON`}
            subtitle={`${data.wallet.address.slice(0, 8)}...${data.wallet.address.slice(-6)}`}
            icon={Activity}
            color="text-green-400"
          />
          <StatCard
            title="Blocks Monitored"
            value={(data.monitor.metrics?.blocks_monitored || 0).toLocaleString()}
            subtitle={data.monitor.metrics ? `Uptime: ${uptimeFormat(data.monitor.metrics.uptime_seconds)}` : 'Not started'}
            icon={Clock}
            color="text-purple-400"
          />
          <StatCard
            title="Events Captured"
            value={data.monitor.metrics?.events_captured || 0}
            subtitle="On-chain interactions"
            icon={Zap}
            color="text-yellow-400"
          />
        </div>

        {/* Contracts */}
        <div className="mb-8">
          <h2 className="text-2xl font-bold mb-4">Deployed Contracts</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {Object.entries(data.contracts).map(([name, info]) => (
              <ContractCard
                key={name}
                name={name}
                address={info.address}
                explorer={data.blockchain.explorer}
              />
            ))}
          </div>
        </div>

        {/* Network Info */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
            <div className="flex items-center gap-2 mb-3">
              <Wifi className="w-4 h-4 text-blue-400" />
              <h3 className="text-sm font-medium text-gray-400">Network Status</h3>
            </div>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-gray-500 text-sm">Network</span>
                <span className="text-white text-sm">Monad Testnet</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 text-sm">Gas Price</span>
                <span className="text-white text-sm">{data.blockchain.gasPrice} gwei</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 text-sm">Latest Block</span>
                <span className="text-white text-sm font-mono">{data.blockchain.block.toLocaleString()}</span>
              </div>
            </div>
          </div>

          <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
            <div className="flex items-center gap-2 mb-3">
              <Activity className="w-4 h-4 text-green-400" />
              <h3 className="text-sm font-medium text-gray-400">Monitor Status</h3>
            </div>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-gray-500 text-sm">State</span>
                <span className={`text-sm font-medium ${data.monitor.active ? 'text-green-400' : 'text-yellow-400'}`}>
                  {data.monitor.active ? 'Active' : 'Idle'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 text-sm">Last Update</span>
                <span className="text-white text-sm">
                  {data.monitor.lastUpdateSeconds < 60
                    ? `${data.monitor.lastUpdateSeconds.toFixed(0)}s ago`
                    : `${(data.monitor.lastUpdateSeconds / 60).toFixed(1)}min ago`}
                </span>
              </div>
              {data.monitor.metrics && (
                <div className="flex justify-between">
                  <span className="text-gray-500 text-sm">Started</span>
                  <span className="text-white text-sm">
                    {new Date(data.monitor.metrics.started_at).toLocaleTimeString()}
                  </span>
                </div>
              )}
            </div>
          </div>

          <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
            <div className="flex items-center gap-2 mb-3">
              <Shield className="w-4 h-4 text-purple-400" />
              <h3 className="text-sm font-medium text-gray-400">Protocol Stats</h3>
            </div>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-gray-500 text-sm">Positions Registered</span>
                <span className="text-white text-sm">0</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 text-sm">Protections Executed</span>
                <span className="text-white text-sm">0</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 text-sm">Total Value Protected</span>
                <span className="text-white text-sm">$0</span>
              </div>
            </div>
          </div>
        </div>

        {/* Recent Events */}
        <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between">
            <h3 className="text-lg font-semibold">Recent Events</h3>
            <span className="text-sm text-gray-500">{data.events.length} captured</span>
          </div>
          <div className="overflow-x-auto">
            {data.events.length === 0 ? (
              <div className="px-6 py-12 text-center text-gray-500">
                <Activity className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p>No events yet</p>
                <p className="text-xs mt-2">Events will appear when contracts are interacted with</p>
              </div>
            ) : (
              <table className="w-full">
                <thead>
                  <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    <th className="px-6 py-3">Time</th>
                    <th className="px-6 py-3">Type</th>
                    <th className="px-6 py-3">Contract</th>
                    <th className="px-6 py-3">Block</th>
                    <th className="px-6 py-3">TX Hash</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {data.events.map((event, i) => (
                    <tr key={i} className="hover:bg-gray-800/50">
                      <td className="px-6 py-3 text-sm text-gray-400">
                        {new Date(event.timestamp).toLocaleTimeString()}
                      </td>
                      <td className="px-6 py-3 text-sm">
                        <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 text-xs rounded">
                          {event.type}
                        </span>
                      </td>
                      <td className="px-6 py-3 text-sm text-white">{event.contract || '-'}</td>
                      <td className="px-6 py-3 text-sm font-mono text-gray-400">{event.block || '-'}</td>
                      <td className="px-6 py-3 text-sm font-mono text-gray-400">
                        {event.tx_hash ? (
                          <a
                            href={`${data.blockchain.explorer}/tx/${event.tx_hash}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-400 hover:text-blue-300"
                          >
                            {event.tx_hash.slice(0, 10)}...
                          </a>
                        ) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <footer className="mt-12 py-6 border-t border-gray-800 text-center text-gray-500 text-sm">
          <p>DeFi AI Liquidation Protection Protocol</p>
          <p className="mt-1 text-xs">Live on Monad Testnet • Updates every 5s</p>
        </footer>
      </main>
    </div>
  );
}
