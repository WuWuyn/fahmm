# Optional minutes provider setup

Open **Settings** to create a provider profile with a name, Base URL, Model ID, timeout, and optional API key. You can keep several profiles, change one, remove its stored key, or delete the profile. API keys are saved through Windows Credential Manager; they are not written to the profile JSON or meeting folders. If protected storage is unavailable, key saving fails instead of falling back to a plaintext file.

Use an `https://` Base URL for a remote provider. Plain `http://` is accepted only for an explicitly configured localhost or loopback endpoint. TLS certificate checks stay enabled, and redirects are not followed for content-bearing requests. A local loopback endpoint still requires the meeting's Cloud permitted mode and a confirmation for each send.

Provider minutes generation is optional and may cost money. Recording, importing, local transcription, and offline extractive drafts need no provider profile or API key. Before a provider request, fahmm shows the destination and the transcript/prompt content to be sent. The request is made only after you confirm it. A failed request leaves local audio, transcripts, and earlier minutes available for retry.
