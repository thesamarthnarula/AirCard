# Card number colour development fork

This build prepares a local Wallet database copy. It does **not** change the number colour on a stock iPhone through AirCard's current AirTraffic transport.

Choose **Number Colour (Database) → Prepare Black Update…** below a verified card. Select a consistent local database snapshot and a new output file. The original is unchanged. The updater changes only the selected PASS row's FOREGROUND_COLOR; it preserves PRIMARY_ACCOUNT_SUFFIX, LABEL_COLOR, all other columns, all other cards, and all other tables. Unknown schemas/encodings, duplicate matches, and triggers which change unrelated data are rejected. SQLite integrity is checked before and after preparation.

Command:

```sh
python3 aircard_backend.py --prepare-database-number-colour SOURCE.sqlite OUTPUT.sqlite CARD_ID black
```

## Device application remains unimplemented

A safe live implementation needs an on-device SQLite connection and transaction, with a consistent backup, exact card matching, and readback before claiming success. AirTraffic moves/replaces files; it cannot acquire SQLite locks or coordinate with passd. Closing Wallet does not stop its database service. Replacing the main database while that service or its WAL remains active is not a transaction and can lose unrelated changes. This fork therefore does not upload the prepared file to the phone.

The former pass.json-only experimental controls did not change the payment-card overlay on the tested phone. Their backend is retained for restoring prior experiments, but is no longer exposed as a working number-colour control.

Tests use synthetic databases, never customer Wallet data. Runtime fixtures, backups, device identifiers, logs, and screenshots must not be committed or published.
