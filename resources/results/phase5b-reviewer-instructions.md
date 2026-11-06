# Reviewer instructions: ScholarGraph relevance pilot

You are assessing whether the supplied historical publications support the researcher's expertise for the stated query. You are not predicting who later coauthored a paper, judging fame or popularity, or evaluating the ranking system. Use only the evidence shown, through the **inclusive cutoff year** in that row. The packet contains up to three publications and may be incomplete.

Start with **P01–P10**. Each candidate has two rows: one reviewer fills slot 1 and a different reviewer fills slot 2. You may filter your assigned slot, but do not change the query ID, person ID, reviewer slot, query, cutoff, name or evidence. Put your identifier in `reviewer`, your assessment in `grade_0_to_3`, and explanatory comments in `notes`. The Q queries are a separate production benchmark with cutoff 2024; P queries use cutoff 2023. Do not mix the populations.

| Entry in `grade_0_to_3` | Meaning |
|---|---|
| `0` | Evidence is sufficiently clear and shows no relevant expertise. |
| `1` | Evidence is adjacent or weak. |
| `2` | Evidence supports direct expertise in the query topic. |
| `3` | Evidence supports strong, sustained expertise through multiple relevant works. |
| `U` | Unable to judge; explain why in `notes`. |
| blank | Not yet reviewed. |

Use **U** for unclear author identity, a missing or broken record, incomplete evidence that cannot support a judgment, or insufficient detail to tell whether a related title is actually relevant. A single directly relevant publication may justify 2 but is normally insufficient to establish the sustained evidence needed for 3. Interdisciplinary work can qualify if its contribution is directly relevant; shared words alone do not establish expertise. Use the DBLP paper ID in each evidence packet to identify a record, but do not use work published after the cutoff or external rank/proxy metadata.

Review independently. Do not discuss a candidate with the other reviewer until both have submitted their grades. Disagreement is not an error to erase: the coordinator records both reviews, reviews the disagreement list, and may seek a separate adjudication. The evaluator reports the median provisionally; if an issue requires resolution, return a corrected reviewed copy with an audit trail. Do not replace uncertainty with 0.
