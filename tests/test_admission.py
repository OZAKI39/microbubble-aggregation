from microbubble.analysis import time_windows


def test_pair_pass_cannot_promote_an_unrefined_long_window():
    s = dict(
        rows=[
            dict(
                id="short",
                kind="HF",
                status="PASS",
                task={},
                state="a",
                action="X",
                N=32,
                completed_s=0.15,
            ),
            dict(
                id="long",
                kind="HF",
                status="PASS",
                task={},
                state="a",
                action="X",
                N=32,
                completed_s=0.25,
            ),
        ],
        paired=[dict(id="short", PASS=True), dict(id="long", PASS=True)],
        convergence=[
            dict(id="short_DT05", parent="short", PASS=True),
            dict(id="short_FINE", parent="short", PASS=True),
        ],
    )
    assert time_windows(s)["max_new_paired_and_refined_s"] == 0.15
    s["convergence"][1]["PASS"] = False
    assert time_windows(s)["max_new_paired_and_refined_s"] == 0
