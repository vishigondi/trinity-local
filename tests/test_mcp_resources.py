"""MCP Resources surface — Phase A of the v2 substrate arc (task #162).

Trinity exposes ~/.trinity/memories/ and the ~/.trinity/scoreboard/
files as MCP Resources. Resources are listed at session start so any
MCP-aware harness sees them without a tool round-trip — the agent
reads `trinity://memories/lens.md` before the user types a prompt
and conditions every response on the lens.

The contract these tests pin:

1. The catalog enumerates exactly the six canonical resources (4
   memories + 2 scoreboards). Adding or removing one should be a
   deliberate spec change, not a silent drift. AGENTS.md was dropped
   2026-05-26 — see _resource_catalog docstring for the rationale.
2. URIs follow `trinity://` scheme (per the v2 spec at
   docs/PREFERENCE_CORPUS_SPEC.md).
3. Cold-install reads (when the underlying file doesn't exist)
   return a stub with an actionable next-step (`trinity-local dream`),
   NOT a 404. The stub is what makes the agent useful out of the box:
   it can tell the user "your lens isn't built yet — run dream first."
4. Populated reads return raw file contents byte-for-byte.
"""
from __future__ import annotations

import asyncio
import json

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Isolate ~/.trinity/ so cold-install + populated-install paths
    are testable in parallel without leaking state."""
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def populated_home(isolated_home):
    """Seed the four cognitive memories + scoreboards with known
    content so the read path can assert on body bytes."""
    memories = isolated_home / "memories"
    memories.mkdir(parents=True, exist_ok=True)
    (memories / "core.md").write_text("# Core\nidentity-paragraph", encoding="utf-8")
    (memories / "lens.md").write_text("# Lens\npaired tensions here", encoding="utf-8")
    (memories / "topics.json").write_text(json.dumps({"basins": []}), encoding="utf-8")
    (memories / "vocabulary.md").write_text("# Vocabulary\nanchors", encoding="utf-8")
    scoreboard = isolated_home / "scoreboard"
    scoreboard.mkdir(parents=True, exist_ok=True)
    (scoreboard / "picks.json").write_text(json.dumps({"rules": {}}), encoding="utf-8")
    (scoreboard / "routing.json").write_text(json.dumps({"task_types": {}}), encoding="utf-8")
    return isolated_home


class TestResourceCatalog:
    """The catalog is the contract — adding/removing a resource is a
    deliberate spec change, not a silent drift. The six canonical
    resources MUST be exactly: core / lens / topics / vocabulary /
    picks / routing. AGENTS.md was on this list briefly but dropped
    2026-05-26 — AGENTS.md is project-scoped by convention (./AGENTS.md
    in the user's repo) and exposing a user-home one was ceremonial;
    every harness that reads AGENTS.md also reads MCP Resources, so
    the lens flows via trinity://memories/lens.md."""

    def test_catalog_has_six_canonical_resources(self, isolated_home):
        from trinity_local.mcp_server import _resource_catalog
        catalog = _resource_catalog()
        uris = {entry[0] for entry in catalog}
        assert uris == {
            "trinity://memories/core.md",
            "trinity://memories/lens.md",
            "trinity://memories/topics.json",
            "trinity://memories/vocabulary.md",
            "trinity://scoreboard/picks.json",
            "trinity://scoreboard/routing.json",
        }, (
            "Resource catalog drifted from the v2 substrate spec. "
            "Adding/removing a resource is a deliberate change — update "
            "docs/PREFERENCE_CORPUS_SPEC.md schemas table AND this test."
        )

    def test_agentsmd_not_in_catalog(self, isolated_home):
        """AGENTS.md was dropped 2026-05-26. Regression guard against
        a future PR adding it back without revisiting the rationale:
        AGENTS.md is project-scoped; harnesses that read it also read
        MCP Resources; exposing it as a user-home resource was
        ceremonial."""
        from trinity_local.mcp_server import _resource_catalog
        uris = {entry[0] for entry in _resource_catalog()}
        assert "trinity://AGENTS.md" not in uris, (
            "trinity://AGENTS.md re-appeared in the catalog. Per the "
            "2026-05-26 decision, AGENTS.md is not a Trinity-exposed "
            "surface — the lens flows via trinity://memories/lens.md. "
            "If reviving, update the docstring + spec first."
        )

    def test_each_entry_has_description_and_mime(self, isolated_home):
        from trinity_local.mcp_server import _resource_catalog
        for uri, name, description, mime, path_func in _resource_catalog():
            assert name, f"Resource {uri} missing name"
            assert description, f"Resource {uri} missing description"
            assert mime in ("text/markdown", "application/json"), (
                f"Resource {uri} has unexpected MIME type: {mime}"
            )
            # path_func must be callable + return a Path (not eval it yet)
            assert callable(path_func), f"Resource {uri} path is not a callable"

    def test_uri_scheme_is_trinity(self, isolated_home):
        from trinity_local.mcp_server import _resource_catalog
        for uri, *_ in _resource_catalog():
            assert uri.startswith("trinity://"), (
                f"Resource URI {uri!r} doesn't use the trinity:// scheme — "
                f"per the v2 spec all Trinity resources MUST be trinity:// "
                f"so harnesses can disambiguate from other MCP servers'."
            )


class TestListResources:
    """The MCP server's list_resources handler must advertise all 6
    canonical resources unconditionally — even when the underlying
    files don't exist yet (cold install). The READ path handles
    cold-install via stubs; the LIST path always shows the catalog."""

    def test_list_returns_all_resources_on_cold_install(self, isolated_home):
        from trinity_local.mcp_server import handle_list_resources
        resources = asyncio.run(handle_list_resources())
        assert len(resources) == 6, (
            f"Cold install should still advertise all 6 resources (so the "
            f"agent sees them + reads the stubs that explain how to populate); "
            f"got {len(resources)}"
        )
        uris = {str(r.uri) for r in resources}
        assert "trinity://memories/lens.md" in uris

    def test_list_returns_same_resources_when_populated(self, populated_home):
        from trinity_local.mcp_server import handle_list_resources
        resources = asyncio.run(handle_list_resources())
        assert len(resources) == 6

    def test_resource_objects_have_required_fields(self, isolated_home):
        """Each Resource the harness lists must have uri/name/description/
        mimeType — without all four, the harness's resource picker UI
        renders broken entries (no description = the user has no idea
        what they're enabling)."""
        from trinity_local.mcp_server import handle_list_resources
        resources = asyncio.run(handle_list_resources())
        for r in resources:
            assert r.uri is not None
            assert r.name
            assert r.description
            assert r.mimeType in ("text/markdown", "application/json")


class TestReadResourcePopulated:
    """When the file exists on disk, read_resource returns its contents
    byte-for-byte. No transformation, no escaping — the harness gets
    exactly what's on disk."""

    def test_lens_md_returns_file_contents(self, populated_home):
        from pydantic import AnyUrl
        from trinity_local.mcp_server import handle_read_resource
        result = asyncio.run(handle_read_resource(AnyUrl("trinity://memories/lens.md")))
        assert result == "# Lens\npaired tensions here"

    def test_topics_json_returns_file_contents(self, populated_home):
        from pydantic import AnyUrl
        from trinity_local.mcp_server import handle_read_resource
        result = asyncio.run(handle_read_resource(AnyUrl("trinity://memories/topics.json")))
        # Round-trip — content is whatever the test fixture wrote
        assert json.loads(result) == {"basins": []}

    def test_picks_json_returns_file_contents(self, populated_home):
        from pydantic import AnyUrl
        from trinity_local.mcp_server import handle_read_resource
        result = asyncio.run(handle_read_resource(AnyUrl("trinity://scoreboard/picks.json")))
        assert json.loads(result) == {"rules": {}}


class TestReadResourceColdInstall:
    """When the file doesn't exist yet, read_resource MUST return a
    stub with an actionable next-step (run `trinity-local dream`)
    rather than 404. This is what makes Trinity useful out of the
    box: the agent reads the stub, sees the suggested action, and
    can surface it to the user."""

    def test_lens_md_returns_actionable_stub_when_missing(self, isolated_home):
        from pydantic import AnyUrl
        from trinity_local.mcp_server import handle_read_resource
        result = asyncio.run(handle_read_resource(AnyUrl("trinity://memories/lens.md")))
        # Stub must name the resource (so the agent knows WHICH was empty),
        # the action to populate it, AND the on-disk path (for debugging).
        assert "Trinity Lens" in result, "stub must include the resource name"
        assert "trinity-local dream" in result, (
            "stub must include the actionable command to populate this resource"
        )
        assert "trinity://memories/lens.md" in result, "stub must include the resource URI"

    def test_unknown_uri_raises(self, isolated_home):
        from pydantic import AnyUrl
        from trinity_local.mcp_server import handle_read_resource
        with pytest.raises(ValueError, match="Unknown Trinity resource"):
            asyncio.run(handle_read_resource(AnyUrl("trinity://not-a-thing")))


class TestResourceCatalogReflectsTrinityHome:
    """When TRINITY_HOME changes (test isolation), the path_func
    closures must resolve to the NEW home. Without this, tests
    leak into the real ~/.trinity/ and pollute the user's state."""

    def test_paths_resolve_under_test_home(self, isolated_home):
        from trinity_local.mcp_server import _resource_catalog
        catalog = _resource_catalog()
        for uri, _name, _desc, _mime, path_func in catalog:
            path = path_func()
            # Every resource path must be under the isolated test home,
            # never under the real $HOME/.trinity/.
            assert str(path).startswith(str(isolated_home)), (
                f"Resource {uri} resolved to {path} which is OUTSIDE the "
                f"isolated home {isolated_home}. The path_func closure is "
                f"capturing the wrong trinity_home() — likely evaluated at "
                f"import time instead of call time."
            )
