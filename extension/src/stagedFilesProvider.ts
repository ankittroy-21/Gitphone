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
import { syncFile, SyncFilePayload, extractErrorMessage } from './api';

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

export type SectionType = 'staged' | 'changes';

export class SectionHeaderItem extends vscode.TreeItem {
  constructor(
    public readonly section: SectionType,
    public readonly count: number,
  ) {
    super(
      section === 'staged'
        ? `Staged Changes (${count})`
        : `Changes (${count})`,
      vscode.TreeItemCollapsibleState.Expanded,
    );
    this.contextValue = 'section';
    this.iconPath = new vscode.ThemeIcon(section === 'staged' ? 'check' : 'diff');
  }
}

export class FileItem extends vscode.TreeItem {
  constructor(
    public readonly change: GitChange,
    public readonly section: SectionType,
    repoRoot: string,
  ) {
    const relPath = path.relative(repoRoot, change.uri.fsPath);
    const parts = relPath.replace(/\\/g, '/').split('/');
    const filename = parts[parts.length - 1];
    const dir = parts.slice(0, -1).join('/');

    super(filename, vscode.TreeItemCollapsibleState.None);

    this.description = dir;
    this.resourceUri = change.uri;
    this.contextValue = section === 'staged' ? 'stagedFile' : 'changedFile';

    // Status letter + color
    const { letter, icon, color } = _statusInfo(change.status, section);
    this.description = `${dir}  ${letter}`;
    this.iconPath = new vscode.ThemeIcon(icon, new vscode.ThemeColor(color));

    this.tooltip = new vscode.MarkdownString(
      `**${relPath}**\n\n${_statusLabel(change.status, section)}\n\n` +
      (section === 'staged'
        ? '_Click to view diff — right-click to unstage_'
        : '_Click to view diff — click **+** to stage_')
    );

    // Clicking the file shows diff
    this.command = {
      command: 'gitphone.showFileDiff',
      title: 'Show Diff',
      arguments: [change, section, repoRoot],
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

    const repoRoot = this._repo.rootUri.fsPath;
    const staged  = this._repo.state.indexChanges;
    const changed = this._repo.state.workingTreeChanges;

    // Top-level: section headers
    if (!element) {
      const items: vscode.TreeItem[] = [];

      if (staged.length > 0) {
        items.push(new SectionHeaderItem('staged', staged.length));
      }
      if (changed.length > 0) {
        items.push(new SectionHeaderItem('changes', changed.length));
      }
      if (staged.length === 0 && changed.length === 0) {
        items.push(new MessageItem(
          'No changes detected',
          'check',
          'Working tree clean'
        ));
        if (isConfigured()) {
          items.push(new MessageItem(
            'GitPhone connected',
            'plug',
            'Save files to stage via Telegram'
          ));
        }
      }

      return items;
    }

    // Children of section headers
    if (element instanceof SectionHeaderItem) {
      if (element.section === 'staged') {
        return staged.map(c => new FileItem(c, 'staged', repoRoot));
      } else {
        return changed.map(c => new FileItem(c, 'changes', repoRoot));
      }
    }

    return [];
  }
}

// --- Commands ------------------------------------------------------------------

/**
 * Show a VS Code diff for a file.
 * For staged files: diff against HEAD (what was last committed).
 * For working tree files: diff current vs. saved.
 */
export async function showFileDiff(
  change: GitChange,
  section: SectionType,
  repoRoot: string,
): Promise<void> {
  if (section === 'staged') {
    // Diff: HEAD version vs index (staged) version
    const title = `${path.basename(change.uri.fsPath)} (staged)`;
    try {
      await vscode.commands.executeCommand(
        'vscode.diff',
        change.originalUri.with({ scheme: 'git', query: 'HEAD' }),
        change.uri.with({ scheme: 'git', query: '~' }),  // index
        `${title}`,
        { preview: true },
      );
      return;
    } catch {
      // Fallback to simple open
    }
  }
  // Working tree: open the actual file
  await vscode.window.showTextDocument(change.uri, { preview: true });
}

/**
 * Sync currently staged git files to the GitPhone backend (so they appear in Telegram /files).
 * This replaces the old file-save-watcher approach.
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

  const staged = provider.stagedChanges;
  if (staged.length === 0) {
    vscode.window.showInformationMessage('No staged files to sync. Stage files with git first.');
    return;
  }

  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: 'GitPhone: Syncing staged files...',
      cancellable: false,
    },
    async (progress) => {
      let synced = 0;
      const baseSha = provider.repository?.state.HEAD?.commit || 'new_file';
      const activeRepo = config.defaultRepo;
      const activeBranch = provider.repository?.state.HEAD?.name || config.branch;

      for (const change of staged) {
        progress.report({ message: `${synced + 1}/${staged.length}: ${path.basename(change.uri.fsPath)}` });
        try {
          const content = await vscode.workspace.fs.readFile(change.uri);
          const changeType = _gitChangeType(change.status);

          const payload: SyncFilePayload = {
            telegram_id: config.telegramId,
            filepath: _relPath(change.uri.fsPath, provider.repository!.rootUri.fsPath),
            diff: null, // Sending full content for staged files
            full_content: Buffer.from(content).toString('base64'),
            base_sha: changeType === 'create' ? 'new_file' : baseSha,
            is_binary: false, // TODO: detect binary
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

function _statusInfo(status: number, section: SectionType): { letter: string; icon: string; color: string } {
  if (section === 'staged') {
    switch (status) {
      case GitStatus.INDEX_ADDED:    return { letter: 'A', icon: 'diff-added',    color: 'gitDecoration.addedResourceForeground' };
      case GitStatus.INDEX_DELETED:  return { letter: 'D', icon: 'diff-removed',  color: 'gitDecoration.deletedResourceForeground' };
      case GitStatus.INDEX_RENAMED:  return { letter: 'R', icon: 'diff-renamed',  color: 'gitDecoration.renamedResourceForeground' };
      default:                       return { letter: 'M', icon: 'diff-modified', color: 'gitDecoration.modifiedResourceForeground' };
    }
  } else {
    switch (status) {
      case GitStatus.UNTRACKED:      return { letter: 'U', icon: 'question',      color: 'gitDecoration.untrackedResourceForeground' };
      case GitStatus.DELETED:        return { letter: 'D', icon: 'diff-removed',  color: 'gitDecoration.deletedResourceForeground' };
      default:                       return { letter: 'M', icon: 'diff-modified', color: 'gitDecoration.modifiedResourceForeground' };
    }
  }
}

function _statusLabel(status: number, section: SectionType): string {
  if (section === 'staged') {
    switch (status) {
      case GitStatus.INDEX_ADDED:   return 'Added (staged)';
      case GitStatus.INDEX_DELETED: return 'Deleted (staged)';
      case GitStatus.INDEX_RENAMED: return 'Renamed (staged)';
      default:                      return 'Modified (staged)';
    }
  } else {
    switch (status) {
      case GitStatus.UNTRACKED:     return 'Untracked';
      case GitStatus.DELETED:       return 'Deleted';
      default:                      return 'Modified';
    }
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
