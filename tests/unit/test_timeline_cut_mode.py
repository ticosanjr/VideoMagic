from __future__ import annotations

from videoflow.steps.timeline import TimelineParams


def test_cut_mode_overrides_legacy_booleans() -> None:
    hard = TimelineParams.model_validate(
        {"cut_mode": "hard", "enable_j_cuts": True, "enable_l_cuts": True}
    )
    assert hard.cut_mode == "hard"
    j_cut = TimelineParams.model_validate({"cut_mode": "j_cut"})
    l_cut = TimelineParams.model_validate({"cut_mode": "l_cut"})
    custom = TimelineParams.model_validate(
        {"cut_mode": "custom", "enable_j_cuts": False, "enable_l_cuts": True}
    )
    assert (j_cut.enable_j_cuts, j_cut.enable_l_cuts) == (True, False)
    assert (l_cut.enable_j_cuts, l_cut.enable_l_cuts) == (False, True)
    assert (custom.enable_j_cuts, custom.enable_l_cuts) == (False, True)
