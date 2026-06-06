/**
 * config.ts — Load and persist GitPhone configuration from VS Code globalState.
 * Config survives restarts. Never stored in workspace settings (global to user).
 */

import * as vscode from 'vscode';

export interface GitPhoneConfig {
  telegramId: string;
  githubToken: string;
  defaultRepo: string;
  branch: string;
  backendUrl: string;
  schemaVersion: number;
}

const CONFIG_KEY = 'gitphone_config';

let _context: vscode.ExtensionContext;

export function initConfig(context: vscode.ExtensionContext): void {
  _context = context;
}

export function getConfig(): GitPhoneConfig | undefined {
  return _context.globalState.get<GitPhoneConfig>(CONFIG_KEY);
}

export function saveConfig(config: GitPhoneConfig): void {
  _context.globalState.update(CONFIG_KEY, config);
}

export function clearConfig(): void {
  _context.globalState.update(CONFIG_KEY, undefined);
}

export function isConfigured(): boolean {
  const cfg = getConfig();
  return !!(
    cfg &&
    cfg.telegramId &&
    cfg.githubToken &&
    cfg.defaultRepo &&
    cfg.backendUrl
  );
}

export function getBackendUrl(): string {
  const cfg = getConfig();
  return cfg?.backendUrl ?? 'https://gitphone.onrender.com';
}
