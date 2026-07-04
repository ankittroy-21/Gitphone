/**
 * setupPanel.ts â€” GitPhone first-time setup.
 * Uses VS Code's built-in GitHub OAuth â€” no manual PAT needed.
 * Falls back to manual PAT entry via Advanced section.
 */

import * as vscode from 'vscode';
import { register, extractErrorMessage } from './api';
import { saveConfig, getConfig } from './config';
import { setConnected, setDisconnected } from './statusBar';

export class SetupPanel {
  public static currentPanel: SetupPanel | undefined;

  private readonly _panel: vscode.WebviewPanel;
  private _disposables: vscode.Disposable[] = [];

  public static createOrShow(extensionUri: vscode.Uri): void {
    const column = vscode.window.activeTextEditor
      ? vscode.window.activeTextEditor.viewColumn
      : undefined;

    if (SetupPanel.currentPanel) {
      SetupPanel.currentPanel._panel.reveal(column);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      'gitphoneSetup',
      'GitPhone Setup',
      column ?? vscode.ViewColumn.One,
      {
        enableScripts: true,
        localResourceRoots: [vscode.Uri.joinPath(extensionUri, 'media')],
      },
    );

    SetupPanel.currentPanel = new SetupPanel(panel);
  }

  private constructor(panel: vscode.WebviewPanel) {
    this._panel = panel;
    this._panel.webview.html = this._getHtmlContent();

    this._panel.webview.onDidReceiveMessage(
      async (message) => {
        if (message.type === 'ready') {
          // Prefill saved config
          const existing = getConfig();
          if (existing) {
            this._panel.webview.postMessage({
              type: 'prefill',
              data: {
                telegramId: existing.telegramId,
                githubToken: existing.githubToken,
                defaultRepo: existing.defaultRepo,
                branch: existing.branch,
                backendUrl: existing.backendUrl,
                isOAuth: !existing.githubToken.startsWith('ghp_') && !existing.githubToken.startsWith('github_pat_'),
              },
            });
          }
        } else if (message.type === 'github_oauth') {
          // Use VS Code's built-in GitHub OAuth
          await this._handleGitHubOAuth();
        } else if (message.type === 'connect') {
          await this._handleConnect(message.data);
        } else if (message.type === 'openLink') {
          vscode.env.openExternal(vscode.Uri.parse(message.url));
        }
      },
      null,
      this._disposables,
    );

    this._panel.onDidDispose(() => this.dispose(), null, this._disposables);
  }

  /** Use VS Code's built-in GitHub OAuth to get a token */
  private async _handleGitHubOAuth(): Promise<void> {
    try {
      this._panel.webview.postMessage({ type: 'oauth_loading' });

      // VS Code built-in GitHub auth - user clicks "Sign in with GitHub" in browser
      const session = await vscode.authentication.getSession(
        'github',
        ['repo', 'read:user'],   // repo = read/write access to repos
        { createIfNone: true },
      );

      if (!session) {
        this._panel.webview.postMessage({
          type: 'oauth_error',
          message: 'GitHub sign-in was cancelled.',
        });
        return;
      }

      const token = session.accessToken;
      const username = session.account.label;

      this._panel.webview.postMessage({
        type: 'oauth_success',
        token,
        username,
      });

    } catch (err: any) {
      this._panel.webview.postMessage({
        type: 'oauth_error',
        message: err?.message ?? 'GitHub sign-in failed.',
      });
    }
  }

