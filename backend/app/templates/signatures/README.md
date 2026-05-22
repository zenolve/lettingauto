# Pre-baked signatures

Drop a transparent-background PNG of a Palace Gate signatory here. The filename
(without extension) becomes the anchor marker that the document body should
reference.

## Naming convention

| File | Anchor in document body | Caption (configured in `services/pre_signatures.py`) |
|---|---|---|
| `pg_sig1.png` | `/pg_sig1/` | "Signed: Lesley Smith, Director, Palace Gate Lettings — <today>" |
| `pg_sig2.png` | `/pg_sig2/` | "Signed: Palace Gate Lettings — <today>" |
| `<custom>.png` | `/<custom>/` | (no caption unless registered in `SIGNATURE_METADATA`) |

## How to use

1. **Save the signature** as a PNG, ideally ~480×120 px with transparent
   background, ~50 KB. The renderer scales it to 160×60 by default.
2. **Drop it in this directory** under the chosen filename.
3. **Reference the anchor** anywhere in your library document HTML:

   ```html
   <p>Yours sincerely,</p>
   <p>/pg_sig1/</p>
   ```

4. **Send the document for signature** as normal. The PDF generation pipeline
   substitutes the marker for an `<img>` data-URI before DocuSign ever sees
   the file, so the recipient receives a PDF with PG already counter-signed
   and only sees their own `/sig1/` / `/sig2/` markers as signature fields.

## Adding a caption

Edit `backend/app/services/pre_signatures.py` and add an entry to
`SIGNATURE_METADATA`:

```python
"my_new_sig": SignatureMeta(
    signatory_name="Jane Doe",
    signatory_role="Property Manager, Palace Gate Lettings",
    width_px=160,
    height_px=60,
),
```

## Privacy note

These PNGs are gitignored by default — they contain a real handwritten
signature and should not be committed to the repo. Each deployment installs
its own.
