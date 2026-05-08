import json
from pathlib import Path

from app.services.geocoding import LocalGeocoder
from app.services.ingestion.classifier import classify
from app.services.intelligence import source_family


CASES_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "stage15_eval_cases.json"


def run_eval(cases_path: Path | None = None) -> dict:
    path = cases_path or CASES_PATH
    cases = json.loads(path.read_text(encoding="utf-8"))
    geocoder = LocalGeocoder()
    report = {
        "total": len(cases),
        "correct_event_type": 0,
        "correct_exception_category": 0,
        "false_event_creation": 0,
        "by_group": {},
    }
    for case in cases:
        result = classify(
            title=case["title"],
            body=case.get("body") or "",
            categories=case.get("categories") or [],
            concepts=case.get("concepts") or [],
            min_score=0.55,
        )
        geocode = geocoder.resolve(text=f"{case['title']} {case.get('body') or ''}")
        family = source_family(case.get("source_type"), case.get("trust_tier"))
        predicted_event_type = result.event_type if result else None
        predicted_exception = _predict_exception(case, result, geocode, family)

        if predicted_event_type == case.get("expected_event_type"):
            report["correct_event_type"] += 1
        if predicted_exception == case.get("expected_exception_category"):
            report["correct_exception_category"] += 1
        if case.get("should_create_event") is False and _would_create_event(result, geocode, family):
            report["false_event_creation"] += 1
        group = case.get("group", "unknown")
        report["by_group"][group] = report["by_group"].get(group, 0) + 1
    return report


def _predict_exception(case: dict, result, geocode, family: str) -> str | None:
    if family == "context" or case.get("status") == "context":
        return "context_only"
    if result is None:
        return "classified_out"
    if geocode is None:
        return "bad_location"
    if family == "social":
        return "social_only"
    if case.get("duplicate"):
        return "possible_duplicate"
    return None


def _would_create_event(result, geocode, family: str) -> bool:
    return bool(result and geocode and family in {"official", "acled"})


if __name__ == "__main__":
    print(json.dumps(run_eval(), indent=2, sort_keys=True))
