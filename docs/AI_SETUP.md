# AI provider setup (optional)

InvoiceOps works fully without AI (`AI_PROVIDER=none`). When AI is enabled and a job has AI assistance checked, the model is
called for **every document**, not only when the rules fail. The AI never replaces a confident rule-based value (confidence
`>= 0.7`), and **any value it returns must appear in the document text, otherwise it is discarded**. It also cross-checks
line-item and total arithmetic. AI-supplied fields are tagged "AI" in the review workspace, disagreements are flagged, and a
document where the AI agreed with the rules is marked "AI checked this document".

Two providers are supported:

| Provider | Where it runs | Privacy | Speed |
| --- | --- | --- | --- |
| **Ollama** | On this PC | Text never leaves the machine | Depends on the local model/CPU |
| **Groq** | Groq cloud API | Text leaves the machine after per-job authorisation | Very fast |

Choose the provider in **Settings → AI provider** (or set `AI_PROVIDER` in `.env`).

## Ollama (local, private)
1. Install Ollama for Windows from ollama.com.
2. In Command Prompt: `ollama pull qwen2.5-coder:1.5b-fast` (any instruction-following model works; set `OLLAMA_MODEL`).
3. Choose **Ollama** in settings and press **Save & test**. No data leaves your PC and no per-job consent is needed.

## Groq (cloud, fast)
1. Create an API key at console.groq.com.
2. Put it in `.env` (never commit this file):
   `GROQ_API_KEY=gsk_...`
3. Optionally set `GROQ_MODEL`. The default is `openai/gpt-oss-20b` (fast). `openai/gpt-oss-120b` is stronger but slower.
   The model must be available to your key.
4. Restart the server, choose **Groq** in settings, and press **Save & test**.
5. When creating a job, tick **Use AI assistance** and then **Allow sending document text to Groq**. Existing jobs show an
   **Authorise Groq** button in the job header.

The API key is read from the environment only; it is never stored in the database or returned by the settings API.

## Checking the setup
`POST /api/settings/ai/test` checks connectivity without sending document content. For Ollama it lists installed models; for
Groq it calls the models endpoint and reports whether `GROQ_MODEL` is available to your key.

## Privacy, consent and costs
Ollama runs on the same machine, so there is no per-job consent step and no provider billing.

Groq is a cloud provider: each job needs explicit operator authorisation before any document text is sent. Consent is recorded
per job and can be revoked with `DELETE /api/jobs/{id}/consent`. Groq usage may be billed by Groq according to your account.
