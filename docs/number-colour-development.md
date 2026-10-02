# Card number colour — rendered cache implementation

This fork changes the existing white card-number glyphs in the selected card's FrontFace render cache to black. It leaves the number value, artwork pixels, Wallet database, and other cache metadata unchanged. The earlier local database preparation code remains a development utility; it is no longer the Number Colour UI.

## Use

1. Connect and unlock the iPhone; detect the card in a current scan.
2. Stop scanning and force-close Wallet on the iPhone.
3. Under the card, choose **Number Colour → Black**. No file selection or upload is required.
4. Reopen Wallet and check the result.

The app saves a device/card-specific original cache and operation snapshots in `~/Library/Application Support/AirCard/NumberRenderBackups/`. **Restore Number** restores the preimage only while the current cache still matches this patch, so it will not overwrite newer artwork.

## Limits

This is a render-cache customization. iOS can restore its original text colour when it regenerates the cache, after an issuer update, artwork flashing, or system changes. Reapply Black after opening and closing the card to generate a new cache.

Only the supported checksummed PKPassFrontFaceImageSet cache, with a lower-left white four-dot/four-digit number layout, is changed. The native helper checks the component layout and recognizes the suffix with Vision against the backed-up pass metadata. Unknown formats, checksum failures, unexpected layouts, and suffix mismatches stop before a cache write. The artwork and the original card number are not rewritten.

## Validation

The captured cache was patched locally and compared pixel by pixel: only the glyph pixels changed; no pixels outside the number zone changed. The modified cache was written and read back exactly, and the user confirmed that the displayed number was black. That validates this tested cache and phone, not every Wallet card layout or persistence after cache regeneration.

Automated tests cover the checksum envelope, archive metadata preservation, invalid output/format rejection, failed-write rollback, readback failure rollback, suffix mismatch, and refusal to restore over newer artwork. Other artwork and database preparation checks remain in the test suite.

Customer cache files, metadata backups, device identifiers, logs, and screenshots are never included in this repository or release.
