from __future__ import annotations

import ast
import io
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

_BUDGET_RE = re.compile(r"\$([\d,]+)")
_ENTITY_SPLIT_RE = re.compile(r"\s*,\s*")


@dataclass
class EntityMatch:
    name: str
    city: str | None
    price: float | None = None
    minimum_nights: int | None = None
    maximum_occupancy: int | None = None
    room_type: str | None = None
    confidence: str = "high"


@dataclass
class CostEstimate:
    total_cost: float
    total_checks: int
    priced_matches: int
    confidence: str


def parse_budget_from_query(query: str) -> int | None:
    match = _BUDGET_RE.search(query or "")
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def parse_reference_information(raw_reference_information: Any) -> list[dict[str, Any]]:
    if raw_reference_information is None:
        return []
    if isinstance(raw_reference_information, list):
        return [item for item in raw_reference_information if isinstance(item, dict)]
    if isinstance(raw_reference_information, str):
        text = raw_reference_information.strip()
        if not text:
            return []
        try:
            value = ast.literal_eval(text)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        except Exception:
            return [{"Description": "Reference information", "Content": text}]
    return []


def _normalize_text(text: str | None) -> str:
    if text is None:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def _to_frame(content: str) -> pd.DataFrame | None:
    if not content or not str(content).strip():
        return None
    try:
        frame = pd.read_fwf(io.StringIO(str(content)))
    except Exception:
        return None
    if frame.empty:
        return None
    return _normalize_frame(frame)


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    for col in frame.columns:
        col_str = str(col).strip()
        if col_str == "Average":
            renamed[col] = "Average"
        elif col_str == "Cost":
            renamed[col] = "Cost"
        elif col_str == "minimum":
            renamed[col] = "minimum"
        elif col_str == "nights":
            renamed[col] = "nights"
        elif col_str == "maximum":
            renamed[col] = "maximum"
        elif col_str == "occupancy":
            renamed[col] = "occupancy"
    if renamed:
        frame = frame.rename(columns=renamed)
    return frame


def _iter_rows_with_context(raw_reference_information: Any):
    for block in parse_reference_information(raw_reference_information):
        description = str(block.get("Description", "")).strip()
        content = str(block.get("Content", "")).strip()
        frame = _to_frame(content)
        if frame is not None:
            yield description, frame


def _split_entity(entity: str) -> tuple[str, str | None]:
    parts = _ENTITY_SPLIT_RE.split(str(entity).strip())
    if len(parts) >= 2:
        return parts[0].strip(), ", ".join(p.strip() for p in parts[1:] if p.strip()) or None
    return str(entity).strip(), None


def _row_text(row: pd.Series) -> str:
    return " ".join(str(value) for value in row.values if pd.notna(value))


def _column_index(row: pd.Series, target: str) -> int | None:
    for idx, col in enumerate(row.index):
        if str(col) == target:
            return idx
    return None


def _combine_with_left_unnamed(row: pd.Series, target: str) -> str:
    idx = _column_index(row, target)
    if idx is None:
        return ""
    parts: list[str] = []
    left = idx - 1
    while left >= 0 and str(row.index[left]).startswith("Unnamed"):
        val = str(row.iloc[left] or "").strip()
        if val:
            parts.insert(0, val)
        left -= 1
    target_val = str(row.iloc[idx] or "").strip()
    if target_val:
        parts.append(target_val)
    return " ".join(parts).strip()


def _row_name(row: pd.Series) -> str:
    if "NAME" in row.index:
        return str(row.get("NAME") or "").strip()
    if "Name" in row.index:
        return _combine_with_left_unnamed(row, "Name") or str(row.get("Name") or "").strip()
    return ""


def _row_city(row: pd.Series) -> str:
    if "city" in row.index:
        city = _combine_with_left_unnamed(row, "city") or str(row.get("city") or "").strip()
        if city:
            return city
    if "City" in row.index:
        city = _combine_with_left_unnamed(row, "City") or str(row.get("City") or "").strip()
        if city:
            return city
    return ""


def _name_match(row_name: str, entity_name: str) -> bool:
    rn = _normalize_text(row_name)
    en = _normalize_text(entity_name)
    if not rn or not en:
        return False
    return rn == en or rn.startswith(en) or en.startswith(rn)


def _name_confidence(row_name: str, entity_name: str) -> str:
    rn = _normalize_text(row_name)
    en = _normalize_text(entity_name)
    if not rn or not en:
        return "low"
    if rn == en:
        return "high"
    if rn.startswith(en) or en.startswith(rn):
        return "medium"
    return "low"


