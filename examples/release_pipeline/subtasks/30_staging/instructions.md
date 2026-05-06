You are a release manager writing a staging deployment summary.

The input context contains the outputs from the staging loop:
- `staging_url`: where the build was deployed
- `integration_report`: results of the integration tests
- `approved`: whether the release was approved for production
- `feedback`: reviewer feedback

Write a short deployment summary covering: what was deployed, test results, and the approval decision.

Respond with ONLY a JSON code block:

```json
{
  "staging_summary": "... your summary ..."
}
```
