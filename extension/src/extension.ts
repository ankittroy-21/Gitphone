import * as vscode from 'vscode';
import { initConfig, isConfigured, getConfig } from './config';
import { initCache, clearAll as clearCache } from './localCache';
import { initStatusBar, setConnected, setDisconnected, dispose as disposeStatusBar } from './statusBar';
import { SetupPanel } from './setupPanel';
import { getVersion, healthCheck } from './api';
import {
  GitPhoneSidebarProvider,
  FileItem,
  showFileDiff,
  syncStagedToBackend,
} from './stagedFilesProvider';
import {
  onFileSaved,
  onFileCreated,
  onFileDeleted,
  onFileRenamed,
} from './fileWatcher';
import axios from 'axios';

// --- Global provider instance -------------------------------------------------
let sidebarProvider: GitPhoneSidebarProvider;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  console.log('[GitPhone] Extension activating...');

  // --- Initialize modules ----------------------------------------------------
  initConfig(context);
  initCache(context);
  initStatusBar();

  // --- Sidebar TreeView ------------------------------------------------------
  sidebarProvider = new GitPhoneSidebarProvider();
  const treeView = vscode.window.createTreeView('gitphone.stagedFiles', {
    treeDataProvider: sidebarProvider,
    showCollapseAll: false,
  });
  context.subscriptions.push(treeView);
  context.subscriptions.push({ dispose: () => sidebarProvider.dispose() });

  // --- Register file watchers (Real-time Sync) -------------------------------
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(onFileSaved),
    vscode.workspace.onDidCreateFiles(e => e.files.forEach(onFileCreated)),
    vscode.workspace.onDidDeleteFiles(e => e.files.forEach(onFileDeleted)),
    vscode.workspace.onDidRenameFiles(e => e.files.forEach(f => onFileRenamed(f.oldUri, f.newUri)))
  );

  // Badge = total changes (fires every time git state changes)
  sidebarProvider.onDidChangeTreeData(() => {
    const total = sidebarProvider.allChanges.length;
    treeView.title = total > 0
      ? `Source Control (${total}M)`
      : 'Source Control';
    treeView.badge = total > 0
      ? { tooltip: `${total} files changed`, value: total }
      : undefined;
    setConnected(total);
  });

  // --- Register commands -----------------------------------------------------
  context.subscriptions.push(

    // Setup panel
    vscode.commands.registerCommand('gitphone.openSetup', () => {
      SetupPanel.createOrShow(context.extensionUri);
    }),

    // Open panel / status menu
    vscode.commands.registerCommand('gitphone.openPanel', () => {
      if (isConfigured()) {
        showStatusMenu();
      } else {
        SetupPanel.createOrShow(context.extensionUri);
      }
    }),

    // Refresh sidebar manually
    vscode.commands.registerCommand('gitphone.refreshStagedFiles', () => {
      sidebarProvider.refresh();
    }),

    // Show diff when clicking a file
    vscode.commands.registerCommand('gitphone.showFileDiff', async (
      change: any, section: any, repoRoot: string
    ) => {
      await showFileDiff(change, section, repoRoot);
    }),

    // Sync ALL modified files to GitPhone backend -> appear in Telegram /files
    vscode.commands.registerCommand('gitphone.syncToTelegram', async () => {
      await syncStagedToBackend(sidebarProvider, context);
    }),

    // Clear local cache
    vscode.commands.registerCommand('gitphone.clearCache', async () => {
      const confirm = await vscode.window.showWarningMessage(
        'Clear GitPhone local cache? This resets all cached file SHAs.',
        'Clear Cache',
        'Cancel',
      );
      if (confirm === 'Clear Cache') {
        clearCache();
        vscode.window.showInformationMessage('GitPhone cache cleared.');
      }
    }),

    // Check status
    vscode.commands.registerCommand('gitphone.checkStatus', () => {
      showStatusMenu();
    }),

    // Diagnose
    vscode.commands.registerCommand('gitphone.diagnose', async () => {
      const config = getConfig();
      const lines: string[] = ['\n=== GitPhone Diagnostics ===\n'];

      if (!config) {
        lines.push('x NOT CONFIGURED - run Connect GitPhone first');
        vscode.window.showErrorMessage('GitPhone not configured. Open Setup first.');
        return;
      }

      lines.push(`[OK] Telegram ID : ${config.telegramId}`);
      lines.push(`[OK] Repo         : ${config.defaultRepo}`);
      lines.push(`[OK] Branch       : ${config.branch}`);
      lines.push(`[OK] Backend URL  : ${config.backendUrl}`);

      const repo = sidebarProvider.repository;
      lines.push(`[OK] Git repo     : ${repo?.rootUri.fsPath ?? 'NOT FOUND'}`);
      const totalChanges = sidebarProvider.allChanges.length;
      lines.push(`[OK] Changes      : ${totalChanges} file(s)`);

      try {
        const health = await axios.get(`${config.backendUrl}/health`, { timeout: 8000 });
        lines.push(`[OK] Backend health: ${JSON.stringify(health.data)}`);
      } catch (e: any) {
        lines.push(`[Error] Backend UNREACHABLE: ${e.message}`);
      }

      const output = lines.join('\n');
      console.log(output);
      const channel = vscode.window.createOutputChannel('GitPhone Diagnostics');
      channel.appendLine(output);
      channel.show();
    }),
  );

  // --- Startup logic ---------------------------------------------------------
  if (isConfigured()) {
    await onStartupConfigured(context);
  } else {
    setDisconnected();
    vscode.window.showInformationMessage(
      'GitPhone is not configured yet. Set it up to start committing from Telegram!',
      'Open Setup',
      'Later',
    ).then(choice => {
      if (choice === 'Open Setup') {
        SetupPanel.createOrShow(context.extensionUri);
      }
    }).catch(() => {});
  }

  context.subscriptions.push({ dispose: disposeStatusBar });
  console.log('[GitPhone] Extension activated [OK]');
}

