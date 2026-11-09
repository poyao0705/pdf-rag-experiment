"""Generate the Gateway cloud instructions from the frontend's library spec."""

import json
from pathlib import Path

FORM_RULES = (
    "A Form's submit button must send the entries to you: its action must be @ToAssistant(...), "
    'e.g. Button("Plan my trip", @ToAssistant("Plan my trip"), "primary"), never @Set or another '
    "local-only action. Don't put what the form produces (a summary, plan or itinerary) in the "
    "same reply, hidden or not; write it in your next reply from the values the user submitted.\n"
    "When a field should only appear for a certain answer (e.g. a company name only for "
    "Business trips), bind the deciding field to a $variable with its value argument, e.g. "
    'RadioGroup("tripType", items, "Leisure", { required: true }, $tripType), and show the '
    'field with $tripType == "Business" ? companyField : null.'
)


def cloud_system_prompt(spec_path: Path) -> str:
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        if (
            not isinstance(spec, dict)
            or not isinstance(spec.get("schema"), dict)
            or not spec["schema"]
            or not isinstance(spec.get("root"), str)
            or not spec["root"].strip()
        ):
            raise ValueError("Invalid library spec")
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f"Missing or invalid OpenUI spec at {spec_path}. "
            "From web/, run: vp run generate"
        ) from exc

    library = {
        key: spec[key]
        for key in ("schema", "root", "componentGroups", "id")
        if spec.get(key) is not None
    }
    return (
        "]]>openui:config\n" + json.dumps({"chatLibrary": library}) + "\n" + FORM_RULES
    )
