"""Tests for ghcr_retention.py. Run: python3 -m unittest discover -s scripts"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ghcr_retention import plan, spare_referenced

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)
POLICY = json.loads((Path(__file__).parent.parent / "retention.json").read_text())


def version(vid: int, digest: str, tags: list[str], days_old: int) -> dict:
    created = (NOW - timedelta(days=days_old)).isoformat().replace("+00:00", "Z")
    return {"id": vid, "name": digest, "created_at": created,
            "metadata": {"container": {"tags": tags}}}


def run(versions: list[dict], indexes: dict[str, list[str]]) -> set[str]:
    deletions = plan(versions, POLICY, NOW)
    deletions = spare_referenced(versions, deletions, lambda d: indexes.get(d, []))
    return {v["name"] for v, _ in deletions}


class SpareReferencedTest(unittest.TestCase):
    def test_published_candidate_manifest_is_kept(self):
        # Regression: imagetools create wraps the candidate's manifest in a new
        # index carrying the published tags; the manifest itself keeps only its
        # candidate-* tag and was deleted as a "failed candidate".
        versions = [
            version(1, "sha256:cand", ["candidate-0.39.2-cu130-r51e6eee4"], 3),
            version(2, "sha256:pub", ["0.39.2-cu130-r51e6eee4", "0.39.2", "latest"], 3),
        ]
        self.assertEqual(run(versions, {"sha256:pub": ["sha256:cand"]}), set())

    def test_untagged_child_of_stable_is_kept(self):
        versions = [
            version(1, "sha256:child", [], 10),
            version(2, "sha256:stable", ["stable", "stable-cu130"], 10),
        ]
        self.assertEqual(run(versions, {"sha256:stable": ["sha256:child"]}), set())

    def test_spared_index_protects_its_children(self):
        # stable -> (untagged, otherwise deletable) index -> manifest
        versions = [
            version(1, "sha256:leaf", [], 10),
            version(2, "sha256:mid", [], 10),
            version(3, "sha256:stable", ["stable"], 10),
        ]
        indexes = {"sha256:stable": ["sha256:mid"], "sha256:mid": ["sha256:leaf"]}
        self.assertEqual(run(versions, indexes), set())

    def test_unreferenced_still_deleted(self):
        versions = [
            version(1, "sha256:orphan", [], 10),
            version(2, "sha256:failed", ["candidate-0.39.3-cu130-r51e6eee4"], 3),
            version(3, "sha256:pub", ["latest"], 3),
        ]
        self.assertEqual(run(versions, {"sha256:pub": []}), {"sha256:orphan", "sha256:failed"})

    def test_children_of_deleted_index_are_not_protected(self):
        # An old release pruned for being beyond newest N must not shield its manifest.
        versions = [version(10 + i, f"sha256:rel{i}", [f"0.{i}.0-cu130-r51e6eee4"], 30 - i)
                    for i in range(6)]
        versions.append(version(1, "sha256:rel0child", [], 30))
        deleted = run(versions, {"sha256:rel0": ["sha256:rel0child"]})
        self.assertEqual(deleted, {"sha256:rel0", "sha256:rel0child"})


if __name__ == "__main__":
    unittest.main()