def _city_match(row_city: str, entity_city: str | None) -> bool:
    if not entity_city:
        return True
    rc = _normalize_text(row_city)
    ec = _normalize_text(entity_city)
    if not ec:
        return True
    return ec in rc or rc in ec


def _city_confidence(row_city: str, entity_city: str | None) -> str:
    if not entity_city:
        return "medium"
    rc = _normalize_text(row_city)
    ec = _normalize_text(entity_city)
    if not rc or not ec:
        return "low"
    if rc == ec:
        return "high"
    if ec in rc or rc in ec:
        return "medium"
    return "low"


def _extract_restaurant_price(row: pd.Series) -> float | None:
    if "Cost" in row.index and pd.notna(row["Cost"]):
        try:
            return float(row["Cost"])
        except Exception:
            return None
    if "Average Cost" in row.index and pd.notna(row["Average Cost"]):
        try:
            return float(row["Average Cost"])
        except Exception:
            return None
    return None


def _extract_numbers(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"(?<![A-Za-z])(\d+(?:\.\d+)?)", text)]


def _line_match(content: str, entity_name: str, entity_city: str | None) -> str | None:
    for line in str(content).splitlines():
        if entity_name and entity_name in line and (not entity_city or entity_city in line):
            return line
    return None


def _extract_accommodation_details(
    row: pd.Series,
) -> tuple[float | None, int | None, int | None, str | None]:
    price = None
    min_nights = None
    max_occupancy = None
    room_type = None
    if "price" in row.index and pd.notna(row["price"]):
        try:
            price = float(row["price"])
        except Exception:
            price = None
    if "nights" in row.index and pd.notna(row["nights"]):
        try:
            min_nights = int(float(row["nights"]))
        except Exception:
            min_nights = None
    if "occupancy" in row.index and pd.notna(row["occupancy"]):
        try:
            max_occupancy = int(float(row["occupancy"]))
        except Exception:
            max_occupancy = None
    if "room type" in row.index and pd.notna(row["room type"]):
        room_type = str(row["room type"]).strip()
    elif "room" in row.index and "type" in row.index:
        room_type = f"{str(row.get('room') or '').strip()} {str(row.get('type') or '').strip()}".strip()
    return price, min_nights, max_occupancy, room_type


def find_restaurant_match(raw_reference_information: Any, entity: str) -> EntityMatch | None:
    entity_name, entity_city = _split_entity(entity)
    for block in parse_reference_information(raw_reference_information):
        description = str(block.get("Description", "")).strip()
        if "restaurant" not in description.lower():
            continue
        content = str(block.get("Content", "")).strip()
        line = _line_match(content, entity_name, entity_city)
        if line:
            numbers = _extract_numbers(line)
            price = None
            for value in numbers:
                if value.is_integer() and 1 <= value <= 500:
                    price = value
                    break
            return EntityMatch(name=entity_name, city=entity_city, price=price, confidence="medium")
        frame = _to_frame(content)
        if frame is None:
            continue
        for _, row in frame.iterrows():
            row_name = _row_name(row)
            row_city = _row_city(row)
            if _name_match(row_name, entity_name) and _city_match(row_city, entity_city):
                name_conf = _name_confidence(row_name, entity_name)
                city_conf = _city_confidence(row_city, entity_city)
                return EntityMatch(
                    name=row_name,
                    city=row_city or entity_city,
                    price=_extract_restaurant_price(row),
                    confidence="high" if name_conf == "high" and city_conf in {"high", "medium"} else "medium",
                )
    return None


def find_accommodation_match(raw_reference_information: Any, entity: str) -> EntityMatch | None:
    entity_name, entity_city = _split_entity(entity)
    for block in parse_reference_information(raw_reference_information):
        description = str(block.get("Description", "")).strip()
        if "accommodation" not in description.lower():
            continue
        content = str(block.get("Content", "")).strip()
        line = _line_match(content, entity_name, entity_city)
        if line:
            numbers = _extract_numbers(line)
            price = numbers[0] if numbers else None
            min_nights = int(numbers[1]) if len(numbers) > 1 else None
            return EntityMatch(
                name=entity_name,
                city=entity_city,
                price=price,
                minimum_nights=min_nights,
                maximum_occupancy=None,
                confidence="medium",
            )
        frame = _to_frame(content)
        if frame is None:
            continue
        for _, row in frame.iterrows():
            row_name = _row_name(row)
            row_city = _row_city(row)
            if _name_match(row_name, entity_name) and _city_match(row_city, entity_city):
                price, minimum_nights, maximum_occupancy, room_type = _extract_accommodation_details(row)
                name_conf = _name_confidence(row_name, entity_name)
                city_conf = _city_confidence(row_city, entity_city)
                return EntityMatch(
                    name=row_name,
                    city=row_city or entity_city,
                    price=price,
                    minimum_nights=minimum_nights,
                    maximum_occupancy=maximum_occupancy,
                    room_type=room_type,
                    confidence="high" if name_conf == "high" and city_conf in {"high", "medium"} else "medium",
                )
    return None


