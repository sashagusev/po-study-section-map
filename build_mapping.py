"""Aggregate raw RePORTER records into program officer <-> study section mappings.

Unit of counting: a distinct grant (core project number). A grant counts once per
(program officer, study section) pair no matter how many fiscal-year records it has.

Outputs:
  out/po_study_section_map.csv   long table, one row per (PO, study section)
  out/po_summary.csv             one row per PO with top study sections
  site/data.json                 compact index embedded in the page
  site/grants/<IC>.json          grant lists for POs whose primary IC is <IC>
  docs/                          standalone copy of the site for GitHub Pages
"""
import collections
import csv
import datetime
import glob
import json
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
NEW_TYPES = {"1", "2"}  # new and competing renewal awards

# Two-letter IC codes embedded in SEP codes such as ZCA1 or ZRG1
IC2 = {"CA": "NCI", "EY": "NEI", "HL": "NHLBI", "HG": "NHGRI", "AG": "NIA", "AA": "NIAAA",
       "AI": "NIAID", "AR": "NIAMS", "EB": "NIBIB", "HD": "NICHD", "DA": "NIDA", "DC": "NIDCD",
       "DE": "NIDCR", "DK": "NIDDK", "ES": "NIEHS", "GM": "NIGMS", "MH": "NIMH", "MD": "NIMHD",
       "NS": "NINDS", "NR": "NINR", "LM": "NLM", "AT": "NCCIH", "TR": "NCATS", "TW": "FIC",
       "OD": "OD", "RG": "CSR", "RR": "OD", "RM": "OD", "OD1": "OD"}


def norm_person(full):
    parts = full.split()
    if not parts:
        return None, None
    key = f"{parts[0]} {parts[-1]}".upper()
    pretty = " ".join(p.capitalize() if len(p) > 1 else p.upper() for p in parts)
    pretty = re.sub(r"(?<=[-'])(\w)", lambda m: m.group(1).upper(), pretty)  # Smith-Jones, O'Neil
    pretty = re.sub(r"\bMc(\w)", lambda m: "Mc" + m.group(1).upper(), pretty)
    return key, pretty


def study_section(ss):
    """Return (key, label, kind, reviewer) or None. kind: 'S' standing, 'P' special emphasis panel."""
    if not ss or not ss.get("srg_code"):
        return None
    srg = ss["srg_code"].strip().upper()
    if srg == "NSS":  # no study section: R00 phases, R37 extensions, R33 transitions
        return None
    name = (ss.get("name") or "").strip()
    if srg.startswith("Z"):
        sra = (ss.get("sra_designator_code") or "").strip().upper()
        key = f"{srg}-{sra}" if sra else srg
        reviewer = IC2.get(srg[1:3], srg[1:3])
        return key, f"{reviewer} special emphasis panels ({srg} {sra})".replace(" )", ")"), "P", reviewer
    m = re.search(r"\[([^\]]+)\]\s*$", name)
    key = m.group(1).strip().upper() if m else srg
    label = re.sub(r"\s*\[[^\]]*\]\s*$", "", name) or key
    label = re.sub(r"\s+Study Section\b", "", label).strip()
    return key, label, "S", ""


