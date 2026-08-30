from dataclasses import dataclass

BASIS_POINTS_TOTAL = 10_000  # 100.00%, in basis points (1% = 100 bps)

_PARTIES = ("archive", "transcriptionist", "platform")


@dataclass(frozen=True)
class RevenueSplitConfig:
    """
    Split percentages expressed as integer basis points rather than floats, so the
    configured shares themselves carry no floating-point representation error
    (0.70 has no exact binary representation; 7000 bps does).
    """

    archive_bps: int
    transcriptionist_bps: int
    platform_bps: int

    def __post_init__(self) -> None:
        for name, value in zip(_PARTIES, self._values(), strict=True):
            if value < 0:
                raise ValueError(f"{name}_bps must be >= 0, got {value}")

        total = sum(self._values())
        if total != BASIS_POINTS_TOTAL:
            raise ValueError(
                f"Revenue split shares must sum to 100% ({BASIS_POINTS_TOTAL} bps), "
                f"got {total} bps (archive={self.archive_bps}, "
                f"transcriptionist={self.transcriptionist_bps}, platform={self.platform_bps})"
            )

    def _values(self) -> tuple[int, int, int]:
        return (self.archive_bps, self.transcriptionist_bps, self.platform_bps)

    @classmethod
    def from_percentages(
        cls, archive: float, transcriptionist: float, platform: float
    ) -> "RevenueSplitConfig":
        """Convenience constructor for human-friendly percentages, e.g. (70, 20, 10)."""
        return cls(
            archive_bps=round(archive * 100),
            transcriptionist_bps=round(transcriptionist * 100),
            platform_bps=round(platform * 100),
        )

    @classmethod
    def from_settings(cls) -> "RevenueSplitConfig":
        from app.config import settings

        return cls(
            archive_bps=settings.archive_share_bps,
            transcriptionist_bps=settings.transcriptionist_share_bps,
            platform_bps=settings.platform_share_bps,
        )


@dataclass(frozen=True)
class RevenueSplitResult:
    archive_cents: int
    transcriptionist_cents: int
    platform_cents: int

    @property
    def total_cents(self) -> int:
        return self.archive_cents + self.transcriptionist_cents + self.platform_cents


def split_amount(total_cents: int, config: RevenueSplitConfig | None = None) -> RevenueSplitResult:
    """
    Split total_cents across archive/transcriptionist/platform.

    Uses integer basis-point math throughout (never floats — total_cents * bps is
    exact) and the largest-remainder (Hamilton's) method to distribute whatever
    pennies are left after flooring each share: whoever was closest to rounding up
    gets first claim on a leftover cent. This guarantees
    archive_cents + transcriptionist_cents + platform_cents == total_cents exactly,
    for every input, not just the ones that happen to divide evenly.
    """
    if total_cents <= 0:
        raise ValueError(f"total_cents must be positive, got {total_cents}")

    config = config or RevenueSplitConfig.from_settings()
    shares = {
        "archive": config.archive_bps,
        "transcriptionist": config.transcriptionist_bps,
        "platform": config.platform_bps,
    }

    floor_amounts: dict[str, int] = {}
    remainders: dict[str, int] = {}
    for name, bps in shares.items():
        raw = total_cents * bps
        floor_amounts[name], remainders[name] = divmod(raw, BASIS_POINTS_TOTAL)

    leftover_cents = total_cents - sum(floor_amounts.values())
    # Ties (equal remainders) are broken by a fixed priority order so results are
    # deterministic and reproducible given the same inputs.
    order = sorted(_PARTIES, key=lambda name: (-remainders[name], _PARTIES.index(name)))
    for i in range(leftover_cents):
        floor_amounts[order[i % len(order)]] += 1

    return RevenueSplitResult(
        archive_cents=floor_amounts["archive"],
        transcriptionist_cents=floor_amounts["transcriptionist"],
        platform_cents=floor_amounts["platform"],
    )
