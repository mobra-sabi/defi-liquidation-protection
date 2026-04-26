import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const VISITS_FILE = path.join(process.cwd(), '..', 'monitor', 'visits.jsonl');
const REPO = 'mobra-sabi/defi-liquidation-protection';

export async function GET() {
  try {
    // Load all visits
    let allVisits: any[] = [];
    try {
      const content = fs.readFileSync(VISITS_FILE, 'utf8');
      allVisits = content.trim().split('\n')
        .filter(l => l.trim())
        .map(l => JSON.parse(l));
    } catch (e) {
      // File doesn't exist yet
    }
    
    // Filter: bots/curl explicitly excluded
    let visits = allVisits.filter(v => v.browser !== 'Bot' && v.browser !== 'curl');
    
    // Detect likely automated traffic (same screen + same browser + internal referer = probably bot)
    const automatedCount = visits.filter(v => {
      const ref = (v.referer || '').replace(/^https?:\/\//, '').split('/')[0];
      return ref === 'defi.cddc-global.com' && v.screen === '1920x1080';
    }).length;
    const externalVisits = visits.filter(v => {
      const ref = (v.referer || '').replace(/^https?:\/\//, '').split('/')[0];
      return ref !== 'defi.cddc-global.com' || v.screen !== '1920x1080';
    });
    
    // Get GitHub stats
    let githubStats: any = null;
    try {
      const ghRes = await fetch(`https://api.github.com/repos/${REPO}`);
      if (ghRes.ok) {
        const gh = await ghRes.json();
        githubStats = {
          stars: gh.stargazers_count,
          watchers: gh.subscribers_count,
          forks: gh.forks_count,
          open_issues: gh.open_issues_count,
          size_kb: gh.size,
          updated: gh.updated_at,
        };
      }
    } catch (e) {}
    
    // Calculate stats
    const now = new Date();
    const dayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    const hourAgo = new Date(now.getTime() - 60 * 60 * 1000);
    
    const visits24h = visits.filter(v => new Date(v.timestamp) > dayAgo);
    const visits1h = visits.filter(v => new Date(v.timestamp) > hourAgo);
    
    // Unique visitors (by ip_hash)
    const unique24h = new Set(visits24h.map(v => v.ip_hash)).size;
    const uniqueAll = new Set(visits.map(v => v.ip_hash)).size;
    
    // Aggregations
    const countries: Record<string, number> = {};
    const browsers: Record<string, number> = {};
    const devices: Record<string, number> = {};
    const referers: Record<string, number> = {};
    const hourlyVisits: Record<string, number> = {};
    
    for (const v of visits24h) {
      countries[v.country] = (countries[v.country] || 0) + 1;
      browsers[v.browser] = (browsers[v.browser] || 0) + 1;
      devices[v.device] = (devices[v.device] || 0) + 1;
      
      const ref = (v.referer || 'direct').replace(/^https?:\/\//, '').split('/')[0];
      referers[ref] = (referers[ref] || 0) + 1;
      
      const hour = v.timestamp.slice(0, 13); // YYYY-MM-DDTHH
      hourlyVisits[hour] = (hourlyVisits[hour] || 0) + 1;
    }
    
    // Recent visits (last 10, anonymized)
    const recentVisits = visits.slice(-10).reverse().map(v => ({
      timestamp: v.timestamp,
      country: v.country,
      browser: v.browser,
      device: v.device,
      path: v.path,
      referer: v.referer === 'direct' ? 'direct' : v.referer.replace(/^https?:\/\//, '').split('/')[0],
    }));
    
    return NextResponse.json({
      total_visits: visits.length,
      visits_24h: visits24h.length,
      visits_1h: visits1h.length,
      unique_24h: unique24h,
      unique_total: uniqueAll,
      automated_traffic: automatedCount,
      real_visits: externalVisits.length,
      countries: sortObj(countries).slice(0, 10),
      browsers: sortObj(browsers).slice(0, 5),
      devices: sortObj(devices),
      referers: sortObj(referers).slice(0, 5),
      hourly: hourlyVisits,
      recent: recentVisits,
      github: githubStats,
    });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

function sortObj(obj: Record<string, number>): Array<[string, number]> {
  return Object.entries(obj).sort(([, a], [, b]) => b - a);
}
