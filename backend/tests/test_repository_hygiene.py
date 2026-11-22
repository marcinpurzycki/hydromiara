"""No secrets, e-mail addresses or local configuration in the tracked files and in the image.

The files checked are the ones git tracks, so the test needs the repository;
it is skipped where there is none (an unpacked archive).
"""

import re
import subprocess
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
BACKEND = REPOSITORY / "backend"

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
# Domains reserved for documentation (RFC 2606) may appear in examples.
ALLOWED_EMAIL_DOMAINS = ("example.org", "example.com", "example.net")

SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "API key (sk-...)": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{30,}"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    "JSON web token": re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}\."),
    "signed storage address": re.compile(r"[?&]sig=[A-Za-z0-9%+/]{20,}"),
    "password in an address": re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s:@]+@"),
    "home directory": re.compile(r"/home/[a-z][a-z0-9_-]*/|/Users/[A-Za-z]|[A-Z]:\\Users\\"),
}
# A value given to a name that says it is secret, in a file of settings.
ASSIGNED_SECRET = re.compile(
    r"^[ \t]*([A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|PASSWD)[A-Z0-9_]*)[ \t]*[=:][ \t]*(\S+)",
    re.MULTILINE,
)
SETTINGS_FILES = (".env.example", "docker-compose.yml", "docker-compose.local.yml")
FORBIDDEN_NAMES = re.compile(
    r"(^|/)(\.env(\..+)?|.*\.pem|.*\.key|id_rsa.*|credentials.*\.json|AGENTS\.md|CLAUDE\.md)$"
)
ALLOWED_NAMES = {".env.example"}


def tracked_files() -> list[Path]:
    try:
        listed = subprocess.run(
            ["git", "-C", str(REPOSITORY), "ls-files", "-z"],
            capture_output=True, timeout=30, check=True,
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        pytest.skip("the tracked files cannot be listed (no git repository)")
    names = [name for name in listed.stdout.decode("utf-8").split("\0") if name]
    return [REPOSITORY / name for name in names if (REPOSITORY / name).is_file()]


def text_of(path: Path) -> str | None:
    raw = path.read_bytes()
    if b"\0" in raw[:8192]:
        return None  # binary (raster fixtures)
    return raw.decode("utf-8", errors="replace")


def tracked_texts() -> list[tuple[str, str]]:
    texts = []
    for path in tracked_files():
        text = text_of(path)
        if text is not None:
            texts.append((path.relative_to(REPOSITORY).as_posix(), text))
    assert len(texts) > 50, "the list of tracked files looks incomplete"
    return texts


def test_no_secret_patterns_in_tracked_files():
    found = [
        f"{name}: {label}"
        for name, text in tracked_texts()
        for label, pattern in SECRET_PATTERNS.items()
        if pattern.search(text)
    ]
    assert found == []


def test_no_email_addresses_in_tracked_files():
    found = [
        f"{name}: {address}"
        for name, text in tracked_texts()
        for address in EMAIL.findall(text)
        if not address.lower().endswith(ALLOWED_EMAIL_DOMAINS)
    ]
    assert found == []


def test_no_secret_or_process_files_are_tracked():
    names = [path.relative_to(REPOSITORY).as_posix() for path in tracked_files()]
    found = [
        name for name in names
        if FORBIDDEN_NAMES.search(name) and Path(name).name not in ALLOWED_NAMES
    ]  # fmt: skip
    assert found == []


def test_settings_files_give_no_value_to_secret_names():
    for name in SETTINGS_FILES:
        text = (REPOSITORY / name).read_text(encoding="utf-8")
        for variable, value in ASSIGNED_SECRET.findall(text):
            # Only a reference to the environment is allowed, with an empty default.
            assert re.fullmatch(r"\$\{" + variable + r":-\}", value), (name, variable)


def test_patterns_find_what_they_are_meant_to_find():
    """The checks above would be worthless if the patterns matched nothing."""
    samples = {
        "private key": "-----BEGIN RSA " + "PRIVATE KEY-----",
        "API key (sk-...)": "sk-" + "a1B2" * 8,
        "AWS access key": "AKIA" + "ABCDEFGH12345678",
        "GitHub token": "ghp_" + "a" * 36,
        "Slack token": "xoxb-" + "1234567890-abcdef",
        "JSON web token": "eyJ" + "a" * 20 + ".eyJ" + "b" * 20 + ".sig",
        "signed storage address": "https://host/file.tif?sv=1&sig=" + "A" * 30,
        "password in an address": "postgres://user:" + "pass@host/db",
        "home directory": "/home/" + "someone/project",
    }
    assert set(samples) == set(SECRET_PATTERNS)
    for label, sample in samples.items():
        assert SECRET_PATTERNS[label].search(sample), label
    address = "someone@" + "mail.example.pl"
    assert EMAIL.findall(f"write to {address} now") == [address]
    assert EMAIL.findall("@pytest.fixture and user@host") == []
    assert ASSIGNED_SECRET.findall("AI_API_KEY=abc\n") == [("AI_API_KEY", "abc")]
    assert ASSIGNED_SECRET.findall("AI_API_KEY=\n# KEY: text\n") == []


def test_image_is_built_without_tests_and_local_configuration():
    ignored = (BACKEND / ".dockerignore").read_text(encoding="utf-8").split()
    for entry in ("tests/", ".venv/", ".git/", "data/", "**/.env", "**/.env.*", "**/*.sqlite3"):
        assert entry in ignored, entry
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    copied = re.findall(r"^COPY\s+(.+)$", dockerfile, re.MULTILINE)
    # Only the requirements and the application package go into the image.
    assert copied == ["requirements.txt .", "app ./app"]
    assert re.search(r"^USER app$", dockerfile, re.MULTILINE)
    assert not re.search(r"^(ARG|ENV)\s+\S*(KEY|SECRET|TOKEN|PASSWORD)", dockerfile, re.MULTILINE)


def test_server_is_started_without_access_log_and_server_header():
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    command = dockerfile[dockerfile.index("CMD") :]
    for flag in ("--proxy-headers", "--no-access-log", "--no-server-header"):
        assert f'"{flag}"' in command, flag
    # Trusting every address would let any client choose the address it is counted under.
    assert "forwarded-allow-ips" not in command
    compose = (REPOSITORY / "docker-compose.yml").read_text(encoding="utf-8")
    assert "FORWARDED_ALLOW_IPS: ${FORWARDED_ALLOW_IPS:-127.0.0.1}" in compose
