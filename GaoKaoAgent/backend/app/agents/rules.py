import re
from statistics import median

from app.agents.scoring import ScoringPolicy


SUBJECTS = ("物理", "化学", "生物", "历史", "政治", "地理", "技术")
TIER_QUOTAS = {
    "conservative": {"冲": 1, "稳": 2, "保": 3},
    "balanced": {"冲": 2, "稳": 2, "保": 2},
    "aggressive": {"冲": 3, "稳": 2, "保": 1},
}


def subjects_in(text: str) -> set[str]:
    return {subject for subject in SUBJECTS if subject in text}


def meets_subjects(chosen: set[str], requirement: str | None) -> bool:
    if not requirement:
        return False  # Unknown requirements cannot establish eligibility.
    requirement = requirement.strip()
    if requirement in {"不限", "无选科要求", "不提科目要求"}:
        return True
    groups = [group.strip() for group in re.split(r"[、,，;；+及和]", requirement) if group.strip()]
    if not groups:
        return False
    for group in groups:
        required = subjects_in(group)
        if not required:
            return False
        if "或" in group or "/" in group:
            if not chosen & required:
                return False
        elif not required <= chosen:
            return False
    return True


def evaluate_candidates(profile: dict, candidates: list[dict], policy: ScoringPolicy
                        ) -> tuple[list[dict], list[str], list[dict]]:
    matches: list[dict] = []
    gaps: list[str] = []
    unranked: dict[tuple[int, int], dict] = {}
    chosen = set(profile["subjects"])
    seen: set[tuple[int, int]] = set()
    for row in candidates:
        key = (row["university_id"], row["major_id"])
        if key in seen:
            continue
        if row["plan_province"] != profile["province"] or row["plan_year"] != profile["exam_year"]:
            continue
        if row["university_year"] != profile["exam_year"] or row["major_year"] != profile["exam_year"]:
            gaps.append(f"{row['university_name']}/{row['major_name']} 的院校或专业资料年份不匹配")
            continue
        if not (meets_subjects(chosen, row["plan_subjects"])
                and meets_subjects(chosen, row["major_subjects"])):
            gaps.append(f"{row['university_name']}/{row['major_name']} 不满足选科要求或要求未明确")
            continue
        history = [record for record in row["history"] if record["min_rank_no"] and record["min_rank_no"] > 0][:3]
        if not history:
            unranked[key] = {
                "university_id": row["university_id"], "major_id": row["major_id"],
                "university_name": row["university_name"], "major_name": row["major_name"],
                "plan_year": row["plan_year"], "plan_source": row["plan_source"],
                "reason": "缺少可用历史最低位次，未纳入正常推荐",
            }
            continue
        seen.add(key)
        unranked.pop(key, None)
        reference_rank = float(median(record["min_rank_no"] for record in history))
        ratio = reference_rank / profile["rank_no"]
        tier = policy.tier(ratio)
        interest_hits = [interest for interest in profile["interests"] if
            interest in (row["major_name"] + (row["category"] or ""))
        ]
        city_hit = row["city"] in profile["target_cities"]
        newest = history[0]
        freshness = profile["exam_year"] - newest["exam_year"]
        sources = [row["plan_source"], row["university_source"],
                   row["major_source"], *(record["source_name"] for record in history)]
        simulated = any("模拟" in (source or "") for source in sources)
        quality_factor = 1.0 if freshness == 1 else 0.7 if freshness <= 3 else 0.4
        if not all(source and source.strip() for source in sources):
            quality_factor *= 0.5
        if simulated:
            quality_factor = min(quality_factor, 0.25)
        preference_factor = {
            "conservative": {"冲": 0, "稳": 0.5, "保": 1},
            "balanced": {"冲": 0.5, "稳": 1, "保": 0.5},
            "aggressive": {"冲": 1, "稳": 0.5, "保": 0},
        }[profile["risk_preference"]][tier]
        breakdown = {
            "rank": round(policy.rank * max(0, min(1, ratio - 0.5)), 2),
            "interest": policy.interest if interest_hits else 0,
            "city": policy.city if city_hit else 0,
            "risk": round(policy.risk * preference_factor, 2),
            "data_quality": round(policy.data_quality * quality_factor, 2),
        }
        score = round(sum(breakdown.values()), 2)
        rank_values = [record["min_rank_no"] for record in history]
        spread = round((max(rank_values) - min(rank_values)) / reference_rank, 3)
        matches.append({
            "university_id": row["university_id"], "major_id": row["major_id"],
            "university_name": row["university_name"], "major_name": row["major_name"],
            "city": row["city"], "tier": tier, "match_score": score,
            "rank_ratio": ratio, "plan_id": row["plan_id"],
            "plan_year": row["plan_year"], "plan_source": row["plan_source"],
            "plan_url": row["plan_url"], "plan_updated_at": row["plan_updated_at"],
            "plan_subjects": row["plan_subjects"], "major_subjects": row["major_subjects"],
            "history_id": newest["id"], "history_year": newest["exam_year"],
            "history_min_rank": newest["min_rank_no"],
            "history_reference_rank": reference_rank, "history_spread": spread,
            "history_records": [
                {"id": record["id"], "exam_year": record["exam_year"],
                 "min_rank_no": record["min_rank_no"], "source_name": record["source_name"],
                 "source_url": record["source_url"], "updated_at": record["updated_at"]}
                for record in history
            ],
            "history_source": newest["source_name"], "history_url": newest["source_url"],
            "history_updated_at": newest["updated_at"],
            "simulated": simulated,
            "interest_hits": interest_hits, "city_hit": city_hit,
            "score_weights": policy.weights(), "score_breakdown": breakdown,
        })
    missing = [item for key, item in unranked.items() if key not in seen]
    gaps.extend(f"{item['university_name']}/{item['major_name']} 缺少可用历史最低位次，未纳入推荐"
                for item in missing)
    return sorted(matches, key=lambda item: item["match_score"], reverse=True), list(dict.fromkeys(gaps)), missing


