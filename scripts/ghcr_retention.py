"""Apply retention.json to the GHCR package. GHCR has no native lifecycle
policy (unlike ECR), so the policy lives in this repo and a workflow enforces it.

A GHCR "package version" is one digest carrying 0..n tags, and deleting it
removes every tag on it. So decisions are per version:

  protected tag (latest*, stable*, keep-*, buildcache-*)  -> keep
  no tags, older than untagged_max_age_days               -> delete (orphaned cache/moved tags)
  only candidate-* tags, older than max age               -> delete (failed smoke test)
  immutable <ver>-<variant>-r<hash> tag                   -> keep newest N per variant
  anything else                                           -> keep (unknown = safe)

Dry run by default; pass --apply to delete.

Env: GITHUB_TOKEN, OWNER, OWNER_TYPE ("User" | "Organization").
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://api.github.com"


def request(method: str, url: str) -> list | dict | None:
    req = urllib.request.Request(url, method=method, headers={
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req) as r:
        body = r.read()
    return json.loads(body) if body else None


def base_url(package: str) -> str:
    owner = os.environ["OWNER"]
    scope = "orgs" if os.environ.get("OWNER_TYPE") == "Organization" else "users"
    return f"{API}/{scope}/{owner}/packages/container/{package}/versions"


def list_versions(url: str) -> list[dict]:
    versions, page = [], 1
    while batch := request("GET", f"{url}?per_page=100&page={page}"):
        versions += batch
        page += 1
    return versions


def plan(versions: list[dict], policy: dict, now: datetime) -> list[tuple[dict, str]]:
    protect = [re.compile(p) for p in policy["protect_tags"]]
    immutable = re.compile(policy["immutable_tag"])
    cand = policy["candidate_prefix"]
    untagged_age = timedelta(days=policy["untagged_max_age_days"])
    cand_age = timedelta(days=policy["failed_candidate_max_age_days"])

    deletions: list[tuple[dict, str]] = []
    by_variant: dict[str, list[dict]] = defaultdict(list)
    for v in versions:
        tags = v["metadata"]["container"]["tags"]
        age = now - datetime.fromisoformat(v["created_at"].replace("Z", "+00:00"))
        if any(p.search(t) for p in protect for t in tags):
            continue
        if not tags:
            if age > untagged_age:
                deletions.append((v, f"untagged, {age.days}d old"))
            continue
        if all(t.startswith(cand) for t in tags):
            if age > cand_age:
                deletions.append((v, f"failed candidate, {age.days}d old"))
            continue
        match = next((m for t in tags if (m := immutable.match(t))), None)
        if match:
            by_variant[match["variant"]].append(v)

    keep = policy["keep_per_variant"]
    for variant, group in by_variant.items():
        group.sort(key=lambda v: v["created_at"], reverse=True)
        for v in group[keep:]:
            deletions.append((v, f"beyond newest {keep} for {variant}"))
    return deletions


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="retention.json")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    policy = json.loads(Path(args.policy).read_text())
    url = base_url(policy["package"])
    versions = list_versions(url)
    deletions = plan(versions, policy, datetime.now(timezone.utc))

    print(f"{len(versions)} versions, {len(deletions)} to delete ({'APPLY' if args.apply else 'dry run'})")
    for v, why in deletions:
        tags = ",".join(v["metadata"]["container"]["tags"]) or "<untagged>"
        print(f"  - {v['name'][:19]}  {tags}  ({why})")
        if args.apply:
            request("DELETE", f"{url}/{v['id']}")
    if deletions and not args.apply:
        print("dry run: nothing deleted", file=sys.stderr)


if __name__ == "__main__":
    main()
