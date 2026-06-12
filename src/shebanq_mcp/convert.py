"""Direction detection + dispatch for the bidirectional converter.

One tiny pure function shared by the web /api/convert route and usable
anywhere a caller has 'some query text' in an unknown language. MQL is
recognized by its mandatory SELECT opener; anything else is treated as a
TF template (and the TF validator does the complaining if it is not)."""
import re

from .feature_reference import FeatureReference
from .mql_to_tf import mql_to_tf
from .tf_to_mql import ConversionError, tf_to_mql

_MQL_OPENER = re.compile(r"(?i)^select\b")


def detect_and_convert(text: str, ref: FeatureReference) -> dict:
    t = text.strip()
    if not t:
        return {"error": "input is empty"}
    if _MQL_OPENER.match(t):
        try:
            r = mql_to_tf(t, ref)
            return {"direction": "mql_to_tf", "output": r.text,
                    "notes": r.notes}
        except ConversionError as exc:
            return {"direction": "mql_to_tf", "error": str(exc)}
    try:
        return {"direction": "tf_to_mql", "output": tf_to_mql(t, ref),
                "notes": []}
    except ConversionError as exc:
        return {"direction": "tf_to_mql", "error": str(exc)}