def build_recommendations(profile: dict, matches: list[dict]) -> list[dict]:
    quotas = TIER_QUOTAS[profile["risk_preference"]]
    results: list[dict] = []
    for tier in ("冲", "稳", "保"):
        group = [item for item in matches if item["tier"] == tier]
        for item in group[:quotas[tier]]:
            evidence = {
                "plan_id": item["plan_id"], "plan_year": item["plan_year"],
                "plan_source": item["plan_source"], "plan_url": item["plan_url"],
                "plan_updated_at": item["plan_updated_at"],
                "history_id": item["history_id"], "history_year": item["history_year"],
                "history_min_rank": item["history_min_rank"],
                "history_reference_rank": item["history_reference_rank"],
                "history_spread": item["history_spread"],
                "history_records": item["history_records"],
                "history_source": item["history_source"], "history_url": item["history_url"],
                "history_updated_at": item["history_updated_at"],
                "rank_ratio": item["rank_ratio"], "score_weights": item["score_weights"],
                "score_breakdown": item["score_breakdown"],
                "subject_requirements": [item["plan_subjects"], item["major_subjects"]],
                "simulated": item["simulated"],
            }
            risk = "unknown" if item["simulated"] else "high" if tier == "冲" else "medium" if tier == "稳" else "low"
            note = "历史位次仅供参考；招生条件和计划可能变化。"
            if len(item["history_records"]) == 1:
                note += "仅有一年可用历史位次。"
            if profile["exam_year"] - item["history_year"] > 2:
                note += "历史数据年份较旧。"
            if item["history_spread"] > 0.25:
                note += "历年最低位次波动较大。"
            if item["simulated"]:
                note += "当前为模拟数据，不能用于实际填报。"
            results.append({
                "university_id": item["university_id"], "major_id": item["major_id"],
                "university_name": item["university_name"], "major_name": item["major_name"],
                "tier": tier, "match_score": item["match_score"],
                "reason_text": (
                    f"近 {len(item['history_records'])} 年可用历史最低位次的中位数 "
                    f"{item['history_reference_rank']:g} 与考生位次 "
                    f"{profile['rank_no']} 的比值为 {item['rank_ratio']:.3f}；"
                    f"选科条件满足，专业兴趣{'匹配' if item['interest_hits'] else '未匹配'}，"
                    f"城市偏好{'匹配' if item['city_hit'] else '未匹配'}；"
                    f"位次 {item['score_breakdown']['rank']} 分、"
                    f"兴趣 {item['score_breakdown']['interest']} 分、"
                    f"城市 {item['score_breakdown']['city']} 分、"
                    f"风险偏好 {item['score_breakdown']['risk']} 分、"
                    f"数据质量 {item['score_breakdown']['data_quality']} 分，"
                    f"总分 {item['match_score']}，"
                    f"归入“{tier}”梯度。评分不是录取概率。"
                ),
                "evidence": evidence, "risk_level": risk, "risk_notes": note,
            })
    return results


