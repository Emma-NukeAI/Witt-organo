"""
git_sync.py — commit the manifest back to git from the hosted ingest service (GWT v1.1, ADR-0021).

The service container is a COPY of the repo (no .git, no push creds). To keep git the CANONICAL record
of the source of truth, this uses the GitHub Contents API (a token + HTTP, no git binary): on approve it
reads the current corpus_manifest.json FROM GitHub, the caller appends the approved record + ingests, and
this PUTs the updated manifest back as a commit. If GITHUB_TOKEN is unset, push-back is disabled (the
record still enters Neo4j; a maintainer syncs the manifest — the scaffold fallback).

Env: GITHUB_TOKEN (fine-grained PAT with Contents read/write on the repo), GITHUB_REPO
(default Emma-NukeAI/Witt-organo), GITHUB_BRANCH (default master). stdlib only.
"""
import os
import json
import base64
import urllib.request

API = "https://api.github.com"
PATH = "rag_index/corpus_manifest.json"


def enabled():
    return bool(os.environ.get("GITHUB_TOKEN"))


def _repo():
    return os.environ.get("GITHUB_REPO", "Emma-NukeAI/Witt-organo")


def _branch():
    return os.environ.get("GITHUB_BRANCH", "master")


def _req(method, url, data=None):
    req = urllib.request.Request(url, method=method,
                                 data=(json.dumps(data).encode() if data is not None else None))
    req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def get_manifest():
    """Return (manifest_dict, sha) — the CANONICAL manifest from GitHub."""
    resp = _req("GET", f"{API}/repos/{_repo()}/contents/{PATH}?ref={_branch()}")
    content = base64.b64decode(resp["content"]).decode("utf-8")
    return json.loads(content), resp["sha"]


def put_manifest(manifest_dict, sha, message):
    """Commit the updated manifest back to GitHub (Contents API). Returns the commit info."""
    body = {"message": message, "branch": _branch(), "sha": sha,
            "content": base64.b64encode(
                (json.dumps(manifest_dict, indent=2, ensure_ascii=False) + "\n").encode("utf-8")).decode("ascii")}
    resp = _req("PUT", f"{API}/repos/{_repo()}/contents/{PATH}", body)
    return resp.get("commit", {}).get("sha", "?")