def main():
    files = sorted(glob.glob(os.path.join(HERE, "raw", "*.jsonl")))
    # Skip fiscal years still being downloaded (fewer IC files than a complete year)
    per_fy = collections.Counter(int(os.path.basename(f)[:4]) for f in files)
    fys = sorted(fy for fy, n in per_fy.items() if n == max(per_fy.values()))
    files = [f for f in files if int(os.path.basename(f)[:4]) in fys]
    po_names = collections.defaultdict(collections.Counter)  # key -> display variants
    ss_info = {}  # key -> (fy, label, kind, reviewer); keep label from latest FY
    grants = {}  # (core, po_key, ss_key) -> dict
    po_ic = collections.defaultdict(collections.Counter)
    po_act = collections.defaultdict(collections.Counter)
    n_records = 0
    for f in files:
        for line in open(f):
            r = json.loads(line)
            n_records += 1
            s = study_section(r["ss"])
            if not s or not r["pos"] or not r["core"]:
                continue
            ss_key, label, kind, reviewer = s
            if ss_key not in ss_info or r["fy"] >= ss_info[ss_key][0]:
                ss_info[ss_key] = (r["fy"], label, kind, reviewer)
            for full in r["pos"]:
                pk, pretty = norm_person(full)
                if not pk:
                    continue
                po_names[pk][pretty] += 1
                g = grants.setdefault((r["core"], pk, ss_key), {
                    "core": r["core"], "po": pk, "ss": ss_key, "ics": collections.Counter(),
                    "fy": 0, "first_fy": 9999, "new": False, "act": r["act"], "appl": None,
                    "title": None, "pi": None, "org": None, "num": None})
                g["ics"][r["ic"]] += 1
                g["new"] |= r["type"] in NEW_TYPES
                g["first_fy"] = min(g["first_fy"], r["fy"])
                if r["fy"] >= g["fy"]:
                    g.update(fy=r["fy"], appl=r["appl_id"], title=r["title"], pi=r["pi"],
                             org=r["org"], num=r["project_num"], act=r["act"])
    # one IC/activity tally per distinct grant per PO
    seen = set()
    for g in grants.values():
        if (g["core"], g["po"]) in seen:
            continue
        seen.add((g["core"], g["po"]))
        po_ic[g["po"]][g["ics"].most_common(1)[0][0]] += 1
        po_act[g["po"]][g["act"]] += 1

    pair = collections.defaultdict(lambda: {"n": 0, "new": 0, "last": 0})
    po_cores = collections.defaultdict(set)
    po_last = collections.Counter()
    ss_cores = collections.defaultdict(set)
    for g in grants.values():
        p = pair[(g["po"], g["ss"])]
        p["n"] += 1
        p["new"] += g["new"]
        p["last"] = max(p["last"], g["fy"])
        po_cores[g["po"]].add(g["core"])
        po_last[g["po"]] = max(po_last[g["po"]], g["fy"])
        ss_cores[g["ss"]].add(g["core"])

    po_keys = sorted(po_cores, key=lambda k: (-len(po_cores[k]), k))
    po_idx = {k: i for i, k in enumerate(po_keys)}
    ss_keys = sorted(ss_cores, key=lambda k: (-len(ss_cores[k]), k))
    ss_idx = {k: i for i, k in enumerate(ss_keys)}
    po_primary = {k: po_ic[k].most_common(1)[0][0] for k in po_keys}
    po_display = {k: po_names[k].most_common(1)[0][0] for k in po_keys}

    by_po = collections.defaultdict(list)
    for (pk, sk), p in pair.items():
        by_po[pk].append((sk, p))

    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "site", "grants"), exist_ok=True)

    with open(os.path.join(HERE, "out", "po_study_section_map.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["program_officer", "po_primary_ic", "po_total_grants", "po_last_fy",
                    "study_section_code", "study_section_name", "type", "grants",
                    "share_of_po_grants", "new_or_renewal_awards", "last_fy",
                    "study_section_total_grants", "share_of_study_section_grants"])
        for pk in po_keys:
            tot = len(po_cores[pk])
            for sk, p in sorted(by_po[pk], key=lambda x: -x[1]["n"]):
                _, label, kind, _ = ss_info[sk]
                w.writerow([po_display[pk], po_primary[pk], tot, po_last[pk], sk, label,
                            "standing" if kind == "S" else "special emphasis panel", p["n"],
                            round(p["n"] / tot, 3), p["new"], p["last"], len(ss_cores[sk]),
                            round(p["n"] / len(ss_cores[sk]), 3)])

    with open(os.path.join(HERE, "out", "po_summary.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["program_officer", "primary_ic", "total_grants", "last_fy",
                    "top_standing_study_sections", "top_special_emphasis_panels", "activity_codes"])
        for pk in po_keys:
            tot = len(po_cores[pk])
            rows = sorted(by_po[pk], key=lambda x: -x[1]["n"])
            fmt = lambda kind: "; ".join([f"{sk} ({p['n']}, {p['n'] / tot:.0%})"
                                          for sk, p in rows if ss_info[sk][2] == kind][:5])
            w.writerow([po_display[pk], po_primary[pk], tot, po_last[pk], fmt("S"), fmt("P"),
                        "; ".join(f"{a} ({n})" for a, n in po_act[pk].most_common(6))])

    data = {
        "meta": {"fy_first": fys[0], "fy_last": fys[-1], "records": n_records,
                 "grants": len({g["core"] for g in grants.values()}),
                 "pos": len(po_keys), "sections": len(ss_keys),
                 "pulled": datetime.datetime.fromtimestamp(
                     max(os.path.getmtime(f) for f in files)).strftime("%b %-d, %Y")},
        # [key, label, kind, reviewer, total grants]
        "ss": [[k, ss_info[k][1], ss_info[k][2], ss_info[k][3], len(ss_cores[k])] for k in ss_keys],
        # [name, primary IC, total grants, last FY, [[ssIdx, n, new, last], ...], [[act, n], ...]]
        "po": [[po_display[k], po_primary[k], len(po_cores[k]), po_last[k],
                [[ss_idx[sk], p["n"], p["new"], p["last"]]
                 for sk, p in sorted(by_po[k], key=lambda x: -x[1]["n"])],
                [[a, n] for a, n in po_act[k].most_common(6)]] for k in po_keys],
    }
    with open(os.path.join(HERE, "site", "data.json"), "w") as fh:
        json.dump(data, fh, separators=(",", ":"))

    shards = collections.defaultdict(list)
    for g in sorted(grants.values(), key=lambda g: (-g["fy"], g["core"])):
        shards[po_primary[g["po"]]].append(
            [po_idx[g["po"]], ss_idx[g["ss"]], g["num"], g["appl"], g["fy"], g["first_fy"],
             int(g["new"]), g["title"], (g["pi"] or "").strip().rstrip(","), g["org"]])
    for ic, rows in shards.items():
        with open(os.path.join(HERE, "site", "grants", f"{ic}.json"), "w") as fh:
            json.dump(rows, fh, separators=(",", ":"))

    page = open(os.path.join(HERE, "page_template.html")).read()
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    page = page.replace("__DATA__", blob)
    with open(os.path.join(HERE, "site", "index.html"), "w") as fh:
        fh.write(page)

    # Standalone copy for GitHub Pages: the template is a head fragment (title, fonts, style)
    # followed by body content, so wrap it in a full document.
    split = page.index("</style>") + len("</style>")
    docs = os.path.join(HERE, "docs")
    shutil.rmtree(os.path.join(docs, "grants"), ignore_errors=True)
    shutil.copytree(os.path.join(HERE, "site", "grants"), os.path.join(docs, "grants"))
    with open(os.path.join(docs, "index.html"), "w") as fh:
        fh.write('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                 '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                 f'{page[:split]}\n</head>\n<body>\n{page[split:]}\n</body>\n</html>\n')
    open(os.path.join(docs, ".nojekyll"), "w").close()

    print(json.dumps(data["meta"]), "pairs", len(pair))


if __name__ == "__main__":
    main()
