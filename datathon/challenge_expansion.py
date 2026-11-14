"""Further frozen-input challenge and resilience cases.

The rounded weights and losses were derived directly from starter price and
FX endpoints/paths, the starting portfolio weights, and reported issuer
weights. The benchmark scores the recorded expectations after selection.
"""

from .benchmark_cases import ProfileGold
_DISCLOSED = ("issuer:QQQ:2026-06-30", "issuer:SPY:2026-06-30")
_BOTH = ("QQQ", "ZST.TO")


def cases(make_case, *, abstain, baseline_blocked, exact_blocked, issuer_unknown, partial, approved, market_unknown):
    """Construct the held-out fixtures with the benchmark's shared case types."""
    return (
        make_case(
            "thin_loss_margin",
            "The closing value just fits this loss rule. What if we counted the deepest decline "
            "from a prior peak instead, with the same limit and trade terms?",
            ProfileGold(600, "QQQ", _BOTH, True, "terminal_loss", 1260),
            "toggle_loss_metric", "comparison_verified", approved, baseline_blocked,
            (("eligible_max_total", 600, None), ("full_zst_max", 43, None), ("proposal_loss_headroom", 12, -438)),
            "The 2022 fully QQQ-funded endpoint falls 12.4759%. The weighted interpolation permits 42.51 "
            "basis points of ZST.TO funding under the cap. The starting portfolio's 16.0530% drawdown "
            "already breaches the alternative measuring convention.",
        ),
        make_case(
            "loose_loss_rule",
            "What would opening-to-closing loss show under the same ceiling? Keep the proposed purchase "
            "and test whether measuring the endpoint changes anything we can do.",
            ProfileGold(450, "QQQ", _BOTH, False, "max_drawdown", 2000),
            "toggle_loss_metric", "no_material_change", approved, approved,
            (("full_zst_max", 450, 450), ("eligible_max_total", 450, 450), ("proposal_loss_headroom", 325, 781)),
            "Both full-size endpoints satisfy the loose limit. The drawdown cap also holds for all mixes: "
            "both endpoint paths satisfy every earlier-peak/later-trough inequality, which is affine in weights.",
        ),
        make_case(
            "reserve_exceeds_start",
            "Stress the cash-like buffer by moving its minimum up three allocation points. Can selling "
            "only the other funding sleeve still leave enough in the reserve before and after the trade?",
            ProfileGold(300, "QQQ", _BOTH, False, reserve_floor_bps=1800),
            "tighten_reserve_floor", "comparison_verified", approved, baseline_blocked,
            (("eligible_max_total", 300, None), ("full_zst_max", 200, None), ("proposal_reserve_headroom", 200, -100)),
            "The 21% reserve floor exceeds the untraded 20% reserve. Selling either permitted sleeve to "
            "buy NVDA cannot increase reserve weight.",
        ),
        make_case(
            "reserve_already_dominated",
            "Hold the closing-loss limit fixed and raise our short-term bond buffer by three "
            "percentage points. I want to learn whether its tighter limit moves the funding boundary.",
            ProfileGold(1200, "QQQ", _BOTH, True, "terminal_loss", 1375, 1300),
            "tighten_reserve_floor", "no_material_change", approved, approved,
            (("eligible_max_total", 1200, 1200), ("full_zst_max", 48, 48), ("proposal_reserve_headroom", 700, 400)),
            "At a fixed 12% total, endpoint interpolation caps ZST.TO at 48.08 bp. That is less than "
            "the reserve allowances of 700 bp before and 400 bp after.",
        ),
        make_case(
            "size_exact_is_redundant",
            "For a comparison only, require the whole previously requested amount. Does forbidding "
            "smaller purchases take away this full QQQ-funded result?",
            ProfileGold(350, "QQQ", ("QQQ",), True),
            "toggle_purchase_size", "no_material_change", approved, approved,
            (("eligible_max_total", 350, 350), ("full_zst_max", 0, 0)),
            "The only permitted source starts at 20%. There is no cap or reserve rule that blocks its "
            "entire 3.50-point sale. An exact-size rule cannot remove this tested full-size result.",
        ),
        make_case(
            "size_exact_decimal",
            "With the same bond buffer and only that fund as a financing source, what is achievable "
            "if we test a purchase that need not reach the full requested amount?",
            ProfileGold(425, "ZST.TO", ("ZST.TO",), False, "terminal_loss", 1390, 1840),
            "toggle_purchase_size", "comparison_verified", exact_blocked, partial,
            (("eligible_max_total", None, 160), ("diagnostic_max_total", 160, 160),
             ("proposal_reserve_headroom", -265, -265)),
            "20.00% less the 18.40% reserve permits 1.60 points. At that size, directly computed worst "
            "terminal loss is about 12.1116%, within the 13.90% cap.",
        ),
        make_case(
            "issuer_filings_tomorrow",
            "For this as-of review, identify which dated disclosures we still need. Leave the trade "
            "size and issuer ceiling alone, and require public availability on the reference date.",
            ProfileGold(650, "QQQ", _BOTH, True, issuer_cap_bps=1050),
            "request_issuer_evidence", "issuer_evidence_required", issuer_unknown, None,
            (("proposal_issuer_lower", 650, None), ("proposal_issuer_upper", 10000, None)),
            "Both SPY and QQQ disclosures were published August 28. The prior day's review can only "
            "verify 6.50% direct and must leave all indirect positions unresolved.",
            required_disclosure="SPY", evidence_date="2026-08-27",
            required_disclosure_reason="publication_after_knowledge_cutoff", expected_issuer_ids=((), None),
        ),
        make_case(
            "issuer_same_day_available",
            "Check whether requiring holdings no older than 90 days affects the concentration finding "
            "on this reference date. Keep the cap, fund weights and publication cutoff fixed.",
            ProfileGold(650, "QQQ", _BOTH, True, issuer_cap_bps=1050),
            "tighten_holdings_age", "no_material_change", issuer_unknown, issuer_unknown,
            (("proposal_issuer_lower", 1016, 1016), ("proposal_issuer_upper", 5516, 5516)),
            "Both records are public on August 28 and their June 30 observation is 59 days old. "
            "6.50% direct plus SPY weight times its filed exposure plus retained QQQ weight times its filed "
            "exposure is 10.1565%. The two funds with unresolved exposure add 45 points to the upper bound.",
            holdings_max_age_days=150, evidence_date="2026-08-28", expected_issuer_ids=(_DISCLOSED, _DISCLOSED),
        ),
        make_case(
            "issuer_at_age_cutoff",
            "The current disclosures sit just on the age cutoff. What remains verified if we reduce "
            "the allowed age by one day and leave the reference date untouched?",
            ProfileGold(650, "QQQ", _BOTH, True, issuer_cap_bps=1050),
            "tighten_holdings_age", "comparison_verified", issuer_unknown, issuer_unknown,
            (("proposal_issuer_lower", 1016, 650), ("proposal_issuer_upper", 5516, 10000)),
            "The June 30 observations are exactly 90 days old on September 28. They qualify at 90 "
            "days but become stale at 89; exposure becomes bounded by 6.50% direct and 100% possible.",
            holdings_max_age_days=90, evidence_date="2026-09-28", expected_issuer_ids=(_DISCLOSED, ()),
        ),
        make_case(
            "unsupported_asset_counterfactual",
            "Only analyze a hypothetical switch from NVDA to AAPL. If the comparison cannot change the "
            "target security, keep the independently checked result and skip every alternative test.",
            ProfileGold(450, "QQQ", _BOTH, True, "terminal_loss", 1450, 1200),
            abstain, "challenge_declined", approved, None,
            (("eligible_max_total", 450, None), ("full_zst_max", 450, None)),
            "A replacement ticker is outside the allowable challenge catalog. The supported 4.50-point "
            "record remains an audit of the confirmed NVDA proposal.",
        ),
        make_case(
            "market_fx_endpoint_missing",
            "Can the initial result be used to challenge the loss rule if the closing USD/CAD fixing "
            "for the second replay has not arrived?",
            ProfileGold(450, "QQQ", _BOTH, False, "terminal_loss", 1450),
            abstain, "baseline_not_verified", market_unknown, None,
            (("proposal_terminal_loss", None, None), ("eligible_max_total", None, None)),
            "Removing only April 8, 2025 from the official FX observations leaves no common replay "
            "end date. No selected challenge or checked replay result is expected.",
            omitted_fx_date="2025-04-08",
        ),
    )
