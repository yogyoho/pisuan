# pisuan-cli

Pisuan command line client.

First-stage scope:

- remote management through `~/.pisuan/config.toml`
- browser login
- API Key import through `--api-key`
- `whoami`, `status`, and `logout`
- server discovery and compatibility check for Pisuan `>=0.7.1`
- `pisuan chat` for a temporary local browser chat with streamed Agent output; `/state` reads thread state and `/approve` resumes a pending tool approval
- `pisuan agent list` and `pisuan agent show <slug>` for inspecting agents visible to the logged-in user
- `pisuan kb upload` for knowledge base file uploads
- `pisuan agent eval` for running existing Langfuse dataset experiments with a logged-in remote
