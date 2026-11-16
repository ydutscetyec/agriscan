# AGRISCAN p9 — what PROMISE changed

Full mapping, with page references and the reasoning for each row, is in the Doc
"AGRISCAN and PROMISE — Technical Mapping". This file is the engineering summary.

PROMISE is a rule-based health-support app. It trains no detection model and reports no
accuracy figure, so most of the original brief (postprocessing, field-level aggregation,
experiment tracking, error analysis, model changes) has no basis in the paper and was
not built. Eleven principles transfer: five are new software, three were already in
AGRISCAN and now have tests, three are wording for the paper.

**YOLO26n is unchanged. The objectives, locale, respondents, 85 percent overall and
0.70 recall criterion, and the minimum-sample rule are unchanged.**

## New

- **Processing versions** (migration 009). Each detection now links to an immutable,
  hashed snapshot of the settings that shaped it: quality-gate limits, palay gate,
  detector, the effective confidence and margin thresholds, and the severity method.
  Identical settings share one row; any change makes a new one. Rows are never updated or
  deleted (database triggers). Shown on the detection page; `GET /processing-versions`.
  Detections written before 009 have none, and may be given one once.
- **Minimised facts to the advice generator.** It now receives condition, severity band
  and growth stage only. No field, owner, coordinates or photograph.
- **`scripts/evaluation_stats.py`** — weighted mean, SD and verbal bands on a four- or
  five-point scale, plus an upper-tailed one-sample t-test against a benchmark. The
  benchmark is never defaulted. Verified against scipy to six decimals. Warns plainly
  below ten respondents. Two different SDs appear in its output and are labelled.
- **`scripts/response_time_test.py`** — times what a user waits on over repeated trials.
  The target is never defaulted and the row counts it ran against are printed.
- **`scripts/inference_time_test.py`** — times the real pipeline stages on image files you
  name, with cold start reported apart. Touches no database. While the detector is the
  stub it marks its own report as not for reporting.

```
python -m scripts.evaluation_stats responses.csv --scale 4 --benchmark 2.51
python -m scripts.response_time_test --user "DEMO Technician" --trials 3 --target-seconds 3.0 --out response_times.md
python -m scripts.inference_time_test --images ./timing_images --trials 3 --model-name yolo26n --out inference_times.md
```

Benchmarks and targets are written into Chapter 3 first, then the scripts are run.

## Tests

Backend 265 passing (was 185). Frontend 15 passing. Build clean.
The inference timing tests were checked by deliberately breaking the tool twice (population
SD instead of sample SD; cold start folded into the warm samples) — each fault failed tests.

## Provenance of this package

Part of the above was left in the project by an interrupted earlier run and was verified
this session before being kept: the processing-version migration, service and wiring, the
evaluation and response-time scripts, and their tests. Their statistics were re-checked
against scipy. `inference_time_test.py` and its tests were written in this session.

## Not done

- The paper text. The revised Word file was not available, so Chapters 1 and 3 are
  unchanged. Four research-method changes wait on group decisions (see the Doc).
- No timing has been measured on real hardware, and no ratings have been collected.
