# SNIPEWINS — fast debug loop

This is the short version. Three steps. No screenshots, no copy-paste of terminal text.

## The fast loop

**1) Start the app with logging on.**

In a terminal opened in the `Python Coding` folder, run:

```
python run_app.py
```

This launches Streamlit exactly like before, but it also saves everything the terminal prints into a file called `last_scan.log` in this folder. Leave this terminal running.

**2) Run a scan in Streamlit.**

Click your scan button in the browser like normal. Wait for it to finish.

**3) Get the diagnosis.**

Open a SECOND terminal in the same folder and run:

```
python diag.py --write
```

This reads `last_scan.log`, finds the funnel/observability lines we've built up across all the patches, and prints a clean summary. The `--write` flag also drops the same summary into `latest_diag.md`.

You now have two ways to feed it to me:

- **Fastest:** in your next message to me, just say "read latest_diag.md" — I'll read the file directly with my Read tool. No copy-paste.
- **Slower but works anywhere:** copy the printed summary and paste it into your message.

Both are way faster than screenshotting the terminal.

## What this gives you

Instead of a wall of terminal text, the diagnosis is one block that names:
- how many auctions were fetched, normalized, and displayed
- which stage of the funnel killed the most rows (`engine death funnel`)
- top drop reasons (`reason_counts`)
- a few sample rows showing the exact title and reason at each drop point
- a "biggest stage cliffs" hint at the bottom that flags any stage where ≥30% of rows died

That's enough information to write the next surgical patch without screenshots.

## When to bring ChatGPT into the loop

You don't need ChatGPT for the patch loop itself anymore. Use it for:

- **Strategy:** "we've fixed seven bottlenecks; which order should we tackle the next three?"
- **Patch review:** "Claude just changed `_es_get_valuation_readiness` — can you confirm it didn't loosen any filter?"
- **Plain-English explanations** of what a patch did, before you accept it.

Skip ChatGPT for "translate this screenshot into a Claude prompt." That's the round-trip tax we're cutting.

## Common questions

**Q: I already have a way I run streamlit. Do I have to use `run_app.py`?**

No. `run_app.py` is just a convenience that captures the log for you. If you prefer your existing command, that's fine — just redirect the output yourself. On Windows PowerShell:

```
streamlit run streamlit_app.py 2>&1 | Tee-Object -FilePath last_scan.log
```

On Mac/Linux:

```
streamlit run streamlit_app.py 2>&1 | tee last_scan.log
```

`diag.py` doesn't care which one you use. It just reads whatever `.log` file is most recent.

**Q: Can `diag.py` read a different log file?**

Yes. Pass the filename:

```
python diag.py mylog.log
```

**Q: What if the scan never finishes / the terminal is stuck?**

`last_scan.log` is being written line-by-line in real time. Even if the scan hangs, you can run `python diag.py` in another terminal to see how far it got. Press Ctrl-C in the first terminal to stop streamlit when you're done.

**Q: Does this affect anything in the app code?**

No. `run_app.py` and `diag.py` are external tooling. They don't import or modify any of your engine, valuation, or UI code. They only wrap streamlit and read log files.
