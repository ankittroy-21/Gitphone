/**
 * stagedFilesProvider.ts - Real-time Git sidebar using vscode.git API.
 *
 * Shows two sections:
 *   STAGED CHANGES   - files in the git index (git add)
 *   CHANGES          - modified/untracked in working tree
 *
 * Clicking a file shows an inline VS Code diff.
 * + button stages a file. - button unstages.
 * "Send to GitPhone" button syncs staged files to the backend for Telegram commit.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import { getConfig, isConfigured } from './config';
import { syncFile, syncState, SyncFilePayload, extractErrorMessage } from './api';

// ── Git Extension API types (inline to avoid needing git.d.ts) ──────────────

interface GitChange {
  readonly uri: vscode.Uri;
  readonly originalUri: vscode.Uri;
  readonly renameUri: vscode.Uri | undefined;
  readonly status: number; // GitStatus enum values
}

interface GitRepository {
  readonly rootUri: vscode.Uri;
  readonly state: {
    readonly HEAD: { commit?: string; name?: string } | undefined;
    readonly indexChanges: GitChange[];          // staged
    readonly workingTreeChanges: GitChange[];    // unstaged modified
    readonly mergeChanges: GitChange[];
    readonly onDidChange: vscode.Event<void>;
  };
  add(resources: vscode.Uri[]): Promise<void>;
  revert(resources: vscode.Uri[]): Promise<void>;
  diff(cached?: boolean): Promise<string>;
  diffWithHEAD(path: string): Promise<string>;
  diffIndexWithHEAD(path: string): Promise<string>;
}

interface GitAPI {
  repositories: GitRepository[];
  onDidOpenRepository: vscode.Event<GitRepository>;
}

// Git Status enum (from vscode.git extension)
const GitStatus = {
  INDEX_MODIFIED:  0,
  INDEX_ADDED:     1,
  INDEX_DELETED:   2,
  INDEX_RENAMED:   3,
  INDEX_COPIED:    4,
  MODIFIED:        5,
  DELETED:         6,
  UNTRACKED:       7,
  IGNORED:         8,
  INTENT_TO_ADD:   9,
  ADDED_BY_US:     10,
  ADDED_BY_THEM:   11,
  DELETED_BY_US:   12,
  DELETED_BY_THEM: 13,
  BOTH_ADDED:      14,
  BOTH_DELETED:    15,
  BOTH_MODIFIED:   16,
};

// ── Tree Item Types ───────────────────────────────────────────────────────────

export class FileItem extends vscode.TreeItem {
  constructor(
    public readonly change: GitChange,
    repoRoot: string,
  ) {
    const fsPath = change.uri.fsPath;
    const relPath = path.relative(repoRoot, fsPath);
    const normalizedRelPath = relPath.replace(/\\/g, '/');
    const parts = normalizedRelPath.split('/');
    const filename = parts[parts.length - 1];
    const dir = parts.slice(0, -1).join('/');

    super(filename, vscode.TreeItemCollapsibleState.None);

    this.description = dir;
    this.resourceUri = change.uri;
    this.contextValue = 'fileToSync';

    // Status letter + color
    const { letter, icon, color } = _statusInfo(change.status);
    this.description = `${dir}  ${letter}`;
    this.iconPath = new vscode.ThemeIcon(icon, new vscode.ThemeColor(color));

    this.tooltip = new vscode.MarkdownString(
      `**${normalizedRelPath}**\n\n${_statusLabel(change.status)}\n\n` +
      '_Click to view diff — click sync to send to Telegram_'
    );

    // Clicking the file shows diff
    this.command = {
      command: 'gitphone.showFileDiff',
      title: 'Show Diff',
      arguments: [change, 'changes', repoRoot],
    };
  }
}

export class MessageItem extends vscode.TreeItem {
  constructor(label: string, icon: string, description = '') {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.iconPath = new vscode.ThemeIcon(icon);
    this.description = description;
    this.contextValue = 'message';
  }
}

// ── Main Provider ─────────────────────────────────────────────────────────────

export class GitPhoneSidebarProvider
  implements vscode.TreeDataProvider<vscode.TreeItem> {

  private _onDidChangeTreeData = new vscode.EventEmitter<vscode.TreeItem | undefined | null>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private _git: GitAPI | undefined;
  private _repo: GitRepository | undefined;
  private _disposables: vscode.Disposable[] = [];
  private _repoListener: vscode.Disposable | undefined;

  constructor() {
    this._initGit();
  }

  private _initGit(): void {
    const gitExtension = vscode.extensions.getExtension('vscode.git');
    if (!gitExtension) {
      console.warn('[GitPhone] vscode.git not found');
      return;
    }

    if (!gitExtension.isActive) {
      gitExtension.activate().then(() => this._initGit());
      return;
    }

    this._git = (gitExtension.exports as any).getAPI(1) as GitAPI;

    // Hook to first available repository
    const hookRepo = (repo: GitRepository) => {
      if (this._repoListener) this._repoListener.dispose();
      this._repo = repo;
      this._repoListener = repo.state.onDidChange(() => {
        this._onDidChangeTreeData.fire(undefined);
        
        // Reconcile state with backend (handles manual commits/reverts)
        const config = getConfig();
        if (config && isConfigured()) {
          const dirtyPaths = this.allChanges.map(c => 
            _relPath(c.uri.fsPath, repo.rootUri.fsPath)
          );
          syncState(config.telegramId, dirtyPaths);
        }
      });
      this._onDidChangeTreeData.fire(undefined);
    };

    if (this._git.repositories.length > 0) {
      hookRepo(this._git.repositories[0]);
    }

    // Also listen for new repos opening
    const sub = this._git.onDidOpenRepository((repo) => {
      if (!this._repo) hookRepo(repo);
    });
    this._disposables.push(sub);
  }

  dispose() {
    this._repoListener?.dispose();
    for (const d of this._disposables) d.dispose();
    this._onDidChangeTreeData.dispose();
  }

  refresh(): void {
    this._onDidChangeTreeData.fire(undefined);
  }

  get repository(): GitRepository | undefined {
    return this._repo;
  }

  /**
   * Returns all changes (staged + working tree) merged and unique by path.
   */
  get allChanges(): GitChange[] {
    if (!this._repo) return [];
    
    const staged = this._repo.state.indexChanges || [];
    const working = this._repo.state.workingTreeChanges || [];
    
    // Unique by fsPath. If a file is in both, the staged one is usually what we want to see,
    // but for syncing we just need one entry.
    const map = new Map<string, GitChange>();
    for (const c of working) map.set(c.uri.fsPath, c);
    for (const c of staged) map.set(c.uri.fsPath, c);
    
    return Array.from(map.values());
  }

  get stagedChanges(): GitChange[] {
    return this._repo?.state.indexChanges ?? [];
  }

  get workingTreeChanges(): GitChange[] {
    return this._repo?.state.workingTreeChanges ?? [];
  }

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  async getChildren(element?: vscode.TreeItem): Promise<vscode.TreeItem[]> {
    if (!this._git) {
      return [new MessageItem('Git extension not found', 'warning')];
    }
    if (!this._repo) {
      return [new MessageItem('No Git repository in workspace', 'git-branch')];
    }

    if (element) return [];

    const repoRoot = this._repo.rootUri.fsPath;
    const changes = this.allChanges;

    if (changes.length === 0) {
      const items = [new MessageItem('No changes detected', 'check', 'Working tree clean')];
      if (isConfigured()) {
        items.push(new MessageItem('GitPhone connected', 'plug', 'Save files to sync via Telegram'));
      }
      return items;
    }

    return changes.map(c => new FileItem(c, repoRoot));
  }
}

