# Student guide

The current source draft has one page for each of the twelve incidents under
[`student/`](student/README.md). The walkthrough and commands are not runtime
validated; follow the README only after a maintainer has completed the host
checks recorded in [`testing.md`](testing.md).

1. Run preflight, up, doctor, and urls. Confirm doctor passes before beginning.
2. Send a healthy request to `/orders`, save its request ID, and find it in
   Kibana. Relate it to the API metrics in Grafana.
3. Start an incident, record the UTC window, and inspect the user-visible symptom.
4. State a hypothesis and compare useful negative controls before inspecting
   pods, endpoints, events, DNS, logs, or metrics.
5. Repair the smallest responsible resource, verify recovery, and reset before
   changing exercises.

Write down impact, first failure time, evidence, root cause, repair, and
recovery. During telemetry outages, use a direct probe to check the application.
Use relative links to the individual exercise pages; keep instructor answers
clearly labeled as spoilers.
