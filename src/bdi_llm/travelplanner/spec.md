# TravelPlanner Output Spec

TravelPlanner is a non-PDDL benchmark. The planner must output a structured day-by-day itinerary that matches the official evaluation format.

## Required daily fields
Each day record must contain all of the following keys:
- `day`
- `current_city`
- `transportation`
- `breakfast`
- `attraction`
- `lunch`
- `dinner`
- `accommodation`

## Formatting rules
- `current_city`
  - Use either `City` or `from A to B`
  - For travel days, prefer `from Origin to Destination`
- `transportation`
  - If a flight is used, prefer: `Flight Number: F1234567, from A to B, Departure Time: HH:MM, Arrival Time: HH:MM`
  - If local movement is not material, use `-`
  - Do not append extra commentary outside the transportation description
- `breakfast`, `lunch`, `dinner`, `accommodation`
  - Prefer `Name, City`
  - If the field is unnecessary, use `-`
  - Do not append prices, review summaries, check-in explanations, or narrative notes
- `attraction`
  - Single attraction: `Name, City`
  - Multiple attractions: `Name, City;Other Name, City;`
  - Keep the trailing `;` when listing multiple attractions
- Missing optional information must use `-`, not natural-language placeholders

## Coverage rules
- Every day from `1..days` must be present
- For the final padded placeholder days, use the repository placeholder city string and `-` for all other fields
- If `current_city` is not a travel transition day, it must be a single city name
- If `current_city` contains `from A to B`, transportation must not be `-`
- For non-travel city days, meals should not be omitted unless the official benchmark permits it

## Canonical style example
```json
{
  "day": 1,
  "current_city": "from Washington to Myrtle Beach",
  "transportation": "Flight Number: F3927581, from Washington to Myrtle Beach, Departure Time: 11:03, Arrival Time: 13:31",
  "breakfast": "-",
  "attraction": "SkyWheel Myrtle Beach, Myrtle Beach",
  "lunch": "Catfish Charlie's, Myrtle Beach",
  "dinner": "d' Curry House, Myrtle Beach",
  "accommodation": "Adorable Prospect Heights 1 Bedroom, Myrtle Beach"
}
```

## Repair policy
- Preserve already-valid days when possible
- Only rewrite fields or days implicated by evaluator feedback
- Prefer official-style canonical strings over conversational prose