def find_flight_match(raw_reference_information: Any, transportation: str) -> EntityMatch | None:
    match = re.search(r"Flight Number:\s*([A-Za-z0-9-]+)", transportation or "", re.IGNORECASE)
    if not match:
        return None
    flight_number = match.group(1).strip()
    for description, frame in _iter_rows_with_context(raw_reference_information):
        if "flight" not in description.lower():
            continue
        if "Flight Number" not in frame.columns:
            continue
        for _, row in frame.iterrows():
            row_flight = str(row.get("Flight Number") or "").strip()
            if row_flight != flight_number:
                continue
            price = None
            if "Price" in row.index and pd.notna(row["Price"]):
                try:
                    price = float(row["Price"])
                except Exception:
                    price = None
            city = " -> ".join(
                part.strip()
                for part in [
                    str(row.get("OriginCityName") or "").strip(),
                    str(row.get("DestCityName") or "").strip(),
                ]
                if part.strip()
            )
            return EntityMatch(name=flight_number, city=city or None, price=price, confidence="high")
    return None


def reference_summary(
    raw_reference_information: Any, query: str, days: int | None, org: str | None, dest: str | None
) -> str:
    blocks = parse_reference_information(raw_reference_information)
    budget = parse_budget_from_query(query)
    descriptions = [str(block.get("Description", "")).strip() for block in blocks if block.get("Description")]

    lines = [
        "SOLE-PLANNING DIGEST",
        f"- Trip frame: {org or 'unknown'} -> {dest or 'unknown'} over {days or 'unknown'} day(s).",
    ]
    if budget is not None:
        lines.append(
            f"- Query-implied budget ceiling: ${budget}. Prefer lower-cost grounded options when choices are ambiguous."
        )
    if descriptions:
        lines.append("- Reference information blocks available:")
        lines.extend(f"  - {desc}" for desc in descriptions[:12])
    lines.append(
        "- Public planning priorities: avoid repeated restaurants, avoid missing transport on travel days,"
        " preserve coherent city sequence, and respect accommodation minimum-night plausibility"
        " when a hotel stays the same across days."
    )
    return "\n".join(lines)


def _collect_restaurant_candidates(
    frame: pd.DataFrame,
    dest: str | None,
) -> list[tuple[str, float]]:
    results: list[tuple[str, float]] = []
    for _, row in frame.iterrows():
        row_name = _row_name(row)
        row_city = _row_city(row)
        price = _extract_restaurant_price(row)
        if not row_name or price is None:
            continue
        if dest and not _city_match(row_city, dest):
            continue
        results.append((f"{row_name}, {row_city}".strip(", "), price))
    return results


def _collect_accommodation_candidates(
    frame: pd.DataFrame,
    dest: str | None,
) -> list[tuple[str, float, int | None, str | None]]:
    results: list[tuple[str, float, int | None, str | None]] = []
    for _, row in frame.iterrows():
        row_name = _row_name(row)
        row_city = _row_city(row)
        price, min_nights, _, room_type = _extract_accommodation_details(row)
        if not row_name or price is None:
            continue
        if dest and not _city_match(row_city, dest):
            continue
        results.append((f"{row_name}, {row_city}".strip(", "), price, min_nights, room_type))
    return results


def _collect_flight_candidates(
    frame: pd.DataFrame,
) -> list[tuple[str, float, str, str]]:
    results: list[tuple[str, float, str, str]] = []
    if "Flight Number" not in frame.columns:
        return results
    for _, row in frame.iterrows():
        row_flight = str(row.get("Flight Number") or "").strip()
        row_price = row.get("Price")
        if not row_flight or pd.isna(row_price):
            continue
        try:
            price = float(row_price)
        except Exception:
            continue
        dep = str(row.get("DepTime") or "").strip()
        arr = str(row.get("ArrTime") or "").strip()
        results.append((row_flight, price, dep, arr))
    return results


