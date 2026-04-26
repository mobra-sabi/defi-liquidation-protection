'use client';

import React, { useState, useEffect } from 'react';
import { 
  Shield, Activity, AlertTriangle, Clock, Box, Zap, 
  ExternalLink, Wifi, WifiOff, Github, BookOpen,
  Rocket, Target, BarChart3, Lock, ArrowRight, Droplet,
  Star, Eye, Globe, Users, GitFork, TrendingUp
} from 'lucide-react';

interface StatusData {
  blockchain: { connected: boolean; block: number; chainId: number; gasPrice: string; explorer: string; };
  wallet: { address: string; balance: string; };
  contracts: Record<string, { address: string; name: string }>;
  monitor: {
    active: boolean;
    lastUpdateSeconds: number;
    metrics: { blocks_monitored: number; events_captured: number; uptime_seconds: number; started_at: string; last_block: number; } | null;
  };
  events: any[];
}

interface AnalyticsData {
  total_visits: number;
  visits_24h: number;
  visits_1h: number;
  unique_24h: number;
  unique_total: number;
  countries: Array<[string, number]>;
  browsers: Array<[string, number]>;
  devices: Array<[string, number]>;
  referers: Array<[string, number]>;
  recent: Array<{
    timestamp: string;
    country: string;
    browser: string;
    device: string;
    path: string;
    referer: string;
  }>;
  github: {
    stars: number;
    watchers: number;
    forks: number;
    open_issues: number;
  } | null;
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

const ContractCard = ({ name, address, explorer }: any) => (
  <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
    <div className="flex items-center justify-between mb-2">
      <h4 className="font-bold text-white">{name}</h4>
      <span className="px-2 py-0.5 bg-green-500/20 text-green-400 text-xs rounded-full border border-green-500/30">
        DEPLOYED
      </span>
    </div>
    <div className="font-mono text-xs text-gray-400 mb-2 break-all">{address}</div>
    <a href={`${explorer}/address/${address}`} target="_blank" rel="noopener noreferrer"
       className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors">
      View on Explorer <ExternalLink className="w-3 h-3" />
    </a>
  </div>
);

const StepCard = ({ number, title, description, icon: Icon, color, link }: any) => (
  <div className="bg-gray-900 rounded-lg p-6 border border-gray-800 hover:border-blue-500/50 transition-all relative">
    <div className="absolute -top-3 -left-3 w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center font-bold text-white text-sm">
      {number}
    </div>
    <Icon className={`w-8 h-8 ${color} mb-3`} />
    <h4 className="text-lg font-bold text-white mb-2">{title}</h4>
    <p className="text-sm text-gray-400 mb-3">{description}</p>
    {link && (
      <a href={link} target="_blank" rel="noopener noreferrer"
         className="inline-flex items-center gap-1 text-sm text-blue-400 hover:text-blue-300 transition-colors">
        Get started <ArrowRight className="w-4 h-4" />
      </a>
    )}
  </div>
);

const flagEmoji = (countryCode: string) => {
  if (!countryCode || countryCode === 'XX' || countryCode.length !== 2) return '🌐';
  const codePoints = countryCode.toUpperCase().split('').map(c => 127397 + c.charCodeAt(0));
  return String.fromCodePoint(...codePoints);
};

const countryName = (code: string) => {
  const names: Record<string, string> = {
    'RO': 'Romania', 'US': 'USA', 'GB': 'UK', 'DE': 'Germany', 'FR': 'France',
    'IT': 'Italy', 'ES': 'Spain', 'NL': 'Netherlands', 'PL': 'Poland', 'CA': 'Canada',
    'AU': 'Australia', 'JP': 'Japan', 'CN': 'China', 'IN': 'India', 'BR': 'Brazil',
    'MX': 'Mexico', 'RU': 'Russia', 'TR': 'Turkey', 'KR': 'South Korea', 'UA': 'Ukraine',
    'XX': 'Unknown',
  };
  return names[code] || code;
};

export default function Dashboard() {
  const [data, setData] = useState<StatusData | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<Date>(new Date());

  useEffect(() => {
    // Track this visit (only once per session)
    const tracked = sessionStorage.getItem('tracked');
    if (!tracked) {
      fetch('/api/track', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: window.location.pathname,
          screen: `${window.screen.width}x${window.screen.height}`,
        }),
      }).catch(() => {});
      sessionStorage.setItem('tracked', '1');
    }
    
