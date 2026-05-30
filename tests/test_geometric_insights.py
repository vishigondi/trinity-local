"""#257 prompt-space mining: outlier_prompts() finds the asks farthest from
every subject basin. Pure geometry over local embeddings — no LLM."""
from __future__ import annotations


def test_outliers_not_ready_without_centroids(tmp_path, monkeypatch):
    # No topics.json -> no centroids -> not ready (don't fabricate outliers).
    import trinity_local.state_paths as sp
    monkeypatch.setattr(sp, "state_dir", lambda: tmp_path)
    import importlib
    import trinity_local.me.geometric_insights as gi
    importlib.reload(gi)
    assert gi.outlier_prompts().get("ready") is False


def test_outliers_rank_farthest_first(tmp_path, monkeypatch):
    """With two basins and three planted prompts, the prompt orthogonal to both
    centroids ranks above the ones sitting on a centroid."""
    import json
    import trinity_local.state_paths as sp
    monkeypatch.setattr(sp, "state_dir", lambda: tmp_path)
    monkeypatch.setattr(sp, "trinity_home", lambda: tmp_path, raising=False)
    (tmp_path / "memories").mkdir(parents=True, exist_ok=True)
    # Two unit-axis basins.
    (tmp_path / "memories" / "topics.json").write_text(json.dumps({"basins": [
        {"id": "b00", "label": "alpha", "centroid": [1.0, 0.0, 0.0, 0.0]},
        {"id": "b01", "label": "beta", "centroid": [0.0, 1.0, 0.0, 0.0]},
    ]}), encoding="utf-8")

    import importlib
    import trinity_local.me.geometric_insights as gi
    importlib.reload(gi)

    pad = "x" * 60  # clear the min_chars floor
    nodes = [
        ("on_alpha " + pad, [1.0, 0.0, 0.0, 0.0]),     # max-cos 1.0
        ("on_beta " + pad, [0.0, 1.0, 0.0, 0.0]),      # max-cos 1.0
        ("orthogonal " + pad, [0.0, 0.0, 1.0, 0.0]),   # max-cos 0.0 -> outlier
    ]

    class _N:
        def __init__(self, text, emb):
            self.text, self.embedding = text, emb

    monkeypatch.setattr(gi, "iter_prompt_nodes", lambda limit=None: [_N(t, e) for t, e in nodes], raising=False)
    # iter_prompt_nodes is imported inside the function from ..memory.store;
    # patch there.
    import trinity_local.memory.store as store
    monkeypatch.setattr(store, "iter_prompt_nodes", lambda limit=None: [_N(t, e) for t, e in nodes])

    res = gi.outlier_prompts(top_n=3, min_chars=40)
    assert res["ready"] is True
    assert res["outliers"][0]["snippet"].startswith("orthogonal")
    assert res["outliers"][0]["nearest_cosine"] < 0.5
