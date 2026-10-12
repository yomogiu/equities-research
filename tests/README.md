# Offline test suites

Run the relevant suite while developing, then all suites before merging:

```sh
python3 scripts/run_tests.py active_pipeline
python3 scripts/run_tests.py legacy_compatibility
python3 scripts/run_tests.py other_workflows
python3 scripts/run_tests.py all
python3 scripts/run_tests.py all --list
```

The default is `active_pipeline`. Add `-v` for individual test names. These
commands use the existing unittest tests; they do not launch live report models.
Ordinary `python3 -m unittest discover -s tests -v` remains supported.

`tests/suites.json` assigns every test module to exactly one group:

- **active_pipeline:** current source/evidence processing, authenticated model
  transport, factual and editorial review, formatting and safe phase advancement.
  Shared modules may include older-schema cases needed by current helpers.
- **legacy_compatibility:** earlier experiment/native/mixed pipelines, bounded
  correction editions and recovery adapters preserving frozen historical runs.
- **other_workflows:** calendar, collection, freshness and workspace workflows.

These are module-level partitions, not proof that a change only affects one group.
If a shared contract changes, run the relevant compatibility tests too. The full
suite remains the pre-merge check; no historical coverage has been deleted.

The runner rejects unclassified files, stale entries, duplicate assignments,
import errors and duplicate discovered test IDs. Add new test modules to the
manifest. Import reusable test classes through their module (for example,
`import test_example as fixtures`), rather than placing an imported TestCase in
a test module's globals: unittest otherwise discovers that class again. Keep
intentional subclass tests when they exercise distinct fixture behavior.

The discovery cleanup preserves all 984 normalized public test IDs while removing
112 redundant executions, including the same fixture imported through both
`test_*` and `tests.test_*` module names. Counts can change as new tests are added;
use `--list` for current counts.
