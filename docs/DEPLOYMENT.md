# Hosted customer application

The customer application is deployed at [https://alphaforge-datathon.streamlit.app/](https://alphaforge-datathon.streamlit.app/).

The November 16, 2026 verification recorded a public customer homepage, market and FX data retrieval, Python calculations and charts. The hosted app returned checked evidence because the deployment had no usable Bedrock credentials during that check. A full hosted model run requires valid credentials in Streamlit Cloud Secrets. See the [verification record](../submission/final-verification.md).

## Deployment configuration

| Field | Value |
| --- | --- |
| Repository | `foglands/datathon` (public) |
| Branch | `architecture-completion-20261115` |
| Main file | `app.py` |
| Python | 3.11 |
| Dependencies | Root `requirements.txt` |
| Audience | Reviewers need working access to the deployed app; repository visibility is separate |

Streamlit Community Cloud follows changes pushed to the deployment branch. Publish application updates to that branch and keep GitHub's default branch `agent-optimization` synchronized. Use `app.py` for the customer deployment and `validation_app.py` for local developer validation. The hosted customer workflow can use public prices and FX without the organizer archive.

## Account and secrets

Sign in at [Streamlit Community Cloud](https://share.streamlit.io/), review the service terms, and connect GitHub when requested. Select Create app and use the fields above. The repository owner made this repository public for deployment; private-repository access is not required.

In Advanced settings, select Python 3.11 and enter runtime configuration using [.streamlit/secrets.example.toml](../.streamlit/secrets.example.toml) as the non-secret template. Root-level secrets become environment variables consumed by the existing AWS provider chain. Enter actual AWS credentials directly in the hosting Secrets editor, never in GitHub, source files, screenshots or chat.

Bedrock credentials must be valid and authorized for the configured model. Temporary AWS sessions expire. Hosting the UI does not extend the life of the competition account or its credentials. The project records the competition-account shutdown as November 16, 2026 at 13:59 Montreal time; continued model availability requires a valid authorized AWS environment after that deadline. Do not present a loaded homepage as proof that research works.

## Verify a release

1. Open the [hosted app](https://alphaforge-datathon.streamlit.app/) after Streamlit updates.
2. Check the three example questions. **Apply question** should fill editable text before **Analyze my question** starts the run.
3. Submit a fictional question and check the observed service status, data dates, calculations and report export. Record any unavailable Bedrock access separately from the UI and data checks.
4. Test a follow-up correction when the full reasoning workflow is available.

Do not send reviewer invitations unless specifically requested. If the app is made publicly accessible, its model calls consume the configured AWS account's quota/budget. Public app access and uploading AWS credentials to a hosting provider require the account owner's approval.

## Platform documentation

- [Deploy a repository and choose Python](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [Store runtime secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
- [App visibility and sharing](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app)
