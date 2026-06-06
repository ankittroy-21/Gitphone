/**
 * localCache.ts — Stores last-committed file content + SHA in VS Code globalState.
 * Used to compute diffs against the committed version (avoids GitHub API calls).
 * Survives VS Code restarts.
 */

import * as vscode from 'vscode';

interface CacheEntry {
  content: string;   // Last committed content (LF-normalized)
  sha: string;       // Git SHA of that committed version
  committedAt: string; // ISO timestamp
}

const KEY_PREFIX = 'gitphone_cache_';
let _context: vscode.ExtensionContext;

export function initCache(context: vscode.ExtensionContext): void {
  _context = context;
}

export function getContent(relativePath: string): string | undefined {
  const entry = _context.globalState.get<CacheEntry>(KEY_PREFIX + relativePath);
  return entry?.content;
}

export function getSha(relativePath: string): string | undefined {
  const entry = _context.globalState.get<CacheEntry>(KEY_PREFIX + relativePath);
  return entry?.sha;
}

export function setEntry(relativePath: string, content: string, sha: string): void {
  const entry: CacheEntry = {
    content,
    sha,
    committedAt: new Date().toISOString(),
  };
  _context.globalState.update(KEY_PREFIX + relativePath, entry);
}

export function removeEntry(relativePath: string): void {
  _context.globalState.update(KEY_PREFIX + relativePath, undefined);
}

export function clearAll(): void {
  // Clear all gitphone cache entries from globalState
  const keys = _context.globalState.keys();
  for (const key of keys) {
    if (key.startsWith(KEY_PREFIX)) {
      _context.globalState.update(key, undefined);
    }
  }
}
