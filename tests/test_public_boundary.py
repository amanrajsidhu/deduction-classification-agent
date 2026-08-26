import gzip
import json
import re
import subprocess
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / "workflows"


def public_candidates():
    completed = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return [ROOT / line for line in completed.stdout.splitlines() if line]


def readable_payloads(path):
    if path.suffix.lower() == ".xlsx":
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.endswith((".xml", ".rels")):
                    yield archive.read(name).decode("utf-8", errors="ignore")
    elif path.suffix.lower() == ".gz":
        yield gzip.decompress(path.read_bytes()).decode("utf-8", errors="ignore")
    elif path.suffix.lower() in {
        ".csv", ".json", ".md", ".py", ".txt", ".yml", ".yaml", ".gitignore"
    } or path.name == ".gitignore":
        yield path.read_text(encoding="utf-8", errors="ignore")


class PublicBoundaryTests(unittest.TestCase):
    def test_public_candidates_contain_no_recognisable_secret_material(self):
        patterns = {
            "Anthropic API key": re.compile("sk" + r"-ant-[A-Za-z0-9_-]{20,}"),
            "Slack token": re.compile("xo" + r"x[baprs]-[A-Za-z0-9-]{10,}"),
            "Private key": re.compile("BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY"),
        }
        hits = []
        for path in public_candidates():
            if not path.is_file():
                continue
            for payload in readable_payloads(path):
                for label, pattern in patterns.items():
                    if pattern.search(payload):
                        hits.append(f"{path.relative_to(ROOT)}: {label}")
        self.assertEqual(hits, [])

    def test_public_workflow_exports_have_no_live_instance_references(self):
        for path in WORKFLOW_DIR.glob("*.json"):
            workflow = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(workflow.get("active"), path.name)
            self.assertFalse(workflow.get("settings", {}).get("availableInMCP"), path.name)
            self.assertNotIn("id", workflow, path.name)
            self.assertNotIn("versionId", workflow, path.name)
            self.assertNotIn("instanceId", workflow.get("meta", {}), path.name)
            for node in workflow.get("nodes", []):
                for credential in node.get("credentials", {}).values():
                    self.assertEqual(
                        credential.get("id"), "REPLACE_WITH_N8N_CREDENTIAL_ID", path.name
                    )


if __name__ == "__main__":
    unittest.main()
