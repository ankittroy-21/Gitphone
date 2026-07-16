"""
github_service.py - All GitHub API interactions via PyGithub.
Handles token validation, SHA fetching, file commits, branch management, and PR creation.
"""

import base64

from diff_service import apply_diff
from github import Github, GithubException


class GitHubService:

    def validate_token_and_repo(self, token: str, repo_name: str) -> dict:
        """
        Validates a PAT/OAuth token and checks access to the specified repo.
        Returns dict: { ok, error?, default_branch?, username? }
        """
        try:
            g = Github(token)
            user = g.get_user()
            repo = g.get_repo(repo_name)
            return {
                "ok": True,
                "default_branch": repo.default_branch,
                "username": user.login,
            }
        except GithubException as e:
            if e.status == 401:
                return {"ok": False, "error": "invalid_token", "message": "GitHub token is invalid or expired"}
            if e.status == 404:
                return {"ok": False, "error": "repo_not_found", "message": f"Repo '{repo_name}' not found or token has no access"}
            return {"ok": False, "error": "github_error", "message": str(e.data)}
        except Exception as e:
            return {"ok": False, "error": "unknown", "message": str(e)}

    def get_username(self, token: str) -> str | None:
        """Return the GitHub username for a given token."""
        try:
            return Github(token).get_user().login
        except Exception:
            return None

    def list_branches(self, token: str, repo_name: str) -> list[str]:
        """Return all branch names for a repo (max 50)."""
        try:
            repo = Github(token).get_repo(repo_name)
            return [b.name for b in repo.get_branches()][:50]
        except Exception as e:
            print(f"[github_service] list_branches error: {e}")
            return []

    def get_default_branch(self, token: str, repo_name: str) -> str:
        """Return the default branch name."""
        try:
            return Github(token).get_repo(repo_name).default_branch
        except Exception:
            return "main"

    def create_branch(self, token: str, repo_name: str, branch_name: str, from_branch: str = "main") -> dict:
        """
        Create a new branch from from_branch.
        Returns { ok, error? }
        """
        try:
            repo = Github(token).get_repo(repo_name)
            source_branch = repo.get_branch(from_branch)
            repo.create_git_ref(
                ref=f"refs/heads/{branch_name}",
                sha=source_branch.commit.sha,
            )
            return {"ok": True}
        except GithubException as e:
            if e.status == 422:
                return {"ok": False, "error": "branch_exists", "message": f"Branch '{branch_name}' already exists"}
            return {"ok": False, "error": "github_error", "message": str(e.data)}
        except Exception as e:
            return {"ok": False, "error": "unknown", "message": str(e)}

    def create_pull_request(self, token: str, repo_name: str, head: str, base: str, title: str, body: str = "") -> dict:
        """
        Create a pull request from head -> base.
        Returns { ok, pr_url?, number?, error? }
        """
        try:
            repo = Github(token).get_repo(repo_name)
            pr = repo.create_pull(
                title=title,
                body=body or "Changes committed via GitPhone\n\n---\n*Created automatically by GitPhone bot*",
                head=head,
                base=base,
            )
            return {"ok": True, "pr_url": pr.html_url, "number": pr.number}
        except GithubException as e:
            if e.status == 422:
                # PR already exists
                msg = str(e.data)
                return {"ok": False, "error": "pr_exists", "message": msg}
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
            # Handle list (directory) case - shouldn't happen but guard anyway
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
        Returns: { ok, commit_sha?, error?, conflict_files?, committed_ids? }
        """
        try:
            g = Github(token)
            repo = g.get_repo(repo_name)
            last_sha: str | None = None
            conflict_files: list[str] = []
            committed_ids: list[str] = []

            for staged in staged_files:
                filepath = staged["filepath"]
                stored_base_sha = staged["base_sha"]
                is_binary = staged.get("is_binary", False)
                full_content_b64 = staged.get("full_content")
                diff_text = staged.get("diff")
                file_id = staged.get("id")

                try:
                    # --- Fetch current GitHub state ------------------------------------------
                    gh_file = self.get_file_sha_and_content(token, repo_name, branch, filepath)
                    current_sha = gh_file["sha"]
                    current_content = gh_file["content"]
                    exists_on_gh = gh_file["exists"]

                    # --- Handle deletions ----------------------------------------------------
                    change_type = staged.get("change_type", "modify")
                    if change_type == "delete" or stored_base_sha == "delete":
                        if not exists_on_gh:
                            print(f"[github_service] Skip delete {filepath} - not on GitHub")
                            if file_id:
                                committed_ids.append(file_id)
                            continue
                        result = repo.delete_file(
                            path=filepath,
                            message=commit_message,
                            sha=current_sha,
                            branch=branch,
                        )
                        last_sha = result["commit"].sha
                        if file_id:
                            committed_ids.append(file_id)
                        continue

                    # --- Reconstruct final content -------------------------------------------
                    if is_binary or full_content_b64:
                        final_bytes = base64.b64decode(full_content_b64)
                        content_to_commit = final_bytes
                    else:
                        # Text file - apply diff
                        # For MVP: We are lenient. If diff applies to CURRENT content, we commit.
                        base_content = current_content if exists_on_gh else ""
                        new_content, success = apply_diff(base_content, diff_text)

                        # Only report conflict if diff COMPELTELY fails AND it's not a force commit
                        if not success and stored_base_sha != "force":
                            # If we have a mismatch AND diff failed -> genuine conflict
                            if stored_base_sha != current_sha and stored_base_sha != "new_file":
                                conflict_files.append(filepath)
                                continue

                        new_content = new_content.replace("\r\n", "\n")
                        content_to_commit = new_content.encode("utf-8")

                    # --- Commit to GitHub ---------------------------------------------------------
                    if not exists_on_gh:
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
                    if file_id:
                        committed_ids.append(file_id)

                except Exception as e:
                    print(f"[github_service] Error committing {filepath}: {e}")
                    conflict_files.append(filepath)

            # --- Return result -------------------------------------------------------------------
            if not committed_ids and conflict_files:
                return {
                    "ok": False,
                    "error": "conflict",
                    "conflict_files": conflict_files,
                    "message": "All selected files had conflicts or errors",
                }

            return {
                "ok": len(committed_ids) > 0,
                "commit_sha": last_sha,
                "conflict_files": conflict_files,
                "committed_ids": committed_ids,
            }

        except GithubException as e:
            if e.status == 409:
                return {"ok": False, "error": "conflict", "message": "SHA conflict on GitHub"}
            if e.status == 422:
                msg = str(e.data.get("message", ""))
                if "protected" in msg.lower() or "required" in msg.lower():
                    return {"ok": False, "error": "branch_protected", "message": f"Branch is protected: {msg}"}
                return {"ok": False, "error": "validation_failed", "message": f"GitHub validation failed: {msg}"}
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
        Force commit - overwrites GitHub content with staged version.
        Used when user chooses 'Force Commit' on conflict screen.
        Fetches the CURRENT GitHub SHA (to satisfy the API) but ignores base_sha.
        """
        # Re-fetch current SHA and commit regardless of mismatch
        for staged in staged_files:
            staged["base_sha"] = "force"  # bypass detect_conflict
        return self.commit_files(token, repo_name, branch, staged_files, commit_message)


github_service = GitHubService()