  private async _handleConnect(data: {
    telegramId: string;
    githubToken: string;
    defaultRepo: string;
    branch: string;
    backendUrl: string;
  }): Promise<void> {
    const repoStr = data.defaultRepo.trim();
    let parsedRepo = repoStr;
    
    if (repoStr.startsWith('http') || repoStr.includes('github.com')) {
      const match = repoStr.match(/github\.com\/([^\/\s]+\/[^\/\s]+?)(?:\.git)?$/i);
      if (match) {
        parsedRepo = match[1];
      } else {
        vscode.window.showErrorMessage('Invalid GitHub repository URL. Please provide a correct URL (e.g., https://github.com/owner/repo).');
        this._panel.webview.postMessage({ type: 'error', message: 'Invalid repository URL.' });
        return;
      }
    } else {
      if (!/^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/.test(repoStr)) {
        vscode.window.showErrorMessage('Invalid GitHub repository format. Please use "username/repo" or a valid GitHub URL.');
        this._panel.webview.postMessage({ type: 'error', message: 'Invalid repository format.' });
        return;
      }
    }
    
    data.defaultRepo = parsedRepo;

    this._panel.webview.postMessage({ type: 'loading', message: 'Connecting to GitPhone...' });

    try {
      const response = await register({
        telegram_id: data.telegramId,
        github_token: data.githubToken,
        default_repo: data.defaultRepo,
        branch: data.branch || 'main',
      });

      if (response.ok) {
        if (!response.api_key) {
          this._panel.webview.postMessage({
            type: 'error',
            message: 'Server did not return an API key. Please try again or update your backend.',
          });
          return;
        }

        // Save config to globalState - including the api_key
        saveConfig({
          telegramId: data.telegramId,
          githubToken: data.githubToken,
          defaultRepo: data.defaultRepo,
          branch: data.branch || 'main',
          backendUrl: data.backendUrl || 'https://gitphone.onrender.com',
          schemaVersion: 1,
          apiKey: response.api_key,   // Store the secret key
        });

        setConnected(0);
        this._panel.webview.postMessage({ type: 'success' });

        // Delay close to let user see the success message
        setTimeout(() => {
          this._panel.dispose();
          vscode.window.showInformationMessage(
            'GitPhone connected! Save any file in your workspace to stage it.',
          );
        }, 1500);
      } else {
        this._panel.webview.postMessage({
          type: 'error',
          message: response.error === 'invalid_token'
            ? 'GitHub token is invalid or expired. Check your fine-grained PAT.'
            : response.error === 'repo_not_found'
            ? 'Repository not found. Check the repo name and token permissions.'
            : response.message || 'Registration failed. Please try again.',
        });
      }
    } catch (err) {
      const message = extractErrorMessage(err);
      this._panel.webview.postMessage({
        type: 'error',
        message: `Connection failed: ${message}`,
      });
      setDisconnected();
    }
  }