// --- Commands ------------------------------------------------------------------

/**
 * Show a VS Code diff for a file.
 */
export async function showFileDiff(
  change: GitChange,
  section: string,
  repoRoot: string,
): Promise<void> {
  // Always try to open the actual file for single-phase sync
  await vscode.window.showTextDocument(change.uri, { preview: true });
}

/**
 * Sync all modified files to the GitPhone backend.
 */
export async function syncStagedToBackend(
  provider: GitPhoneSidebarProvider,
  context: vscode.ExtensionContext,
): Promise<void> {
  const config = getConfig();
  if (!config) {
    vscode.window.showWarningMessage('GitPhone not configured. Open Setup first.');
    return;
  }

  const changes = provider.allChanges;
  if (changes.length === 0) {
    vscode.window.showInformationMessage('No modified files to sync.');
    return;
  }

  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: 'GitPhone: Syncing all changes...',
      cancellable: false,
    },
    async (progress) => {
      let synced = 0;
      const baseSha = provider.repository?.state.HEAD?.commit || 'new_file';
      const activeRepo = config.defaultRepo;
      const activeBranch = provider.repository?.state.HEAD?.name || config.branch;

      for (const change of changes) {
        progress.report({ message: `${synced + 1}/${changes.length}: ${path.basename(change.uri.fsPath)}` });
        try {
          const content = await vscode.workspace.fs.readFile(change.uri);
          const changeType = _gitChangeType(change.status);

          const payload: SyncFilePayload = {
            telegram_id: config.telegramId,
            filepath: _relPath(change.uri.fsPath, provider.repository!.rootUri.fsPath),
            diff: null,
            full_content: Buffer.from(content).toString('base64'),
            base_sha: changeType === 'create' ? 'new_file' : baseSha,
            is_binary: false,
            file_size: content.length,
            active_repo: activeRepo,
            active_branch: activeBranch,
            change_type: changeType,
          };

          await syncFile(payload);
          synced++;
        } catch (err: any) {
          const msg = extractErrorMessage(err);
          console.error(`[GitPhone] sync error for ${change.uri.fsPath}:`, msg);
        }
      }

      vscode.window.showInformationMessage(
        `[OK] GitPhone: ${synced} file(s) synced. Use /files in Telegram to commit.`,
      );
    },
  );
}

