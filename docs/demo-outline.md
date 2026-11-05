# Suggested 3–5 minute demonstration

**Historical prototype:** The static UI shown in the existing recording has been retired. Update this outline and recording after building the new frontend.

1. Start the app with `docker compose up --build` and open `http://localhost:8000`. Explain that the initial graph is the included 200-paper DBLP sample.
2. Search for “graph neural networks hardware acceleration”. Show a ranked result, its score, expandable source papers, years and collaborators, and the publication profile.
3. Shortlist a result, ask the assistant “show shortlist”, and point out the tool call and memory applied. Clear memory and verify the count changes.
4. Run `./run --data resources/examples/sample.xml --queries resources/examples/queries.txt --out /tmp/hiresense-demo.json` and show the resulting evidence-backed JSON.
5. Explain the temporal train/validation/test boundaries, the locally trained ranker, final metrics and baselines from `resources/results/lean-final-v1.json`. State that future authorship is a weak proxy and that missing history limits recall.
6. Briefly describe the remaining limitations: narrow venue selection, incomplete relevance labels, modest ranking scores, and no measured 50-million-paper/200-QPS deployment.

An automated visual walkthrough is provided in `demo.mp4`; its narration is synthesized and explicitly identifies itself as such. Review it before submission. You can use this outline to record your own explanation instead; this outline itself is not a recording.
