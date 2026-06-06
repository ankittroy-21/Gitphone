/**
 * setupPanel.ts — VS Code Webview panel for first-time GitPhone configuration.
 * Opens as a tab in the editor. Collects 5 fields and POSTs to /register.
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

    // Pre-fill with existing config if available
    const existing = getConfig();
    if (existing) {
      this._panel.webview.postMessage({
        type: 'prefill',
        data: {
          telegramId: existing.telegramId,
          defaultRepo: existing.defaultRepo,
          branch: existing.branch,
          backendUrl: existing.backendUrl,
        },
      });
    }

    // Listen for messages from the webview
    this._panel.webview.onDidReceiveMessage(
      async (message) => {
        if (message.type === 'connect') {
          await this._handleConnect(message.data);
        }
      },
      null,
      this._disposables,
    );

    this._panel.onDidDispose(() => this.dispose(), null, this._disposables);
  }

  private async _handleConnect(data: {
    telegramId: string;
    githubToken: string;
    defaultRepo: string;
    branch: string;
    backendUrl: string;
  }): Promise<void> {
    this._panel.webview.postMessage({ type: 'loading', message: 'Connecting to GitPhone...' });

    try {
      const response = await register({
        telegram_id: data.telegramId,
        github_token: data.githubToken,
        default_repo: data.defaultRepo,
        branch: data.branch || 'main',
      });

      if (response.ok) {
        // Save config to globalState
        saveConfig({
          telegramId: data.telegramId,
          githubToken: data.githubToken,
          defaultRepo: data.defaultRepo,
          branch: data.branch || 'main',
          backendUrl: data.backendUrl || 'https://gitphone.onrender.com',
          schemaVersion: 1,
        });

        setConnected(0);
        this._panel.webview.postMessage({ type: 'success' });

        // Delay close to let user see the success message
        setTimeout(() => {
          this._panel.dispose();
          vscode.window.showInformationMessage(
            '🚀 GitPhone connected! Save any file in your workspace to stage it.',
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
    :root {
      --radius: 8px;
      --gap: 16px;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
      color: var(--vscode-foreground);
      background: var(--vscode-editor-background);
      padding: 32px;
      max-width: 560px;
      margin: 0 auto;
    }

    .header {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 28px;
    }

    .logo {
      font-size: 32px;
    }

    h1 {
      font-size: 22px;
      font-weight: 600;
      color: var(--vscode-foreground);
    }

    .subtitle {
      font-size: 13px;
      color: var(--vscode-descriptionForeground);
      margin-top: 2px;
    }

    .divider {
      height: 1px;
      background: var(--vscode-widget-border);
      margin: 20px 0;
    }

    .field {
      margin-bottom: 18px;
    }

    label {
      display: block;
      font-size: 12px;
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
      border-radius: var(--radius);
      font-size: 13px;
      font-family: var(--vscode-editor-font-family);
      outline: none;
      transition: border-color 0.15s;
    }

    input:focus {
      border-color: var(--vscode-focusBorder);
    }

    input::placeholder {
      color: var(--vscode-input-placeholderForeground);
    }

    .hint {
      font-size: 11px;
      color: var(--vscode-descriptionForeground);
      margin-top: 4px;
    }

    .hint a {
      color: var(--vscode-textLink-foreground);
      text-decoration: none;
    }

    .hint a:hover { text-decoration: underline; }

    .btn-primary {
      display: block;
      width: 100%;
      padding: 10px 20px;
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
      border: none;
      border-radius: var(--radius);
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      margin-top: 24px;
      transition: background 0.15s, opacity 0.15s;
    }

    .btn-primary:hover {
      background: var(--vscode-button-hoverBackground);
    }

    .btn-primary:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .status-box {
      display: none;
      padding: 12px 16px;
      border-radius: var(--radius);
      font-size: 13px;
      margin-top: 16px;
      align-items: center;
      gap: 10px;
    }

    .status-box.loading {
      display: flex;
      background: var(--vscode-inputValidation-infoBackground);
      border: 1px solid var(--vscode-inputValidation-infoBorder);
      color: var(--vscode-inputValidation-infoForeground, var(--vscode-foreground));
    }

    .status-box.error {
      display: flex;
      background: var(--vscode-inputValidation-errorBackground);
      border: 1px solid var(--vscode-inputValidation-errorBorder);
      color: var(--vscode-inputValidation-errorForeground, var(--vscode-foreground));
    }

    .status-box.success {
      display: flex;
      background: var(--vscode-inputValidation-infoBackground);
      border: 1px solid var(--vscode-inputValidation-infoBorder);
    }

    .spinner {
      width: 14px;
      height: 14px;
      border: 2px solid currentColor;
      border-top-color: transparent;
      border-radius: 50%;
      animation: spin 0.6s linear infinite;
      flex-shrink: 0;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .advanced-toggle {
      font-size: 12px;
      color: var(--vscode-textLink-foreground);
      cursor: pointer;
      margin-top: 8px;
      display: inline-block;
    }

    .advanced-toggle:hover { text-decoration: underline; }

    .advanced-section {
      display: none;
      margin-top: 12px;
    }

    .advanced-section.open { display: block; }

    .field-row {
      display: flex;
      gap: 12px;
    }

    .field-row .field {
      flex: 1;
    }
  </style>
</head>
<body>
  <div class="header">
    <span class="logo">📱</span>
    <div>
      <h1>GitPhone Setup</h1>
      <div class="subtitle">Commit to GitHub from anywhere via Telegram</div>
    </div>
  </div>

  <div class="divider"></div>

  <form id="setupForm">
    <div class="field">
      <label>GitHub Fine-Grained PAT <span style="color:var(--vscode-errorForeground)">*</span></label>
      <input
        type="password"
        id="githubToken"
        placeholder="ghp_xxxxxxxxxxxx or github_pat_..."
        autocomplete="off"
        spellcheck="false"
        required
      />
      <div class="hint">
        <a href="#" onclick="openLink('https://github.com/settings/tokens?type=beta')">
          Settings → Developer Settings → Fine-grained tokens
        </a>
        — needs <strong>Contents: read &amp; write</strong>
      </div>
    </div>

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

    <span class="advanced-toggle" onclick="toggleAdvanced()">⚙️ Advanced options</span>
    <div class="advanced-section" id="advancedSection">
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
      🚀 Connect GitPhone
    </button>
  </form>

  <script>
    const vscode = acquireVsCodeApi();

    function openLink(url) {
      vscode.postMessage({ type: 'openLink', url });
    }

    function toggleAdvanced() {
      const section = document.getElementById('advancedSection');
      section.classList.toggle('open');
    }

    function showStatus(type, message) {
      const box = document.getElementById('statusBox');
      const text = document.getElementById('statusText');
      const spinner = document.getElementById('statusSpinner');

      box.className = 'status-box ' + type;
      text.textContent = message;
      spinner.style.display = type === 'loading' ? 'block' : 'none';
    }

    function hideStatus() {
      document.getElementById('statusBox').className = 'status-box';
    }

    document.getElementById('setupForm').addEventListener('submit', (e) => {
      e.preventDefault();

      const githubToken = document.getElementById('githubToken').value.trim();
      const telegramId = document.getElementById('telegramId').value.trim();
      const defaultRepo = document.getElementById('defaultRepo').value.trim();
      const branch = document.getElementById('branch').value.trim() || 'main';
      const backendUrl = document.getElementById('backendUrl').value.trim() || 'https://gitphone.onrender.com';

      // Basic client-side validation
      if (!githubToken.startsWith('ghp_') && !githubToken.startsWith('github_pat_')) {
        showStatus('error', 'Token must start with ghp_ or github_pat_');
        return;
      }
      if (!/^\\d{6,12}$/.test(telegramId)) {
        showStatus('error', 'Telegram ID must be a 6-12 digit number');
        return;
      }
      if (!defaultRepo.includes('/') || defaultRepo.split('/').length !== 2) {
        showStatus('error', 'Repo must be in format: username/repo-name');
        return;
      }

      document.getElementById('connectBtn').disabled = true;
      showStatus('loading', 'Connecting to GitPhone...');

      vscode.postMessage({
        type: 'connect',
        data: { telegramId, githubToken, defaultRepo, branch, backendUrl },
      });
    });

    // Handle messages from extension
    window.addEventListener('message', (event) => {
      const msg = event.data;
      if (msg.type === 'loading') {
        showStatus('loading', msg.message);
      } else if (msg.type === 'error') {
        showStatus('error', msg.message);
        document.getElementById('connectBtn').disabled = false;
      } else if (msg.type === 'success') {
        showStatus('success', '✅ Connected! GitPhone is now active.');
      } else if (msg.type === 'prefill') {
        const d = msg.data;
        if (d.telegramId) document.getElementById('telegramId').value = d.telegramId;
        if (d.defaultRepo) document.getElementById('defaultRepo').value = d.defaultRepo;
        if (d.branch) document.getElementById('branch').value = d.branch;
        if (d.backendUrl) document.getElementById('backendUrl').value = d.backendUrl;
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
