# Fuzzing

Coverage-guided fuzz targets ([Atheris](https://github.com/google/atheris)) for the code that
reads untrusted input: stream links, `Range` headers, Amazon certificate URLs, Alexa's playback
tokens and stored player state. They complement the Hypothesis property tests in `tests/`.

CI runs each target for a few minutes every week and on changes to that code
(`.github/workflows/fuzz.yml`). Atheris has Linux wheels only, so run them on Linux:

```bash
uv sync --group fuzz
uv run python fuzz/fuzz_tokens.py -max_total_time=60
```

A crash prints the input that caused it; add it as a regular test before fixing.