/**
 * Runs when extension starts and is already configured.
 */
async function onStartupConfigured(context: vscode.ExtensionContext): Promise<void> {
  const config = getConfig()!;

  const healthy = await healthCheck();
  if (!healthy) {
    setDisconnected();
    vscode.window.showWarningMessage(
      `GitPhone: Cannot reach backend (${config.backendUrl}). ` +
      'Check your backend URL or try again later.',
    );
    return;
  }

  checkSchemaVersion().catch(console.error);
  setConnected(0);
}

/**
 * Schema version check - notifies user if backend has a newer schema.
 */
async function checkSchemaVersion(): Promise<void> {
  try {
    const response = await getVersion();
    const serverVersion = response.schema_version;
    const config = getConfig();
    const localVersion = config?.schemaVersion ?? 1;

    if (serverVersion > localVersion) {
      const choice = await vscode.window.showWarningMessage(
        `GitPhone schema update required (v${localVersion} -> v${serverVersion})`,
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
    // Backend unreachable - already handled in onStartupConfigured
  }
}

/**
 * Quick-pick menu when user clicks the status bar while configured.
 */
async function showStatusMenu(): Promise<void> {
  const config = getConfig();
  if (!config) return;

  const staged  = sidebarProvider.stagedChanges.length;
  const changed = sidebarProvider.workingTreeChanges.length;

  const items = [
    {
      label: '$(info) GitPhone Status',
      description: `${config.defaultRepo} - ${config.branch} - ${staged}S ${changed}M`,
      action: 'status',
    },
    {
      label: '$(cloud-upload) Sync staged files to Telegram',
      description: `Push ${staged} staged file(s) to /files`,
      action: 'sync',
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
    case 'sync':
      vscode.commands.executeCommand('gitphone.syncToTelegram');
      break;
    case 'setup':
      SetupPanel.createOrShow(vscode.Uri.parse(''));
      break;
    case 'cache':
      vscode.commands.executeCommand('gitphone.clearCache');
      break;
    case 'status':
      vscode.window.showInformationMessage(
        `GitPhone [OK]\nRepo: ${config.defaultRepo} - ${config.branch}\nBackend: ${config.backendUrl}`,
      );
      break;
  }
}


export function deactivate(): void {
  console.log('[GitPhone] Extension deactivated');
}
