"""
github_service.py — All GitHub API interactions via PyGithub.
Handles token validation, SHA fetching, and file commits.
"""

import base64
from typing import Optional
from github import Github, GithubException

from diff_service import apply_diff, detect_conflict


class GitHubService:

    def validate_token_and_repo(self, token: str, repo_name: str) -> dict:
        """
        Validates a PAT and checks access to the specified repo.
        Returns dict: { ok, error?, default_branch? }
        """
        try:
            g = Github(token)
            repo = g.get_repo(repo_name)
            return {
                "ok": True,
                "default_branch": repo.default_branch,
            }
        except GithubException as e:
            if e.status == 401:
                return {"ok": False, "error": "invalid_token", "message": "GitHub token is invalid or expired"}
            if e.status == 404:
                return {"ok": False, "error": "repo_not_found", "message": f"Repo '{repo_name}' not found or token has no access"}
            return {"ok": False, "error": "github_error", "message": str(e.data)}
        except Exception as e:
            return {"ok": False, "error": "unknown", "message": str(e)}

    def get_file_sha_and_content(
        self, token: str, repo_name: str, branch: str, filepath: str
    ) -> dict:
        """
        Fetches current SHA and decoded text content of a file from GitHub.
        Returns: { exists, sha, content }
        Returns exists=False for new files (404).
        """
        try:
            g = Github(token)
            repo = g.get_repo(repo_name)
            file_obj = repo.get_contents(filepath, ref=branch)
            # Handle list (directory) case — shouldn't happen but guard anyway
            if isinstance(file_obj, list):
                return {"exists": False, "sha": None, "content": ""}
            content = base64.b64decode(file_obj.content).decode("utf-8", errors="replace")
            return {
                "exists": True,
                "sha": file_obj.sha,
                "content": content,
            }
        except GithubException as e:
            if e.status == 404:
                return {"exists": False, "sha": None, "content": ""}
            raise

    def commit_files(
        self,
        token: str,
        repo_name: str,
        branch: str,
        staged_files: list[dict],
        commit_message: str,
    ) -> dict:
        """
        Commits one or more staged files to GitHub.
        staged_files: list of staged_files rows from Supabase.

        For each file:
          1. Fetch current GitHub content + SHA
          2. Detect conflict (base_sha mismatch)
          3. Apply diff to reconstruct new content
          4. Commit via Contents API

        Returns: { ok, commit_sha?, error?, conflict_files? }
        """
        try:
            g = Github(token)
            repo = g.get_repo(repo_name)
            last_sha: Optional[str] = None
            conflict_files: list[str] = []

            for staged in staged_files:
                filepath = staged["filepath"]
                stored_base_sha = staged["base_sha"]
                is_binary = staged.get("is_binary", False)
                full_content_b64 = staged.get("full_content")
                diff_text = staged.get("diff")

                # ── Fetch current GitHub state ────────────────────────────
                gh_file = self.get_file_sha_and_content(token, repo_name, branch, filepath)
                current_sha = gh_file["sha"]
                current_content = gh_file["content"]
                is_new_file = not gh_file["exists"] or stored_base_sha == "new_file"

                # ── Conflict check (skip for new files) ───────────────────
                if not is_new_file and detect_conflict(stored_base_sha, current_sha):
                    conflict_files.append(filepath)
                    continue

                # ── Reconstruct final content ─────────────────────────────
                if is_binary or full_content_b64:
                    # Binary or full-content file — decode base64 directly
                    final_bytes = base64.b64decode(full_content_b64)
                    content_to_commit = final_bytes
                else:
                    # Text file — apply diff to current GitHub content
                    base_content = current_content if not is_new_file else ""
                    new_content, success = apply_diff(base_content, diff_text)
                    if not success:
                        print(f"[github_service] Diff apply failed for {filepath}, using raw content")
                    # Normalize before committing
                    new_content = new_content.replace("\r\n", "\n")
                    content_to_commit = new_content.encode("utf-8")

                # ── Commit to GitHub ──────────────────────────────────────
                if is_new_file:
                    result = repo.create_file(
                        path=filepath,
                        message=commit_message,
                        content=content_to_commit,
                        branch=branch,
                    )
                else:
                    result = repo.update_file(
                        path=filepath,
                        message=commit_message,
                        content=content_to_commit,
                        sha=current_sha,
                        branch=branch,
                    )
                last_sha = result["commit"].sha

            # ── Return result ─────────────────────────────────────────────
            if conflict_files and not last_sha:
                return {
                    "ok": False,
                    "error": "conflict",
                    "conflict_files": conflict_files,
                    "message": "All selected files had conflicts",
                }

            return {
                "ok": True,
                "commit_sha": last_sha,
                "conflict_files": conflict_files,  # partial conflicts possible
            }

        except GithubException as e:
            if e.status == 409:
                return {"ok": False, "error": "conflict", "message": "SHA conflict on GitHub"}
            if e.status == 422:
                return {"ok": False, "error": "branch_protected", "message": "Branch has protection rules"}
            return {"ok": False, "error": "github_error", "message": str(e.data)}
        except Exception as e:
            print(f"[github_service] commit_files error: {e}")
            return {"ok": False, "error": "unknown", "message": str(e)}

    def force_commit_files(
        self,
        token: str,
        repo_name: str,
        branch: str,
        staged_files: list[dict],
        commit_message: str,
    ) -> dict:
        """
        Force commit — overwrites GitHub content with staged version.
        Used when user chooses 'Force Commit' on conflict screen.
        Fetches the CURRENT GitHub SHA (to satisfy the API) but ignores base_sha.
        """
        # Re-fetch current SHA and commit regardless of mismatch
        for staged in staged_files:
            staged["base_sha"] = "force"  # bypass detect_conflict
        return self.commit_files(token, repo_name, branch, staged_files, commit_message)


github_service = GitHubService()
