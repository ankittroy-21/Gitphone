/**
 * statusBar.ts — Manages the GitPhone status bar item at the bottom of VS Code.
 * Always visible. Clicking opens setup or info panel.
 */

import * as vscode from 'vscode';

const STATUS_BAR_PRIORITY = 100;
let _statusBar: vscode.StatusBarItem;
let _stagedCount = 0;

export function initStatusBar(): vscode.StatusBarItem {
  _statusBar = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left,
    STATUS_BAR_PRIORITY,
  );
  _statusBar.command = 'gitphone.openPanel';
  _statusBar.show();
  return _statusBar;
}

export function setDisconnected(): void {
  _statusBar.text = '$(warning) GitPhone — Disconnected';
  _statusBar.tooltip = 'GitPhone: Not connected — click to set up';
  _statusBar.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
}

export function setConnected(stagedCount: number = 0): void {
  _stagedCount = stagedCount;
  _statusBar.text = `$(check) GitPhone — ${stagedCount} staged`;
  _statusBar.tooltip = `GitPhone: ${stagedCount} file(s) staged. Click to open panel.`;
  _statusBar.backgroundColor = undefined;
}

export function setSyncing(): void {
  _statusBar.text = '$(sync~spin) GitPhone — Syncing...';
  _statusBar.tooltip = 'GitPhone: Syncing file to backend';
  _statusBar.backgroundColor = undefined;
}

export function setError(message: string): void {
  _statusBar.text = '$(error) GitPhone — Error';
  _statusBar.tooltip = `GitPhone error: ${message}`;
  _statusBar.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
}

export function setInactive(): void {
  _statusBar.text = '$(circle-slash) GitPhone — Inactive';
  _statusBar.tooltip = 'GitPhone: Account dormant. Click to reactivate.';
  _statusBar.backgroundColor = undefined;
}

export function increment(): void {
  _stagedCount++;
  setConnected(_stagedCount);
}

export function decrement(by: number = 1): void {
  _stagedCount = Math.max(0, _stagedCount - by);
  setConnected(_stagedCount);
}

export function dispose(): void {
  _statusBar?.dispose();
}