def assess_risks(profile: dict, recommendations: list[dict], matches: list[dict],
                 data_gaps: list[str], adjustment_count: int,
                 max_adjustments: int, history_years: int,
                 policy: ScoringPolicy) -> dict:
    issues = list(data_gaps)
    tiers = {tier: sum(item["tier"] == tier for item in recommendations)
             for tier in ("冲", "稳", "保")}
    missing_tiers = [tier for tier, count in tiers.items() if count == 0]
    if missing_tiers:
        issues.append("志愿梯度缺少：" + "、".join(missing_tiers))
    chosen = set(profile["subjects"])
    for item in recommendations:
        if any(not meets_subjects(chosen, value)
               for value in item["evidence"]["subject_requirements"]):
            issues.append(f"{item['university_name']}/{item['major_name']} 存在选科冲突")
        if item["evidence"]["plan_year"] != profile["exam_year"]:
            issues.append(f"{item['university_name']}/{item['major_name']} 招生计划年份不匹配")
        if len(item["evidence"]["history_records"]) == 1:
            issues.append(f"{item['university_name']}/{item['major_name']} 仅有一年历史位次")
        if policy.tier(item["evidence"]["rank_ratio"]) != item["tier"]:
            issues.append(f"{item['university_name']}/{item['major_name']} 梯度与历史位次不一致")
        if profile["exam_year"] - item["evidence"]["history_year"] > 2:
            issues.append(f"{item['university_name']}/{item['major_name']} 历史位次较旧")
        if item["evidence"]["history_spread"] > 0.25:
            issues.append(f"{item['university_name']}/{item['major_name']} 历年位次波动较大")
        if item["evidence"]["simulated"]:
            issues.append(f"{item['university_name']}/{item['major_name']} 使用模拟数据")
    if profile["risk_preference"] == "conservative" and tiers["保"] < TIER_QUOTAS["conservative"]["保"]:
        issues.append("保守偏好下保档数量不足")
    if profile["risk_preference"] == "aggressive" and tiers["冲"] < TIER_QUOTAS["aggressive"]["冲"]:
        issues.append("积极偏好下冲档数量不足")
    if not recommendations:
        issues.append("无可用推荐方案；请补充适用年份的招生和历史位次数据")
    # Widen history only when excluded candidates may gain a usable record.
    needs_adjustment = bool(
        missing_tiers and matches and adjustment_count < max_adjustments
        and history_years < 6
        and any("缺少可用历史最低位次" in gap for gap in data_gaps)
    )
    overall = "high" if missing_tiers or not recommendations else "medium" if issues else "low"
    return {
        "overall_risk": overall, "issues": list(dict.fromkeys(issues)),
        "tier_counts": tiers, "needs_adjustment": needs_adjustment,
        "suggestions": [
            "核对省级考试机构与院校官网最新招生要求、计划和录取数据。",
            "当前数据如标记为模拟，仅用于演示，不能作为实际填报依据。",
        ],
        "disclaimer": "本系统仅提供志愿决策辅助，不保证录取结果。",
    }
