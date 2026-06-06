/**
 * fileWatcher.ts — Watches for file saves and syncs diffs to the backend.
 * This is the core extension feature — triggered by vscode.workspace.onDidSaveTextDocument.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

import { isConfigured, getConfig } from './config';
import { getContent, getSha } from './localCache';
import { detectBinary, detectMinified, normalizeLineEndings, computeDiff } from './diffEngine';
import { syncFile, extractErrorMessage } from './api';
import { setSyncing, setConnected, setError, increment } from './statusBar';

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

let _stagedCount = 0;

/**
 * Called on every file save event.
 * Computes diff and POSTs to /sync-file.
 */
export async function onFileSaved(document: vscode.TextDocument): Promise<void> {
  // ── Guard: must be configured ───────────────────────────────────────────
  if (!isConfigured()) {
    return;
  }

  const config = getConfig()!;
  const filePath = document.uri.fsPath;

  // ── Guard: must be inside a workspace ──────────────────────────────────
  const workspaceFolders = vscode.workspace.workspaceFolders;
  if (!workspaceFolders || workspaceFolders.length === 0) {
    return;
  }
  const workspaceRoot = workspaceFolders[0].uri.fsPath;

  // Only watch files inside the workspace
  if (!filePath.startsWith(workspaceRoot)) {
    return;
  }

  const relativePath = path.relative(workspaceRoot, filePath).replace(/\\/g, '/');

  // ── Guard: skip gitignored-style patterns ──────────────────────────────
  if (shouldIgnore(relativePath)) {
    return;
  }

  // ── Step 1: Size check (read stat only, not file content yet) ──────────
  let stats: fs.Stats;
  try {
    stats = fs.statSync(filePath);
  } catch {
    return; // File deleted after save event — ignore
  }

  if (stats.size > MAX_FILE_SIZE) {
    const sizeMB = (stats.size / (1024 * 1024)).toFixed(1);
    vscode.window.showWarningMessage(
      `⚠️ GitPhone: ${path.basename(relativePath)} skipped (${sizeMB}MB). ` +
      `Exceeds 10MB limit. Consider adding to .gitignore.`
    );
    return;
  }

  // ── Step 2: Binary / minified detection ────────────────────────────────
  const isBinary = detectBinary(filePath);
  const isMinified = detectMinified(relativePath);

  // ── Step 3: Build payload ───────────────────────────────────────────────
  let diffText: string | null = null;
  let fullContent: string | null = null;

  if (isBinary || isMinified) {
    // Store full file as base64
    try {
      const rawBytes = fs.readFileSync(filePath);
      fullContent = rawBytes.toString('base64');
    } catch (err) {
      console.error(`[GitPhone] Failed to read binary file: ${err}`);
      return;
    }
  } else {
    // Text file — compute diff against cached version
    let rawContent: string;
    try {
      rawContent = fs.readFileSync(filePath, 'utf8');
    } catch (err) {
      console.error(`[GitPhone] Failed to read file: ${err}`);
      return;
    }

    const normalizedNew = normalizeLineEndings(rawContent);
    const cachedContent = getContent(relativePath) ?? '';
    const normalizedOld = normalizeLineEndings(cachedContent);

    diffText = computeDiff(normalizedOld, normalizedNew, relativePath);
    if (!diffText) {
      return; // No actual changes — skip sync
    }
  }

  // ── Step 4: Get base SHA from cache ────────────────────────────────────
  const baseSha = getSha(relativePath) ?? 'new_file';

  // ── Step 5: POST to backend ─────────────────────────────────────────────
  setSyncing();
  try {
    await syncFile({
      telegram_id: config.telegramId,
      filepath: relativePath,
      diff: diffText,
      full_content: fullContent,
      base_sha: baseSha,
      is_binary: isBinary,
      file_size: stats.size,
    });

    _stagedCount++;
    setConnected(_stagedCount);
    increment();

  } catch (err) {
    const message = extractErrorMessage(err);
    console.error(`[GitPhone] Sync failed: ${message}`);

    // Don't spam the user on every save — just show in status bar
    setError(`Sync failed: ${message}`);

    // Restore staged count after 3 seconds
    setTimeout(() => {
      setConnected(_stagedCount);
    }, 3000);
  }
}

export function resetStagedCount(count: number = 0): void {
  _stagedCount = count;
  setConnected(_stagedCount);
}

/**
 * Returns true if the file should be ignored (node_modules, .git, etc.)
 */
function shouldIgnore(relativePath: string): boolean {
  const ignoredPrefixes = [
    '.git/',
    'node_modules/',
    '.next/',
    '__pycache__/',
    '.venv/',
    'venv/',
    'dist/',
    'build/',
    '.DS_Store',
  ];
  const ignoredExtensions = ['.log', '.lock'];

  for (const prefix of ignoredPrefixes) {
    if (relativePath.startsWith(prefix) || relativePath.includes(`/${prefix}`)) {
      return true;
    }
  }
  for (const ext of ignoredExtensions) {
    if (relativePath.endsWith(ext)) {
      return true;
    }
  }
  return false;
}
