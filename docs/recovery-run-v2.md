# Recovery run v2: historical record

This experiment stopped before a new production ranker was trained. Its validation retrieval and identity findings, limitations and resource decisions are recorded in [the project journal](project-journal.md) and the `results/recovery-*.json` reports. The historical source and cohort configurations remain in `experiments/recovery-*.json`.

The experimental evidence retriever, query adapters, learned identity matcher and their dedicated runners were retired in the lean cleanup. Their historical implementation can be inspected in Git at commit `87c48ac`; its commands are not supported by the current checkout. Locally prepared source data, graph snapshots and indexes were not deleted. A new experiment must define its own data and temporal evaluation rules before training, and must not treat the inspected old test as untouched.
