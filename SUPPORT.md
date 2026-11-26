# Getting help

1. **Run the self-check**: `docker compose exec echo-tunes echo-tunes doctor`. It tests each
   link in the chain (configuration, YouTube, your public address) and says which one fails.
2. **Read [Troubleshooting](docs/TROUBLESHOOTING.md)**: most problems (Alexa can't reach the
   server, wrong skill ID, the Echo's language, YouTube blocking a cloud server) are covered.
3. **Still stuck?** [Open an issue](https://github.com/denzilrdz/echo-tunes/issues/new/choose)
   with the `doctor` output and the log lines around the problem.

Security problems: please don't open an issue; see [SECURITY.md](SECURITY.md).
