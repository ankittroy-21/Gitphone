/**
 * extension.ts — GitPhone VS Code Extension entry point.
 * Registers all commands, activates the file watcher, and manages lifecycle.
 */

import * as vscode from 'vscode';
import { initConfig, isConfigured, getConfig } from './config';
import { initCache, clearAll as clearCache } from './localCache';
import { initStatusBar, setConnected, setDisconnected, dispose as disposeStatusBar } from './statusBar';
import { onFileSaved, resetStagedCount } from './fileWatcher';
import { SetupPanel } from './setupPanel';
import { getVersion, healthCheck } from './api';


export async function activate(context: vscode.ExtensionContext): Promise<void> {
  console.log('[GitPhone] Extension activating...');

  // ── Initialize modules ────────────────────────────────────────────────────
  initConfig(context);
  initCache(context);
  initStatusBar();

  // ── Register commands ─────────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('gitphone.openSetup', () => {
      SetupPanel.createOrShow(context.extensionUri);
    }),

    vscode.commands.registerCommand('gitphone.openPanel', () => {
      if (isConfigured()) {
        // Show quick-pick info menu when already configured
        showStatusMenu();
      } else {
        SetupPanel.createOrShow(context.extensionUri);
      }
    }),

    vscode.commands.registerCommand('gitphone.clearCache', async () => {
      const confirm = await vscode.window.showWarningMessage(
        'Clear GitPhone local cache? This will reset all cached file SHAs.',
        'Clear Cache',
        'Cancel',
      );
      if (confirm === 'Clear Cache') {
        clearCache();
        resetStagedCount(0);
        vscode.window.showInformationMessage('GitPhone cache cleared.');
      }
    }),

    vscode.commands.registerCommand('gitphone.checkStatus', () => {
      showStatusMenu();
    }),
  );

  // ── File watcher ──────────────────────────────────────────────────────────
  const saveListener = vscode.workspace.onDidSaveTextDocument(
    (document) => onFileSaved(document),
  );
  context.subscriptions.push(saveListener);

  // ── Startup logic ─────────────────────────────────────────────────────────
  if (isConfigured()) {
    await onStartupConfigured(context);
  } else {
    setDisconnected();
    // Prompt setup on first install
    const choice = await vscode.window.showInformationMessage(
      '📱 GitPhone is not configured yet. Set it up to start committing from Telegram!',
      'Open Setup',
      'Later',
    );
    if (choice === 'Open Setup') {
      SetupPanel.createOrShow(context.extensionUri);
    }
  }

  context.subscriptions.push({ dispose: disposeStatusBar });
  console.log('[GitPhone] Extension activated ✅');
}

/**
 * Runs when extension starts and is already configured.
 * Checks backend health and shows staged count.
 */
async function onStartupConfigured(context: vscode.ExtensionContext): Promise<void> {
  const config = getConfig()!;

  // Quick health check
  const healthy = await healthCheck();
  if (!healthy) {
    setDisconnected();
    vscode.window.showWarningMessage(
      `GitPhone: Cannot reach backend (${config.backendUrl}). ` +
      'Check your backend URL or try again later.',
    );
    return;
  }

  // Schema version check (non-blocking)
  checkSchemaVersion().catch(console.error);

  // Start with 0 — the status bar updates on next file save
  setConnected(0);
}

/**
 * Schema version check — notifies user if backend has a newer schema.
 */
async function checkSchemaVersion(): Promise<void> {
  try {
    const response = await getVersion();
    const serverVersion = response.schema_version;
    const config = getConfig();
    const localVersion = config?.schemaVersion ?? 1;

    if (serverVersion > localVersion) {
      const choice = await vscode.window.showWarningMessage(
        `GitPhone schema update required (v${localVersion} → v${serverVersion})`,
        'How To Update',
        'Copy SQL',
        'Later',
      );
      if (choice === 'Copy SQL' && response.migration_sql) {
        await vscode.env.clipboard.writeText(response.migration_sql);
        vscode.window.showInformationMessage(
          'Migration SQL copied! Paste it in your Supabase SQL editor.',
        );
      }
      if (choice === 'How To Update') {
        vscode.env.openExternal(vscode.Uri.parse(response.docs_url));
      }
    }
  } catch {
    // Backend unreachable — already handled in onStartupConfigured
  }
}

/**
 * Quick-pick menu when user clicks the status bar while configured.
 */
async function showStatusMenu(): Promise<void> {
  const config = getConfig();
  if (!config) return;

  const items = [
    {
      label: '$(info) GitPhone Status',
      description: `${config.defaultRepo} • ${config.branch}`,
      action: 'status',
    },
    {
      label: '$(gear) Open Setup',
      description: 'Reconfigure your GitPhone connection',
      action: 'setup',
    },
    {
      label: '$(trash) Clear Cache',
      description: 'Reset local diff cache (use if diffs are wrong)',
      action: 'cache',
    },
  ];

  const selected = await vscode.window.showQuickPick(items, {
    placeHolder: 'GitPhone Actions',
  });

  if (!selected) return;

  switch (selected.action) {
    case 'setup':
      SetupPanel.createOrShow(vscode.Uri.parse(''));
      break;
    case 'cache':
      vscode.commands.executeCommand('gitphone.clearCache');
      break;
    case 'status':
      vscode.window.showInformationMessage(
        `GitPhone ✅\nRepo: ${config.defaultRepo} • ${config.branch}\nBackend: ${config.backendUrl}`,
      );
      break;
  }
}


export function deactivate(): void {
  console.log('[GitPhone] Extension deactivated');
}
