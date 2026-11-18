"""Backends turn (system prompt, input) into model text.

Both backends expose the same two methods, so the pipeline does not care which one it has:

    generate(system, user_text, schema=None, image=None) -> str
        schema given: the reply is JSON text, constrained by the schema (extract and classify calls).
        schema None:  the reply is plain text (reply drafts).
        image: optional (bytes, mime_type), for IMAGE_MODE=vision.

Any failure (network, timeout, refusal, bad exit, unreadable output) raises BackendError. The pipeline
turns that into "send to a person". Backends never retry and never repair JSON: retry once is the
pipeline's job (SPEC core rule 3).
"""


class BackendError(Exception):
    """The model could not be reached, timed out, refused, stopped early, or returned unreadable output."""
