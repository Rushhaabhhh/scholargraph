# AI tools statement

This project was developed with OpenAI Codex as a coding and analysis assistant. It helped inspect the assignment, draft and modify code and documentation, run tests, prepare data and model experiments, investigate low evaluation scores, and verify submission materials. The project owner set the scope, questioned the validity of the results and requested that the work be made reproducible.

One significant error was an earlier suggestion that a 50–70k-paper slice would probably preserve quality before checking historical author coverage. On the same inspected validation cohort, nine venue families covered 464 of 686 future-author instances (67.64%); the preselected 18-family history covered 534 (77.84%). The team corrected the approach by measuring coverage and recording that these are future-authorship proxies, not human relevance labels. A later rebuild check also showed that a venue/year-only reconstruction did not reproduce the original source selection; the pipeline now checks a frozen paper-ID list and content digest.

AI-generated code, tests, documentation and outputs require human review. The reported evaluation uses future-authorship proxy labels; the project does not claim that human relevance has been evaluated.