// --- Helpers -------------------------------------------------------------------

function _statusInfo(status: number): { letter: string; icon: string; color: string } {
  switch (status) {
    case GitStatus.INDEX_ADDED:
    case GitStatus.UNTRACKED:     return { letter: 'A', icon: 'diff-added',    color: 'gitDecoration.addedResourceForeground' };
    case GitStatus.INDEX_DELETED:
    case GitStatus.DELETED:       return { letter: 'D', icon: 'diff-removed',  color: 'gitDecoration.deletedResourceForeground' };
    case GitStatus.INDEX_RENAMED: return { letter: 'R', icon: 'diff-renamed',  color: 'gitDecoration.renamedResourceForeground' };
    default:                      return { letter: 'M', icon: 'diff-modified', color: 'gitDecoration.modifiedResourceForeground' };
  }
}

function _statusLabel(status: number): string {
  switch (status) {
    case GitStatus.INDEX_ADDED:
    case GitStatus.UNTRACKED:     return 'Added / Untracked';
    case GitStatus.INDEX_DELETED:
    case GitStatus.DELETED:       return 'Deleted';
    case GitStatus.INDEX_RENAMED: return 'Renamed';
    default:                      return 'Modified';
  }
}

function _gitChangeType(status: number): 'create' | 'delete' | 'modify' {
  if (status === GitStatus.INDEX_ADDED || status === GitStatus.UNTRACKED) return 'create';
  if (status === GitStatus.INDEX_DELETED || status === GitStatus.DELETED)  return 'delete';
  return 'modify';
}

function _relPath(absolute: string, root: string): string {
  return path.relative(root, absolute).replace(/\\/g, '/');
}
