import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import crypto from 'crypto';

const VISITS_FILE = path.join(process.cwd(), '..', 'monitor', 'visits.jsonl');

function hashIP(ip: string): string {
  // Hash IP for privacy (one-way, can't be reversed)
  return crypto.createHash('sha256').update(ip + 'defi-protection-salt').digest('hex').slice(0, 12);
}

export async function POST(req: NextRequest) {
  try {
    // Get visitor info from Cloudflare headers
    const ip = req.headers.get('cf-connecting-ip') || 
               req.headers.get('x-forwarded-for') || 
               req.headers.get('x-real-ip') || 
               'unknown';
    const country = req.headers.get('cf-ipcountry') || 'XX';
    const userAgent = req.headers.get('user-agent') || 'unknown';
    const referer = req.headers.get('referer') || 'direct';
    
    // Parse user agent for browser/OS
    const browser = parseBrowser(userAgent);
    const os = parseOS(userAgent);
    const deviceType = parseDevice(userAgent);
    
    // Get path from request body
    const body = await req.json().catch(() => ({}));
    const path_visited = body.path || '/';
    const screen = body.screen || null;
    
    const visit = {
      timestamp: new Date().toISOString(),
      ip_hash: hashIP(ip),
      country,
      browser,
      os,
      device: deviceType,
      path: path_visited,
      referer: referer.length > 200 ? referer.slice(0, 200) : referer,
      screen,
    };
    
    // Append to file
    fs.appendFileSync(VISITS_FILE, JSON.stringify(visit) + '\n');
    
    return NextResponse.json({ ok: true });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

function parseBrowser(ua: string): string {
  if (/Edg/i.test(ua)) return 'Edge';
  if (/Chrome/i.test(ua)) return 'Chrome';
  if (/Firefox/i.test(ua)) return 'Firefox';
  if (/Safari/i.test(ua)) return 'Safari';
  if (/Opera|OPR/i.test(ua)) return 'Opera';
  if (/curl/i.test(ua)) return 'curl';
  if (/bot|crawler|spider/i.test(ua)) return 'Bot';
  return 'Other';
}

function parseOS(ua: string): string {
  if (/Windows/i.test(ua)) return 'Windows';
  if (/Mac OS X|Macintosh/i.test(ua)) return 'macOS';
  if (/Android/i.test(ua)) return 'Android';
  if (/iPhone|iPad|iOS/i.test(ua)) return 'iOS';
  if (/Linux/i.test(ua)) return 'Linux';
  return 'Other';
}

function parseDevice(ua: string): string {
  if (/Mobile/i.test(ua)) return 'mobile';
  if (/Tablet/i.test(ua)) return 'tablet';
  return 'desktop';
}
