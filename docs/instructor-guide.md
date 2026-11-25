# Instructor guide

Suggested 90-minute session: 15 minutes for the healthy request path, 15 for Exercise 01, 15 for 03, 20 for 05, 15 for 06, and 10 for reports. Pre-pull images and run doctor on student hosts ahead of class.

Write a solution per exercise with expected Grafana panels and Kibana queries, exact diagnosis and repair commands, expected negative controls, known timing differences, and reset verification. Include common incorrect hypotheses and the observation that rules each out. Mark sample logs as synthetic and timestamp examples in UTC.

For the blind capstone, start the exercise from an instructor terminal without
sharing that terminal:

```sh
make lab-start LAB=12
make lab-status
```

Read `started_at` from `make lab-status` and give students a UTC window that
covers the start and current investigation period, plus only the symptom from
the [capstone brief](student/blind-worker-capstone.md). Do not show the command,
status output, or scenario ID. The student should identify the drained worker
from cluster evidence, explain the impact, and propose a scoped uncordon. Reveal
the verification/reset commands only when the repair discussion is complete.
The answer key can live publicly under docs/instructor/ with a spoiler label.

| Grading criterion | Points |
| --- | ---: |
| Describes impact and incident window | 2 |
| Collects evidence from two relevant sources | 3 |
| Identifies and explains the root cause | 2 |
| Applies a scoped repair | 2 |
| Verifies sustained recovery | 1 |
