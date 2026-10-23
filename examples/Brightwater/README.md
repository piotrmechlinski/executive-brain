# Brightwater: an example vault

The vault of Alex Morgan, the COO of Brightwater Logistics, three weeks after the vault was set up. Brightwater, its
people and its numbers are made up.

## Try it

You need git and Python 3, nothing else: no account and no packages. Get the code, then run the tools on this vault
from the repository's top folder:

```
git clone https://github.com/piotrmechlinski/executive-brain
cd executive-brain
VAULT_TODAY=2026-10-22 python3 tools/vault.py check --vault examples/Brightwater
VAULT_TODAY=2026-10-22 python3 tools/vault.py review --vault examples/Brightwater
VAULT_TODAY=2026-10-22 python3 tools/build_map.py --vault examples/Brightwater
```

- `check` passes, and notes one milestone that is overdue.
- `review` lists what is overdue, what is due within 14 days, and the open points without a date or a mitigation.
- `build_map.py` writes `examples/Brightwater/build/Project map.html`. Open it in a browser.

`VAULT_TODAY` sets the day the tools take as today: 22 October 2026, the day this vault was last worked on. Without it
the review counts from your own date. In Windows PowerShell, run `$env:VAULT_TODAY = "2026-10-22"` first and leave it
out of the commands.

## What to look at

- `Home.md` and the project cards in `Projects/`: their lower parts are written by the tools from the registers.
- `Knowledge/`: the registers, every row with its project, date and source.
- `Meetings/`: a setup interview, a debrief, a recorded meeting and a weekly review.
- `Sources/`: a transcript, and a document with its summary.
- `Private/`: a confidential point; its code name is kept out of everything else by the check.
- `Archive/Projects/`: a project that is done.
