# Hosted customer application

The customer application is deployed at [https://alphaforge-datathon.streamlit.app/](https://alphaforge-datathon.streamlit.app/).

Verified on November 16, 2026: Python 3.11.18 build completed, customer homepage loaded, app sharing was public, and an AMD research request retrieved market/FX observations and displayed Python calculations and charts. Cloud Bedrock credentials were not configured; the app correctly returned an evidence-only partial result and no checked personalized conclusion. Full model research and its follow-up/export acceptance remain unverified in the hosted environment. Local shell credentials are not automatically transferred to Streamlit Cloud.

## Deployment configuration

| Field | Value |
| --- | --- |
| Repository | `foglands/datathon` (public) |
| Branch | `architecture-completion-20261115` |
| Main file | `app.py` |
| Python | 3.11 |
| Dependencies | Root `requirements.txt` |
| Audience | Reviewers need working access to the deployed app; repository visibility is separate |

The customer entry point contains no Reference cases navigation. Do not deploy `validation_app.py` as the customer submission. The public-data research path does not require the organizer archive; unsupported archive-dependent evidence remains unavailable.

## Account and secrets

Sign in at [Streamlit Community Cloud](https://share.streamlit.io/), review the service terms, and connect GitHub when requested. Select Create app and use the fields above. The repository owner made this repository public for deployment; private-repository access is not required.

In Advanced settings, select Python 3.11 and enter runtime configuration using [.streamlit/secrets.example.toml](../.streamlit/secrets.example.toml) as the non-secret template. Root-level secrets become environment variables consumed by the existing AWS provider chain. Enter actual AWS credentials directly in the hosting Secrets editor, never in GitHub, source files, screenshots or chat.

Bedrock credentials must be valid and authorized for the configured model. Temporary AWS sessions expire. Hosting the UI does not extend the life of the competition account or its credentials. The project records the competition-account shutdown as November 16, 2026 at 13:59 Montreal time; continued model availability requires a valid authorized AWS environment after that deadline. Do not present a loaded homepage as proof that research works.

## Verify before submission

1. Wait for the deployment to finish and copy the actual assigned `https://...streamlit.app` address.
2. Open the address from a signed-out browser. A private-source deployment may also default to private app access. Set the intended reviewer access separately; keep source-code visibility unchanged.
3. Submit a fictional investment question and check real Bedrock activity, dated market observations, Python results, partial/complete status and report export.
4. Test a follow-up correction. Confirm that no developer navigation appears on the customer page.
5. Add only the verified deployed address to the README, repository website field and submission form.

Do not send reviewer invitations unless specifically requested. If the app is made publicly accessible, its model calls consume the configured AWS account's quota/budget. Public app access and uploading AWS credentials to a hosting provider require the account owner's approval.

## Platform documentation

- [Deploy a repository and choose Python](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [Store runtime secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
- [App visibility and sharing](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app)
