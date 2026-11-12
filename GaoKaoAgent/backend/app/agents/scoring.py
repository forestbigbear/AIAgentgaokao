from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True)
class ScoringPolicy:
    rank: int = 50
    interest: int = 15
    city: int = 10
    risk: int = 10
    data_quality: int = 15
    reach_ratio: float = 0.9
    safe_ratio: float = 1.2

    @classmethod
    def from_settings(cls, settings: Settings) -> "ScoringPolicy":
        return cls(
            rank=settings.match_rank_weight,
            interest=settings.match_interest_weight,
            city=settings.match_city_weight,
            risk=settings.match_risk_weight,
            data_quality=settings.match_data_weight,
            reach_ratio=settings.match_reach_ratio,
            safe_ratio=settings.match_safe_ratio,
        )

    def tier(self, ratio: float) -> str:
        if ratio < self.reach_ratio:
            return "冲"
        if ratio < self.safe_ratio:
            return "稳"
        return "保"

    def weights(self) -> dict[str, int]:
        return {"rank": self.rank, "interest": self.interest, "city": self.city,
                "risk": self.risk, "data_quality": self.data_quality}
