"""Pyflakes-as-test: catch undefined-name bugs that mock-heavy unit
tests miss.

Earned 2026-05-16: `me_builder.build_me_via_lens_pipeline` had three
references to `chairman_name` (the variable in scope was `chairman`).
Every unit test that touched lens-build did so via
`monkeypatch.setattr` of the whole function — so the NameError
never fired in tests. Only a real-user `trinity-local lens-build`
would have hit it.

Principle #5 ("Real-data validation is the substantive test") at the
static-analysis tier. Pyflakes catches what mocked unit tests
can't.

Scope: undefined names ONLY. The unused-import / unused-variable
warnings pyflakes also emits are useful but noisier — they can be
cleaned in dedicated passes. Catching `NameError-at-runtime` is the
high-stakes target.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_no_undefined_names_in_src():
    """Run pyflakes against src/trinity_local/ and fail on any
    `undefined name` line. Other pyflakes warnings (unused imports,
    f-strings without placeholders) are tolerated — they're style
    issues, not crashes.
    """
    src = REPO / "src" / "trinity_local"
    result = subprocess.run(
        ["python", "-m", "pyflakes", str(src)],
        capture_output=True,
        text=True,
    )
    # pyflakes returns 1 when it finds issues — that's expected. We only
    # care about the substantive ones.
    undefined_lines = [
        line for line in result.stdout.splitlines()
        if "undefined name" in line
    ]
    assert not undefined_lines, (
        "pyflakes found undefined-name references in src/. These are "
        "runtime NameErrors that fire on the real user's machine but "
        "don't trip unit tests (which mock the offending functions).\n\n"
        + "\n".join(undefined_lines)
        + "\n\nFix the names or pre-define the variables before use."
    )
