# Hosted customer application

This repository is ready for Streamlit Community Cloud. A submitted application URL must come from a completed deployment; a GitHub URL, localhost address or proposed subdomain is not a deployed tool.

## Deployment configuration

| Field | Value |
| --- | --- |
| Repository | `foglands/datathon` (private) |
| Branch | `architecture-completion-20261115` |
| Main file | `app.py` |
| Python | 3.11 |
| Dependencies | Root `requirements.txt` |
| Audience | Reviewers need working access to the deployed app; repository visibility is separate |

The customer entry point contains no Reference cases navigation. Do not deploy `validation_app.py` as the customer submission. The public-data research path does not require the organizer archive; unsupported archive-dependent evidence remains unavailable.

## Account and secrets

Sign in at [Streamlit Community Cloud](https://share.streamlit.io/), review the service terms, and authorize the private GitHub repository when requested. Select Create app and use the fields above. The account owner must approve any new repository access; this does not require making the repository public.

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
