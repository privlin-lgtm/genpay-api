import pytest

from app.services.revenue_split import (
    BASIS_POINTS_TOTAL,
    RevenueSplitConfig,
    RevenueSplitResult,
    split_amount,
)

DEFAULT_CONFIG = RevenueSplitConfig(archive_bps=7000, transcriptionist_bps=2000, platform_bps=1000)


# --- RevenueSplitConfig validation -----------------------------------------------


def test_config_accepts_shares_summing_to_100_percent():
    config = RevenueSplitConfig(archive_bps=7000, transcriptionist_bps=2000, platform_bps=1000)
    assert config.archive_bps + config.transcriptionist_bps + config.platform_bps == BASIS_POINTS_TOTAL


def test_config_rejects_shares_that_dont_sum_to_100_percent():
    with pytest.raises(ValueError, match="must sum to 100%"):
        RevenueSplitConfig(archive_bps=7000, transcriptionist_bps=2000, platform_bps=500)


def test_config_rejects_shares_summing_over_100_percent():
    with pytest.raises(ValueError, match="must sum to 100%"):
        RevenueSplitConfig(archive_bps=7000, transcriptionist_bps=2000, platform_bps=2000)


def test_config_rejects_negative_share():
    with pytest.raises(ValueError, match="archive_bps must be >= 0"):
        RevenueSplitConfig(archive_bps=-100, transcriptionist_bps=9000, platform_bps=1100)


def test_config_from_percentages_matches_default_bps():
    config = RevenueSplitConfig.from_percentages(archive=70, transcriptionist=20, platform=10)
    assert config == DEFAULT_CONFIG


def test_config_from_settings_matches_default_env():
    config = RevenueSplitConfig.from_settings()
    assert config == DEFAULT_CONFIG


# --- split_amount: exact cases ----------------------------------------------------


def test_ten_dollar_purchase_splits_exactly_with_no_rounding_needed():
    # $10.00 -> 1000 cents; 70/20/10 of 1000 are all whole numbers already.
    result = split_amount(1000, DEFAULT_CONFIG)
    assert result == RevenueSplitResult(archive_cents=700, transcriptionist_cents=200, platform_cents=100)
    assert result.total_cents == 1000


@pytest.mark.parametrize(
    "total_cents,expected",
    [
        (100, RevenueSplitResult(70, 20, 10)),
        (2000, RevenueSplitResult(1400, 400, 200)),
        (10_000, RevenueSplitResult(7000, 2000, 1000)),
    ],
)
def test_amounts_that_divide_evenly(total_cents, expected):
    assert split_amount(total_cents, DEFAULT_CONFIG) == expected


# --- split_amount: rounding correctness -------------------------------------------


def test_matches_previously_hardcoded_example_599_cents():
    # $5.99 purchase from the original demo seed data / existing integration tests.
    result = split_amount(599, DEFAULT_CONFIG)
    assert result == RevenueSplitResult(archive_cents=419, transcriptionist_cents=120, platform_cents=60)
    assert result.total_cents == 599


def test_single_cent_goes_to_the_largest_remainder_share():
    # 1 cent * 70% = 0.007, closest to rounding up of the three -> archive gets it.
    result = split_amount(1, DEFAULT_CONFIG)
    assert result == RevenueSplitResult(archive_cents=1, transcriptionist_cents=0, platform_cents=0)
    assert result.total_cents == 1


@pytest.mark.parametrize("total_cents", [1, 2, 3, 7, 11, 13, 17, 99, 101, 333, 599, 1001, 12_345, 999_999])
def test_split_always_sums_back_to_total_regardless_of_rounding(total_cents):
    result = split_amount(total_cents, DEFAULT_CONFIG)
    assert result.total_cents == total_cents
    assert result.archive_cents >= 0
    assert result.transcriptionist_cents >= 0
    assert result.platform_cents >= 0


def test_naive_independent_rounding_would_have_broken_the_invariant():
    # Demonstrates *why* the largest-remainder method matters: naively rounding
    # each share independently with round(total_cents * percentage) does not
    # always sum back to the total. At 2 cents:
    #   round(2 * 0.70) = round(1.4) = 1
    #   round(2 * 0.20) = round(0.4) = 0
    #   round(2 * 0.10) = round(0.2) = 0
    #   1 + 0 + 0 = 1, not 2 -- a whole cent silently vanishes.
    naive_archive = round(2 * 0.70)
    naive_transcriptionist = round(2 * 0.20)
    naive_platform = round(2 * 0.10)
    assert naive_archive + naive_transcriptionist + naive_platform == 1  # broken: should be 2

    result = split_amount(2, DEFAULT_CONFIG)
    assert result.total_cents == 2  # split_amount does not have this bug


def test_rejects_zero_amount():
    with pytest.raises(ValueError, match="must be positive"):
        split_amount(0, DEFAULT_CONFIG)


def test_rejects_negative_amount():
    with pytest.raises(ValueError, match="must be positive"):
        split_amount(-500, DEFAULT_CONFIG)


# --- configurability ---------------------------------------------------------------


def test_split_honors_a_custom_config_instead_of_the_default():
    custom = RevenueSplitConfig(archive_bps=5000, transcriptionist_bps=3000, platform_bps=2000)
    result = split_amount(1000, custom)
    assert result == RevenueSplitResult(archive_cents=500, transcriptionist_cents=300, platform_cents=200)


def test_split_uses_default_settings_when_no_config_given():
    result = split_amount(1000)
    assert result == RevenueSplitResult(archive_cents=700, transcriptionist_cents=200, platform_cents=100)


def test_extreme_split_all_to_one_party():
    all_archive = RevenueSplitConfig(archive_bps=10_000, transcriptionist_bps=0, platform_bps=0)
    result = split_amount(599, all_archive)
    assert result == RevenueSplitResult(archive_cents=599, transcriptionist_cents=0, platform_cents=0)