  private _getHtmlContent(): string {
    return /* html */`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GitPhone Setup</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
      color: var(--vscode-foreground);
      background: var(--vscode-editor-background);
      padding: 32px;
      max-width: 540px;
      margin: 0 auto;
    }

    .header {
      display: flex;
      align-items: center;
      gap: 14px;
      margin-bottom: 28px;
    }
    .logo { font-size: 36px; }
    h1 { font-size: 22px; font-weight: 600; }
    .subtitle { font-size: 13px; color: var(--vscode-descriptionForeground); margin-top: 3px; }

    .divider {
      height: 1px;
      background: var(--vscode-widget-border);
      margin: 22px 0;
    }

    /* --- GitHub OAuth button --- */
    .btn-github {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      width: 100%;
      padding: 12px 20px;
      background: #238636;
      color: #fff;
      border: none;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s, transform 0.1s;
      margin-bottom: 8px;
    }
    .btn-github:hover { background: #2ea043; transform: translateY(-1px); }
    .btn-github:active { transform: translateY(0); }
    .btn-github:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
    .btn-github svg { flex-shrink: 0; }

    /* --- Connected GitHub badge --- */
    .github-connected {
      display: none;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      background: rgba(35,134,54,0.15);
      border: 1px solid rgba(35,134,54,0.4);
      border-radius: 8px;
      margin-bottom: 8px;
    }
    .github-connected.show { display: flex; }
    .github-avatar {
      width: 28px; height: 28px;
      border-radius: 50%;
      background: #238636;
      display: flex; align-items: center; justify-content: center;
      font-size: 14px; color: #fff; font-weight: 700;
      flex-shrink: 0;
    }
    .github-name { font-weight: 600; font-size: 13px; }
    .github-status { font-size: 11px; color: var(--vscode-descriptionForeground); }
    .change-account {
      margin-left: auto;
      font-size: 11px;
      color: var(--vscode-textLink-foreground);
      cursor: pointer;
      white-space: nowrap;
    }
    .change-account:hover { text-decoration: underline; }

    /* --- Fields --- */
    .field { margin-bottom: 16px; }

    label {
      display: block;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--vscode-descriptionForeground);
      margin-bottom: 6px;
    }

    input {
      width: 100%;
      padding: 8px 12px;
      background: var(--vscode-input-background);
      color: var(--vscode-input-foreground);
      border: 1px solid var(--vscode-input-border, var(--vscode-widget-border));
      border-radius: 8px;
      font-size: 13px;
      font-family: var(--vscode-editor-font-family);
      outline: none;
      transition: border-color 0.15s;
    }
    input:focus { border-color: var(--vscode-focusBorder); }
    input::placeholder { color: var(--vscode-input-placeholderForeground); }

    .hint { font-size: 11px; color: var(--vscode-descriptionForeground); margin-top: 4px; }
    .hint a { color: var(--vscode-textLink-foreground); text-decoration: none; }
    .hint a:hover { text-decoration: underline; }

    .field-row { display: flex; gap: 12px; }
    .field-row .field { flex: 1; }

    /* --- Connect button --- */
    .btn-primary {
      display: block;
      width: 100%;
      padding: 10px 20px;
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
      border: none;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      margin-top: 20px;
      transition: background 0.15s, opacity 0.15s;
    }
    .btn-primary:hover { background: var(--vscode-button-hoverBackground); }
    .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

    /* --- Status box --- */
    .status-box {
      display: none;
      padding: 10px 14px;
      border-radius: 8px;
      font-size: 13px;
      margin-top: 14px;
      align-items: center;
      gap: 10px;
    }
    .status-box.loading {
      display: flex;
      background: var(--vscode-inputValidation-infoBackground);
      border: 1px solid var(--vscode-inputValidation-infoBorder);
    }
    .status-box.error {
      display: flex;
      background: var(--vscode-inputValidation-errorBackground);
      border: 1px solid var(--vscode-inputValidation-errorBorder);
    }
    .status-box.success {
      display: flex;
      background: rgba(35,134,54,0.15);
      border: 1px solid rgba(35,134,54,0.4);
    }

    .spinner {
      width: 14px; height: 14px;
      border: 2px solid currentColor;
      border-top-color: transparent;
      border-radius: 50%;
      animation: spin 0.6s linear infinite;
      flex-shrink: 0;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* --- Advanced (manual PAT) --- */
    .advanced-toggle {
      font-size: 11px;
      color: var(--vscode-textLink-foreground);
      cursor: pointer;
      margin-top: 6px;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .advanced-toggle:hover { text-decoration: underline; }
    .advanced-section { display: none; margin-top: 14px; }
    .advanced-section.open { display: block; }

    .or-divider {
      display: flex;
      align-items: center;
      gap: 10px;
      margin: 16px 0 10px;
      color: var(--vscode-descriptionForeground);
      font-size: 11px;
    }
    .or-divider::before, .or-divider::after {
      content: '';
      flex: 1;
      height: 1px;
      background: var(--vscode-widget-border);
    }
  </style>
</head>
<body>
  <div class="header">
    <span class="logo">[Phone]</span>
    <div>
      <h1>GitPhone Setup</h1>
      <div class="subtitle">Commit to GitHub from anywhere via Telegram</div>
    </div>
  </div>

  <div class="divider"></div>

  <form id="setupForm">

    <!-- --- Step 1: GitHub Auth --- -->
    <div class="field">
      <label>GitHub Account <span style="color:var(--vscode-errorForeground)">*</span></label>

      <!-- OAuth button (shown when not signed in) -->
      <button type="button" class="btn-github" id="githubOAuthBtn" onclick="signInWithGitHub()">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="white">
          <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
        </svg>
        Sign in with GitHub
      </button>

      <!-- Connected state (shown after OAuth) -->
      <div class="github-connected" id="githubConnected">
        <div class="github-avatar" id="githubAvatar">G</div>
        <div>
          <div class="github-name" id="githubUsername">-</div>
          <div class="github-status">[OK] Connected via GitHub</div>
        </div>
        <span class="change-account" onclick="resetGitHubAuth()">Change account</span>
      </div>

      <!-- Hidden: stores the actual token -->
      <input type="hidden" id="githubToken" />
    </div>

    <!-- --- Step 2: Telegram ID --- -->
    <div class="field">
      <label>Telegram User ID <span style="color:var(--vscode-errorForeground)">*</span></label>
      <input
        type="text"
        id="telegramId"
        placeholder="123456789"
        autocomplete="off"
        inputmode="numeric"
        required
      />
      <div class="hint">Message <strong>@userinfobot</strong> on Telegram to get your numeric ID</div>
    </div>

    <!-- --- Step 3: Repo + Branch --- -->
    <div class="field-row">
      <div class="field">
        <label>Default Repository <span style="color:var(--vscode-errorForeground)">*</span></label>
        <input
          type="text"
          id="defaultRepo"
          placeholder="username/repo-name"
          autocomplete="off"
          spellcheck="false"
          required
        />
      </div>
      <div class="field">
        <label>Branch</label>
        <input
          type="text"
          id="branch"
          placeholder="main"
          value="main"
          autocomplete="off"
          spellcheck="false"
        />
      </div>
    </div>

    <!-- --- Advanced (manual PAT fallback) --- -->
    <div class="or-divider">or use a Personal Access Token</div>
    <span class="advanced-toggle" onclick="toggleAdvanced()">
      [Settings] Advanced options
    </span>
    <div class="advanced-section" id="advancedSection">
      <div class="field" style="margin-top:12px">
        <label>GitHub PAT (manual)</label>
        <input
          type="password"
          id="githubTokenManual"
          placeholder="ghp_xxxxxxxxxxxx or github_pat_..."
          autocomplete="off"
          spellcheck="false"
        />
        <div class="hint">
          <a href="#" onclick="openLink('https://github.com/settings/tokens?type=beta')">
            Settings -> Developer Settings -> Fine-grained tokens
          </a>
          - needs <strong>Contents: read &amp; write</strong>
        </div>
      </div>
      <div class="field">
        <label>Backend URL</label>
        <input
          type="text"
          id="backendUrl"
          placeholder="https://gitphone.onrender.com"
          value="https://gitphone.onrender.com"
          autocomplete="off"
          spellcheck="false"
        />
        <div class="hint">Only change this if you're self-hosting</div>
      </div>
    </div>

    <div class="status-box" id="statusBox">
      <div class="spinner" id="statusSpinner"></div>
      <span id="statusText"></span>
    </div>

    <button type="submit" class="btn-primary" id="connectBtn">
      [Launch] Connect GitPhone
    </button>
  </form>

  <script>
    const vscode = acquireVsCodeApi();

    // Signal extension that webview is ready
    vscode.postMessage({ type: 'ready' });

    function openLink(url) {
      vscode.postMessage({ type: 'openLink', url });
    }

    function toggleAdvanced() {
      document.getElementById('advancedSection').classList.toggle('open');
    }

    function showStatus(type, message) {
      const box = document.getElementById('statusBox');
      box.className = 'status-box ' + type;
      document.getElementById('statusText').textContent = message;
      document.getElementById('statusSpinner').style.display = type === 'loading' ? 'block' : 'none';
    }

    function hideStatus() {
      document.getElementById('statusBox').className = 'status-box';
    }

    // --- GitHub OAuth ---------------------------------------------------------
    function signInWithGitHub() {
      document.getElementById('githubOAuthBtn').disabled = true;
      document.getElementById('githubOAuthBtn').textContent = 'Opening GitHub...';
      vscode.postMessage({ type: 'github_oauth' });
    }

    function resetGitHubAuth() {
      document.getElementById('githubToken').value = '';
      document.getElementById('githubConnected').classList.remove('show');
      document.getElementById('githubOAuthBtn').style.display = 'flex';
      document.getElementById('githubOAuthBtn').disabled = false;
      document.getElementById('githubOAuthBtn').innerHTML = \`
        <svg width="18" height="18" viewBox="0 0 24 24" fill="white">
          <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
        </svg>
        Sign in with GitHub\`;
    }

    // --- Form submit ----------------------------------------------------------
    document.getElementById('setupForm').addEventListener('submit', (e) => {
      e.preventDefault();

      // Prefer OAuth token, fall back to manual PAT
      const oauthToken = document.getElementById('githubToken').value.trim();
      const manualToken = document.getElementById('githubTokenManual').value.trim();
      const githubToken = oauthToken || manualToken;

      const telegramId = document.getElementById('telegramId').value.trim();
      const defaultRepo = document.getElementById('defaultRepo').value.trim();
      const branch = document.getElementById('branch').value.trim() || 'main';
      const backendUrl = document.getElementById('backendUrl').value.trim() || 'https://gitphone.onrender.com';

      if (!githubToken) {
        showStatus('error', 'Sign in with GitHub or enter a PAT first.');
        return;
      }
      if (manualToken && !manualToken.startsWith('ghp_') && !manualToken.startsWith('github_pat_')) {
        showStatus('error', 'Manual token must start with ghp_ or github_pat_');
        return;
      }
      if (!/^\\d{6,12}$/.test(telegramId)) {
        showStatus('error', 'Telegram ID must be a 6-12 digit number');
        return;
      }

      document.getElementById('connectBtn').disabled = true;
      showStatus('loading', 'Connecting to GitPhone...');

      vscode.postMessage({
        type: 'connect',
        data: { telegramId, githubToken, defaultRepo, branch, backendUrl },
      });
    });

    // --- Messages from extension -----------------------------------------------
    window.addEventListener('message', (event) => {
      const msg = event.data;

      if (msg.type === 'oauth_loading') {
        // Already handled by button state

      } else if (msg.type === 'oauth_success') {
        // GitHub signed in - show connected state
        document.getElementById('githubToken').value = msg.token;
        document.getElementById('githubUsername').textContent = msg.username;
        document.getElementById('githubAvatar').textContent = msg.username[0].toUpperCase();
        document.getElementById('githubConnected').classList.add('show');
        document.getElementById('githubOAuthBtn').style.display = 'none';

        // Auto-fill repo if empty
        const repoInput = document.getElementById('defaultRepo');
        if (!repoInput.value) {
          repoInput.value = msg.username + '/';
          repoInput.focus();
          repoInput.setSelectionRange(repoInput.value.length, repoInput.value.length);
        }

      } else if (msg.type === 'oauth_error') {
        document.getElementById('githubOAuthBtn').disabled = false;
        document.getElementById('githubOAuthBtn').textContent = 'Sign in with GitHub';
        showStatus('error', msg.message);

      } else if (msg.type === 'loading') {
        showStatus('loading', msg.message);

      } else if (msg.type === 'error') {
        showStatus('error', msg.message);
        document.getElementById('connectBtn').disabled = false;

      } else if (msg.type === 'success') {
        showStatus('success', '[OK] Connected! GitPhone is now active.');

      } else if (msg.type === 'prefill') {
        const d = msg.data;
        if (d.telegramId) document.getElementById('telegramId').value = d.telegramId;
        if (d.defaultRepo) document.getElementById('defaultRepo').value = d.defaultRepo;
        if (d.branch) document.getElementById('branch').value = d.branch;
        if (d.backendUrl) document.getElementById('backendUrl').value = d.backendUrl;

        if (d.githubToken) {
          if (d.isOAuth) {
            // Was signed in via OAuth - show connected state with placeholder name
            document.getElementById('githubToken').value = d.githubToken;
            document.getElementById('githubUsername').textContent = 'GitHub Account';
            document.getElementById('githubAvatar').textContent = 'OK';
            document.getElementById('githubConnected').classList.add('show');
            document.getElementById('githubOAuthBtn').style.display = 'none';
          } else {
            // Was set via manual PAT
            document.getElementById('githubTokenManual').value = d.githubToken;
            document.getElementById('githubTokenManual').placeholder = '******** (saved)';
            document.getElementById('advancedSection').classList.add('open');
          }
        }
      }
    });
  </script>
</body>
</html>`;
  }

  public dispose(): void {
    SetupPanel.currentPanel = undefined;
    this._panel.dispose();
    while (this._disposables.length) {
      const d = this._disposables.pop();
      if (d) d.dispose();
    }
  }
}
