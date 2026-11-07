# Submission status and remaining checks

- Code, pinned dependencies, the offline batch interface, CI configuration and sample data are present.
- `design.pdf` is the required three-page design document; `design.html` is its editable source.
- `resources/results/README.md` and linked JSON reports contain measured results and reproduction commands. Metrics are incomplete future-authorship proxies, not human accuracy.
- `ai-use-statement.md` identifies AI assistance and an error; the submitter must review and add any omitted contributions.
- The search page includes a graph assistant sharing the search session, with three validated tools, visible applied memory, shortlist/reject decisions and deletion. General Gemini/local-model conversation remains separate; graph actions use explicit commands.
- A browser test covers search, all three graph tools, a shortlist decision, applied memory and deletion. Run the full suite against the final submission.
- Compose configuration validates, but a clean image build/start remains unverified because this machine's Docker Desktop daemon fails. Prepared local dependencies passed the backend clean-copy check; this does not substitute for a clean Compose run.
- The assignment requests a 3–5 minute demonstration video. It is intentionally omitted at the project owner's instruction and should be disclosed if submitted without one.
- Complete independent relevance review if time permits; no human accuracy is claimed. No accounts or tenant isolation are implemented.
- Before submitting: run the README commands from a clean copy; verify `docker compose up --build`, the required unseen-slice batch command and current UI flow; review the design and AI-use statement; fill in the submitter's name, actual hours and omissions in the email. Never commit local `data/`, keys, dependencies or build output.