    const fetchData = async () => {
      try {
        const [statusRes, analyticsRes] = await Promise.all([
          fetch('/api/status'),
          fetch('/api/analytics'),
        ]);
        
        if (statusRes.ok) setData(await statusRes.json());
        if (analyticsRes.ok) setAnalytics(await analyticsRes.json());
        
        setError(null);
        setLastFetch(new Date());
      } catch (e: any) {
        setError(e.message);
      }
    };
    
    fetchData();
    const interval = setInterval(fetchData, 5000);
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

  const timeAgo = (timestamp: string) => {
    const diff = Date.now() - new Date(timestamp).getTime();
    if (diff < 60000) return 'just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return `${Math.floor(diff / 86400000)}d ago`;
  };

  return (
    <div className="min-h-screen bg-black text-white">
      {/* Top Banner */}
      <div className="bg-gradient-to-r from-blue-600/20 via-purple-600/20 to-blue-600/20 border-b border-blue-500/20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2 text-center text-sm">
          <span className="text-blue-300">🚀 Protecting DeFi positions on Monad testnet</span>
          <span className="text-gray-500 mx-2">•</span>
          <span className="text-gray-400">Trained on 28,434 real Aave positions</span>
          <span className="text-gray-500 mx-2">•</span>
          <span className="text-green-400">Live</span>
        </div>
      </div>

      {/* Header */}
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
                <p className="text-xs text-gray-500">AI-Powered Liquidation Defense • Monad Testnet</p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {analytics?.github && (
                <a href="https://github.com/mobra-sabi/defi-liquidation-protection" target="_blank" rel="noopener noreferrer"
                   className="hidden sm:inline-flex items-center gap-1 px-3 py-1 bg-gray-800 text-yellow-400 rounded-full border border-gray-700 hover:border-yellow-500/50 transition-colors text-xs">
                  <Star className="w-3 h-3 fill-current" /> {analytics.github.stars}
                </a>
              )}
              <a href="https://github.com/mobra-sabi/defi-liquidation-protection" target="_blank" rel="noopener noreferrer"
                 className="text-gray-400 hover:text-white transition-colors p-2" title="GitHub">
                <Github className="w-5 h-5" />
              </a>
              {data.monitor.active ? (
                <span className="hidden sm:inline-flex items-center gap-2 px-3 py-1 bg-green-500/20 text-green-400 rounded-full border border-green-500/30 text-xs">
                  <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>
                  LIVE
                </span>
              ) : (
                <span className="hidden sm:inline-flex items-center gap-2 px-3 py-1 bg-yellow-500/20 text-yellow-400 rounded-full border border-yellow-500/30 text-xs">
                  IDLE
                </span>
              )}
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Hero */}
        <div className="mb-12 text-center">
          <h2 className="text-4xl md:text-5xl font-bold mb-4 bg-gradient-to-r from-white via-blue-100 to-purple-200 bg-clip-text text-transparent">
            Never Get Liquidated Again
          </h2>
          <p className="text-lg text-gray-400 max-w-3xl mx-auto mb-6">
            Non-custodial DeFi liquidation protection. Monitors your health factor 24/7 and 
            executes protective actions before liquidators do — without taking custody of your funds.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <span className="inline-flex items-center gap-2 px-4 py-2 bg-blue-500/10 text-blue-300 rounded-full border border-blue-500/30 text-sm">
              <Lock className="w-4 h-4" /> Non-custodial
            </span>
            <span className="inline-flex items-center gap-2 px-4 py-2 bg-green-500/10 text-green-300 rounded-full border border-green-500/30 text-sm">
              <Shield className="w-4 h-4" /> Real-time monitoring
            </span>
            <span className="inline-flex items-center gap-2 px-4 py-2 bg-purple-500/10 text-purple-300 rounded-full border border-purple-500/30 text-sm">
              <BarChart3 className="w-4 h-4" /> Open source
            </span>
          </div>
        </div>

