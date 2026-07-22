from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".py", ".toml", ".yaml", ".yml", ".example"}
BANNED_DEPLOYMENT_LITERALS = (
    "192" + ".168.",
    "/mnt" + "/user/",
    "C:" + "\\Users\\",
)


class RepositoryHygieneTests(TestCase):
    def test_public_sources_do_not_embed_private_deployment_paths(self):
        failures: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            if path.suffix not in TEXT_SUFFIXES and path.name != ".env.example":
                continue
            content = path.read_text(encoding="utf-8")
            for literal in BANNED_DEPLOYMENT_LITERALS:
                if literal in content:
                    failures.append(f"{path.relative_to(ROOT)} contains {literal!r}")
        self.assertEqual([], failures)
