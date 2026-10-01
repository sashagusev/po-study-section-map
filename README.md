# PO–Study Section Map

Which study sections the grants managed by each NIH program officer were reviewed in, built from public [NIH RePORTER](https://reporter.nih.gov/) award records.

**Site:** https://sashagusev.github.io/po-study-section-map/

Browse by program officer to see the study sections their portfolio came through, or by study section to see which program officers manage its grants. Each pairing drills down to the individual grants, linked to their RePORTER pages.

Related NIH tools that start from your own abstract: [RePORTER Matchmaker](https://reporter.nih.gov/matchmaker) finds similar funded projects with their program officers and study sections, and CSR's [Assisted Referral Tool](https://public.csr.nih.gov/ForApplicants/ArtHome) recommends study sections for your application text.

## Data

- `out/po_study_section_map.csv`: one row per (program officer, study section), with grant counts, the share of the PO's portfolio, and the share of the section's grants.
- `out/po_summary.csv`: one row per program officer, listing their top standing study sections, special emphasis panels and activity codes.

## Method

- Pulls every NIH-administered award record for the chosen fiscal years from the RePORTER v2 API, including the program official and study section.
- Collapses records to distinct grants by core project number. A grant counts once for each program officer and study section listed on any of its records, so a renewal reviewed in a different section counts in both.
- Non-competing years carry the study section of the competing review that produced them.
- Groups special emphasis panels by reviewing office and branch code. For example, `ZRG1-CTH` is a CSR panel from the CTH branch, and `ZCA1-SRB` is an NCI panel.
- Excludes three kinds of records:
  - records with no listed program officer, mostly components of multi-project awards, contracts and intramural projects;
  - records with no study section;
  - `NSS` records, which were not separately peer reviewed (R00 phases, R37 extensions, R33 transitions).
- Matches program officers on first and last name. A PO counts as active if they are named on an award record in either of the last two fiscal years.

## Rebuild

```bash
python3 fetch_reporter.py 2022 2026   # downloads into raw/, resumable, ~1 request/second
python3 build_mapping.py              # writes out/*.csv, site/ and docs/
```

The build skips any fiscal year whose download is incomplete.

Not affiliated with or endorsed by NIH.