def _format_accommodation_line(
    name: str,
    price: float,
    min_nights: int | None,
    room_type: str | None,
) -> str:
    suffix = []
    if room_type:
        suffix.append(room_type)
    if min_nights:
        suffix.append(f"min {min_nights} night(s)")
    suffix_text = f" ({', '.join(suffix)})" if suffix else ""
    return f"  - {name}: ${price:.0f}{suffix_text}"


def grounding_hint_summary(
    raw_reference_information: Any,
    *,
    org: str | None,
    dest: str | None,
    budget: int | None,
) -> str:
    """Build a compact public grounding summary for cheaper candidate selection."""
    restaurant_candidates: list[tuple[str, float]] = []
    accommodation_candidates: list[tuple[str, float, int | None, str | None]] = []
    flight_candidates: list[tuple[str, float, str, str]] = []

    for block in parse_reference_information(raw_reference_information):
        description = str(block.get("Description", "")).strip()
        content = str(block.get("Content", "")).strip()
        frame = _to_frame(content)
        if frame is None:
            continue

        desc_lower = description.lower()
        if "restaurant" in desc_lower:
            restaurant_candidates.extend(_collect_restaurant_candidates(frame, dest))
        elif "accommodation" in desc_lower:
            accommodation_candidates.extend(_collect_accommodation_candidates(frame, dest))
        elif "flight" in desc_lower and org and dest and org.lower() in desc_lower and dest.lower() in desc_lower:
            flight_candidates.extend(_collect_flight_candidates(frame))

    restaurant_candidates = sorted(restaurant_candidates, key=lambda item: item[1])[:5]
    accommodation_candidates = sorted(accommodation_candidates, key=lambda item: item[1])[:5]
    flight_candidates = sorted(flight_candidates, key=lambda item: item[1])[:5]

    lines = ["PUBLIC GROUNDED CANDIDATE HINTS"]
    if budget is not None:
        lines.append(f"- Budget context: ${budget}. Prefer cheaper compatible grounded choices.")
    if flight_candidates:
        lines.append("- Cheaper matching flights:")
        for flight_no, price, dep, arr in flight_candidates:
            lines.append(f"  - {flight_no}: ${price:.0f}, dep {dep}, arr {arr}")
    if restaurant_candidates:
        lines.append("- Cheaper restaurant candidates:")
        for name, price in restaurant_candidates:
            lines.append(f"  - {name}: avg cost ${price:.0f}")
    if accommodation_candidates:
        lines.append("- Cheaper accommodation candidates:")
        for name, price, min_nights, room_type in accommodation_candidates:
            lines.append(_format_accommodation_line(name, price, min_nights, room_type))
    if len(lines) == 1:
        lines.append("- No compact candidate summary available; fall back to the full reference information.")
    return "\n".join(lines)


def estimate_itinerary_cost(
    raw_reference_information: Any,
    plan_rows: list[dict[str, Any]],
    *,
    people_count: int = 1,
) -> CostEstimate:
    total_cost = 0.0
    total_checks = 0
    priced_matches = 0

    for row in plan_rows:
        transport = str(row.get("transportation") or "").strip()
        if transport and transport != "-":
            total_checks += 1
            flight_match = find_flight_match(raw_reference_information, transport)
            if flight_match and flight_match.price is not None:
                priced_matches += 1
                total_cost += flight_match.price * max(people_count, 1)

        for field in ("breakfast", "lunch", "dinner"):
            meal = str(row.get(field) or "").strip()
            if meal and meal != "-":
                total_checks += 1
                restaurant_match = find_restaurant_match(raw_reference_information, meal)
                if restaurant_match and restaurant_match.price is not None:
                    priced_matches += 1
                    total_cost += restaurant_match.price * max(people_count, 1)

        accommodation = str(row.get("accommodation") or "").strip()
        if accommodation and accommodation != "-":
            total_checks += 1
            accommodation_match = find_accommodation_match(raw_reference_information, accommodation)
            if accommodation_match and accommodation_match.price is not None:
                priced_matches += 1
                occupancy = max(accommodation_match.maximum_occupancy or 1, 1)
                rooms_needed = (max(people_count, 1) + occupancy - 1) // occupancy
                total_cost += accommodation_match.price * rooms_needed

    if total_checks == 0:
        confidence = "none"
    else:
        ratio = priced_matches / total_checks
        if ratio >= 0.8:
            confidence = "high"
        elif ratio >= 0.4:
            confidence = "medium"
        else:
            confidence = "low"

    return CostEstimate(
        total_cost=total_cost,
        total_checks=total_checks,
        priced_matches=priced_matches,
        confidence=confidence,
    )