        {/* === TRAFFIC ANALYTICS === */}
        {analytics && (
          <div className="mb-12">
            <h3 className="text-2xl font-bold mb-4 flex items-center gap-2">
              <TrendingUp className="w-6 h-6 text-blue-400" />
              Live Traffic & Community
            </h3>
            
            {/* Top metrics row */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
              <div className="bg-gradient-to-br from-blue-900/40 to-blue-800/20 rounded-lg p-4 border border-blue-500/20">
                <div className="flex items-center gap-2 mb-1">
                  <Eye className="w-4 h-4 text-blue-400" />
                  <span className="text-xs text-blue-300">Visits 1h</span>
                </div>
                <div className="text-2xl font-bold text-white">{analytics.visits_1h}</div>
              </div>
              <div className="bg-gradient-to-br from-purple-900/40 to-purple-800/20 rounded-lg p-4 border border-purple-500/20">
                <div className="flex items-center gap-2 mb-1">
                  <Eye className="w-4 h-4 text-purple-400" />
                  <span className="text-xs text-purple-300">Visits 24h</span>
                </div>
                <div className="text-2xl font-bold text-white">{analytics.visits_24h}</div>
              </div>
              <div className="bg-gradient-to-br from-green-900/40 to-green-800/20 rounded-lg p-4 border border-green-500/20">
                <div className="flex items-center gap-2 mb-1">
                  <Users className="w-4 h-4 text-green-400" />
                  <span className="text-xs text-green-300">Unique 24h</span>
                </div>
                <div className="text-2xl font-bold text-white">{analytics.unique_24h}</div>
              </div>
              <div className="bg-gradient-to-br from-cyan-900/40 to-cyan-800/20 rounded-lg p-4 border border-cyan-500/20">
                <div className="flex items-center gap-2 mb-1">
                  <Globe className="w-4 h-4 text-cyan-400" />
                  <span className="text-xs text-cyan-300">Total Visits</span>
                </div>
                <div className="text-2xl font-bold text-white">{analytics.total_visits}</div>
              </div>
              {analytics.github && (
                <>
                  <div className="bg-gradient-to-br from-yellow-900/40 to-yellow-800/20 rounded-lg p-4 border border-yellow-500/20">
                    <div className="flex items-center gap-2 mb-1">
                      <Star className="w-4 h-4 text-yellow-400" />
                      <span className="text-xs text-yellow-300">GitHub Stars</span>
                    </div>
                    <div className="text-2xl font-bold text-white">{analytics.github.stars}</div>
                  </div>
                  <div className="bg-gradient-to-br from-pink-900/40 to-pink-800/20 rounded-lg p-4 border border-pink-500/20">
                    <div className="flex items-center gap-2 mb-1">
                      <GitFork className="w-4 h-4 text-pink-400" />
                      <span className="text-xs text-pink-300">Forks</span>
                    </div>
                    <div className="text-2xl font-bold text-white">{analytics.github.forks}</div>
                  </div>
                </>
              )}
            </div>

            {/* Traffic detail */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Countries */}
              <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
                <div className="flex items-center gap-2 mb-3">
                  <Globe className="w-4 h-4 text-blue-400" />
                  <h4 className="text-sm font-semibold text-gray-300">Top Countries (24h)</h4>
                </div>
                {analytics.countries.length > 0 ? (
                  <div className="space-y-2">
                    {analytics.countries.slice(0, 5).map(([code, count]) => (
                      <div key={code} className="flex items-center justify-between">
                        <span className="text-sm text-gray-300">
                          <span className="mr-2">{flagEmoji(code)}</span>
                          {countryName(code)}
                        </span>
                        <span className="text-sm font-mono text-blue-400">{count}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-500">No visits yet</p>
                )}
              </div>

              {/* Browsers */}
              <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
                <h4 className="text-sm font-semibold text-gray-300 mb-3">Browsers (24h)</h4>
                {analytics.browsers.length > 0 ? (
                  <div className="space-y-2">
                    {analytics.browsers.map(([name, count]) => (
                      <div key={name} className="flex items-center justify-between">
                        <span className="text-sm text-gray-300">{name}</span>
                        <span className="text-sm font-mono text-purple-400">{count}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-500">No data yet</p>
                )}
              </div>

              {/* Devices */}
              <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
                <h4 className="text-sm font-semibold text-gray-300 mb-3">Devices (24h)</h4>
                {analytics.devices.length > 0 ? (
                  <div className="space-y-2">
                    {analytics.devices.map(([name, count]) => (
                      <div key={name} className="flex items-center justify-between">
                        <span className="text-sm text-gray-300 capitalize">{name}</span>
                        <span className="text-sm font-mono text-green-400">{count}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-500">No data yet</p>
                )}
              </div>

              {/* Referers */}
              <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
                <h4 className="text-sm font-semibold text-gray-300 mb-3">Top Referrers (24h)</h4>
                {analytics.referers.length > 0 ? (
                  <div className="space-y-2">
                    {analytics.referers.map(([name, count]) => (
                      <div key={name} className="flex items-center justify-between">
                        <span className="text-sm text-gray-300 truncate max-w-[140px]" title={name}>
                          {name === 'direct' ? '🔗 Direct' : name}
                        </span>
                        <span className="text-sm font-mono text-cyan-400">{count}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-500">No data yet</p>
                )}
              </div>
            </div>

            {/* Recent visitors */}
            {analytics.recent.length > 0 && (
              <div className="bg-gray-900 rounded-lg p-4 border border-gray-800 mt-4">
                <h4 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-green-400" />
                  Recent Visitors (anonymized)
                </h4>
                <div className="space-y-1.5 text-xs font-mono">
                  {analytics.recent.slice(0, 8).map((v, i) => (
                    <div key={i} className="flex items-center gap-2 text-gray-400">
                      <span className="w-16 text-gray-500">{timeAgo(v.timestamp)}</span>
                      <span className="w-6">{flagEmoji(v.country)}</span>
                      <span className="w-20 text-gray-300">{v.browser}</span>
                      <span className="w-16 text-gray-500 capitalize">{v.device}</span>
                      <span className="text-gray-400 truncate">
                        {v.referer === 'direct' ? '🔗 direct' : `← ${v.referer}`}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <div className="text-xs text-gray-500 mb-6 text-right">
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
            title="On-chain Events"
            value={data.monitor.metrics?.events_captured || 0}
            subtitle="Contract interactions"
            icon={Zap}
            color="text-yellow-400"
          />
        </div>

        {/* How It Works */}
        <div className="mb-12">
          <h3 className="text-2xl font-bold mb-4">How It Works</h3>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-gray-900 rounded-lg p-4 border border-green-500/30">
              <div className="text-green-400 text-sm font-bold mb-1">SAFE</div>
              <div className="text-2xl font-bold text-white mb-1">HF &gt; 1.30</div>
              <div className="text-xs text-gray-400">No action needed</div>
            </div>
            <div className="bg-gray-900 rounded-lg p-4 border border-yellow-500/30">
              <div className="text-yellow-400 text-sm font-bold mb-1">WARNING</div>
              <div className="text-2xl font-bold text-white mb-1">HF 1.15-1.30</div>
              <div className="text-xs text-gray-400">Notify user</div>
            </div>
            <div className="bg-gray-900 rounded-lg p-4 border border-orange-500/30">
              <div className="text-orange-400 text-sm font-bold mb-1">ALERT</div>
              <div className="text-2xl font-bold text-white mb-1">HF 1.05-1.15</div>
              <div className="text-xs text-gray-400">Prepare rebalancing</div>
            </div>
            <div className="bg-gray-900 rounded-lg p-4 border border-red-500/30">
              <div className="text-red-400 text-sm font-bold mb-1">CRITICAL</div>
              <div className="text-2xl font-bold text-white mb-1">HF &lt; 1.05</div>
              <div className="text-xs text-gray-400">Execute protection</div>
            </div>
          </div>
        </div>

        {/* How to test */}
        <div className="mb-12">
          <h3 className="text-2xl font-bold mb-2">Want to Test?</h3>
          <p className="text-gray-400 mb-6">Get involved as a beta tester. Help shape the protocol.</p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <StepCard number="1" title="Get Testnet Tokens" 
              description="Get free MON tokens from the Monad testnet faucet to interact with the protocol."
              icon={Droplet} color="text-blue-400" link="https://testnet.monad.xyz/faucet" />
            <StepCard number="2" title="Read the Code"
              description="All contracts are open source. Verify the logic, check for bugs, suggest improvements."
              icon={BookOpen} color="text-purple-400" link="https://github.com/mobra-sabi/defi-liquidation-protection" />
            <StepCard number="3" title="Try It Out"
              description="Interact with the contracts on testnet. Report bugs and feedback. Be a real user."
              icon={Rocket} color="text-green-400" link="https://testnet.monadexplorer.com/address/0x242Eb426481d3C1C2b635bcC8BF801ebC678a4E9" />
          </div>
        </div>

        {/* Contracts */}
        <div className="mb-12">
          <h3 className="text-2xl font-bold mb-4">Deployed Contracts</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {Object.entries(data.contracts).map(([name, info]) => (
              <ContractCard key={name} name={name} address={info.address} explorer={data.blockchain.explorer} />
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
              <div className="flex justify-between"><span className="text-gray-500 text-sm">Network</span><span className="text-white text-sm">Monad Testnet</span></div>
              <div className="flex justify-between"><span className="text-gray-500 text-sm">Gas Price</span><span className="text-white text-sm">{data.blockchain.gasPrice} gwei</span></div>
              <div className="flex justify-between"><span className="text-gray-500 text-sm">Latest Block</span><span className="text-white text-sm font-mono">{data.blockchain.block.toLocaleString()}</span></div>
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
                  <span className="text-white text-sm">{new Date(data.monitor.metrics.started_at).toLocaleTimeString()}</span>
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
              <div className="flex justify-between"><span className="text-gray-500 text-sm">Positions Registered</span><span className="text-white text-sm">0</span></div>
              <div className="flex justify-between"><span className="text-gray-500 text-sm">Protections Executed</span><span className="text-white text-sm">0</span></div>
              <div className="flex justify-between"><span className="text-gray-500 text-sm">Total Value Protected</span><span className="text-white text-sm">$0</span></div>
            </div>
          </div>
        </div>

        {/* CTA Section */}
        <div className="bg-gradient-to-r from-blue-600/10 via-purple-600/10 to-blue-600/10 rounded-xl border border-blue-500/30 p-8 mb-12 text-center">
          <h3 className="text-2xl font-bold mb-3">Looking for First Testers</h3>
          <p className="text-gray-400 mb-6 max-w-2xl mx-auto">
            Help shape this protocol. Test on Monad testnet, find bugs, suggest features. 
            Real feedback from real users is invaluable.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <a href="https://github.com/mobra-sabi/defi-liquidation-protection" target="_blank" rel="noopener noreferrer"
               className="inline-flex items-center gap-2 px-6 py-3 bg-white text-black font-semibold rounded-lg hover:bg-gray-200 transition-colors">
              <Github className="w-5 h-5" /> View on GitHub
              {analytics?.github?.stars ? (
                <span className="ml-1 px-2 py-0.5 bg-gray-200 text-black rounded text-xs flex items-center gap-1">
                  <Star className="w-3 h-3 fill-current" /> {analytics.github.stars}
                </span>
              ) : null}
            </a>
            <a href="https://testnet.monad.xyz/faucet" target="_blank" rel="noopener noreferrer"
               className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition-colors">
              <Droplet className="w-5 h-5" /> Get Testnet Tokens
            </a>
          </div>
        </div>

        {/* Footer */}
        <footer className="border-t border-gray-800 pt-8 pb-6">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="text-center md:text-left">
              <div className="flex items-center gap-2 mb-1">
                <Shield className="w-4 h-4 text-blue-400" />
                <span className="text-white font-bold">DeFi Protection</span>
              </div>
              <p className="text-xs text-gray-500">Built in 2 days. Live on Monad Testnet. Updates every 5s.</p>
            </div>
            <div className="flex items-center gap-4">
              <a href="https://github.com/mobra-sabi/defi-liquidation-protection" target="_blank" rel="noopener noreferrer"
                 className="text-gray-400 hover:text-white transition-colors text-sm flex items-center gap-1">
                <Github className="w-4 h-4" /> GitHub
              </a>
              <a href="https://testnet.monadexplorer.com" target="_blank" rel="noopener noreferrer"
                 className="text-gray-400 hover:text-white transition-colors text-sm flex items-center gap-1">
                <ExternalLink className="w-4 h-4" /> Explorer
              </a>
              <a href="https://monad.xyz" target="_blank" rel="noopener noreferrer"
                 className="text-gray-400 hover:text-white transition-colors text-sm">Monad</a>
            </div>
          </div>
          <div className="text-center mt-6 text-xs text-gray-600">
            <p>⚠️ Alpha software on testnet. Not for production use. Code is unaudited.</p>
            <p className="mt-1">© 2026 DeFi Protection Protocol • MIT License</p>
          </div>
        </footer>
      </main>
    </div>
  );
}
