"""Pull NIH RePORTER award records (program officer + study section) for all NIH ICs.

Writes one JSONL file per (fiscal year, administering IC) into raw/ so reruns resume.
Usage: python3 fetch_reporter.py [first_fy] [last_fy]
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

URL = "https://api.reporter.nih.gov/v2/projects/search"
ICS = ["NCI", "NEI", "NHLBI", "NHGRI", "NIA", "NIAAA", "NIAID", "NIAMS", "NIBIB", "NICHD",
       "NIDA", "NIDCD", "NIDCR", "NIDDK", "NIEHS", "NIGMS", "NIMH", "NIMHD", "NINDS", "NINR",
       "NLM", "NCCIH", "NCATS", "FIC", "OD", "CLC"]
FIELDS = ["ApplId", "ProjectNum", "CoreProjectNum", "FiscalYear", "AgencyIcAdmin",
          "ProgramOfficers", "FullStudySection", "ActivityCode", "AwardType", "AwardAmount",
          "ProjectTitle", "ContactPiName", "Organization"]
PAGE = 500
MAX_WINDOW = 15000  # API rejects offset + limit beyond this
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")


def post(criteria, offset, limit, tries=6):
    body = json.dumps({"criteria": criteria, "include_fields": FIELDS,
                       "offset": offset, "limit": limit}).encode()
    for i in range(tries):
        try:
            req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            wait = 5 * (i + 1)
            print(f"  retry {i + 1} after {e!r}; sleeping {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"failed: {criteria} offset={offset}")


def slim(r):
    org = r.get("organization") or {}
    return {
        "appl_id": r.get("appl_id"),
        "project_num": r.get("project_num"),
        "core": r.get("core_project_num"),
        "fy": r.get("fiscal_year"),
        "ic": (r.get("agency_ic_admin") or {}).get("abbreviation"),
        "pos": [p.get("full_name") for p in (r.get("program_officers") or []) if p.get("full_name")],
        "ss": r.get("full_study_section"),
        "act": r.get("activity_code"),
        "type": r.get("award_type"),
        "amt": r.get("award_amount"),
        "title": r.get("project_title"),
        "pi": r.get("contact_pi_name"),
        "org": org.get("org_name"),
    }


def fetch(fy, ic):
    path = os.path.join(OUT, f"{fy}_{ic}.jsonl")
    if os.path.exists(path):
        return
    crit = {"fiscal_years": [fy], "agencies": [ic], "is_agency_admin": True}
    first = post(crit, 0, PAGE)
    total = first["meta"]["total"]
    if total >= MAX_WINDOW:
        raise RuntimeError(f"{fy} {ic}: {total} records exceeds API window; needs finer split")
    rows = [slim(r) for r in first["results"]]
    offset = PAGE
    while offset < total:
        time.sleep(1)
        rows += [slim(r) for r in post(crit, offset, PAGE)["results"]]
        offset += PAGE
    if len(rows) != total:
        print(f"  WARNING {fy} {ic}: got {len(rows)} of {total}", flush=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    os.replace(tmp, path)
    print(f"{fy} {ic}: {len(rows)}", flush=True)
    time.sleep(1)


if __name__ == "__main__":
    first_fy = int(sys.argv[1]) if len(sys.argv) > 1 else 2022
    last_fy = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
    os.makedirs(OUT, exist_ok=True)
    for fy in range(last_fy, first_fy - 1, -1):
        for ic in ICS:
            fetch(fy, ic)
    print("DONE", flush=True)
