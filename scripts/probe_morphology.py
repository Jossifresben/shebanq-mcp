"""Probe the live BHSA database for the Plan M morphology features.

Prints one PROBE line per query: name, count or ERROR. Run in CI where Emdros +
the DB exist. The output pins the catalogue content (which feature names are
populated, which enum values attest, how nametype is stored) and the counts used
in the primer and fixtures. NOT a pytest test; temporary (removed in Task M4).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from shebanq_mcp.runner import run_query  # noqa: E402

DB = sys.argv[1] if len(sys.argv) > 1 else "data/bhsa.sqlite3"

PROBES = [
    # -- which suffix-feature name is populated? (both typecheck; count decides)
    ("prs_ps_p3",        "SELECT ALL OBJECTS WHERE [word prs_ps=p3] GO"),
    ("suffix_person_p3", "SELECT ALL OBJECTS WHERE [word suffix_person=p3] GO"),
    # -- enum value attestation
    ("prs_ps_p1",   "SELECT ALL OBJECTS WHERE [word prs_ps=p1] GO"),
    ("prs_ps_p2",   "SELECT ALL OBJECTS WHERE [word prs_ps=p2] GO"),
    ("prs_ps_unknown", "SELECT ALL OBJECTS WHERE [word prs_ps=unknown] GO"),
    ("prs_gn_m",    "SELECT ALL OBJECTS WHERE [word prs_gn=m] GO"),
    ("prs_gn_f",    "SELECT ALL OBJECTS WHERE [word prs_gn=f] GO"),
    ("prs_nu_sg",   "SELECT ALL OBJECTS WHERE [word prs_nu=sg] GO"),
    ("prs_nu_du",   "SELECT ALL OBJECTS WHERE [word prs_nu=du] GO"),
    ("prs_nu_pl",   "SELECT ALL OBJECTS WHERE [word prs_nu=pl] GO"),
    ("pdp_advb",    "SELECT ALL OBJECTS WHERE [word pdp=advb] GO"),
    ("pdp_NA",      "SELECT ALL OBJECTS WHERE [word pdp=NA] GO"),
    ("pdp_unknown", "SELECT ALL OBJECTS WHERE [word pdp=unknown] GO"),
    # -- nametype storage: exact vs regex (string feature, QUOTED)
    ("nametype_topo_eq",    "SELECT ALL OBJECTS WHERE [word nametype='topo'] GO"),
    ("nametype_topo_regex", "SELECT ALL OBJECTS WHERE [word nametype ~ 'topo'] GO"),
    ("nametype_pers_eq",    "SELECT ALL OBJECTS WHERE [word nametype='pers'] GO"),
    ("nametype_pers_regex", "SELECT ALL OBJECTS WHERE [word nametype ~ 'pers'] GO"),
    # -- ls on word and on lex
    ("ls_card_word", "SELECT ALL OBJECTS WHERE [word ls=card] GO"),
    ("ls_gntl_word", "SELECT ALL OBJECTS WHERE [word ls=gntl] GO"),
    ("ls_card_lex",  "SELECT ALL OBJECTS WHERE [lex ls=card] GO"),
    # -- the counts the primer / fixtures will pin
    ("ex_3ms_suffix",
     "SELECT ALL OBJECTS WHERE [word prs_ps=p3 AND prs_gn=m AND prs_nu=sg] GO"),
    ("ex_noun_as_adverb",
     "SELECT ALL OBJECTS WHERE [word sp=subs AND pdp=advb] GO"),
    ("ex_cardinals", "SELECT ALL OBJECTS WHERE [word ls=card] GO"),
    ("ex_topo_names_regex",
     "SELECT ALL OBJECTS WHERE [word sp=nmpr AND nametype ~ 'topo'] GO"),
    ("ex_topo_names_eq",
     "SELECT ALL OBJECTS WHERE [word sp=nmpr AND nametype='topo'] GO"),
]


def main() -> None:
    for name, mql in PROBES:
        try:
            count = run_query(mql, DB, limit=1).count
            print(f"PROBE {name} count={count}", flush=True)
        except Exception as exc:  # noqa: BLE001 - a failed probe is itself data
            print(f"PROBE {name} ERROR={exc}", flush=True)


if __name__ == "__main__":
    main()
