"""Standard unit-of-measure codes (Sprint 2 Phase 1.5 — pre-POS master data).

`StandardUnitCode` is a curated subset of the UN/CEFACT Recommendation 20
"Codes for Units of Measure Used in International Trade" list — the same
code set required by the Egyptian Tax Authority (ETA) e-invoice/e-receipt
`unitType` field. This is metadata ONLY in this batch: no ETA API call, no
enforcement, no data migration on existing units.

Every value below is a real, verified Rec 20 code (not invented) — codes and
labels are useless for future e-invoice compliance if they are wrong, so
this list favors a smaller, correct set over padding to a round number. The
enum is a `TextChoices` (plain Python, zero DB rows, zero joins) rather than
a table: `Unit.standard_code` stores the code string directly.

`Unit.name` (free text, e.g. "كرتونة") stays the primary, required label —
this enum only powers the optional `Unit.standard_code` field. Adding a new
code later is a one-line enum change plus an additive migration; it never
requires touching existing `Unit` rows.
"""

from __future__ import annotations

from django.db import models


class StandardUnitCode(models.TextChoices):
    # ── Count ─────────────────────────────────────────────────────────
    ONE        = 'C62', 'One'
    EACH       = 'EA',  'Each'
    PIECE      = 'H87', 'Piece'
    PAIR       = 'PR',  'Pair'
    SET        = 'SET', 'Set'
    DOZEN      = 'DZN', 'Dozen'
    GROSS      = 'GRO', 'Gross'
    KIT        = 'KT',  'Kit'
    PORTION    = 'PTN', 'Portion'
    BULK_PACK  = 'AB',  'Bulk pack'
    BATCH      = '5B',  'Batch'
    BALL       = 'AA',  'Ball'

    # ── Mass / weight ────────────────────────────────────────────────
    MICROGRAM   = 'MC',  'Microgram'
    MILLIGRAM   = 'MGM', 'Milligram'
    CENTIGRAM   = 'CGM', 'Centigram'
    GRAM        = 'GRM', 'Gram'
    HECTOGRAM   = 'HGM', 'Hectogram'
    KILOGRAM    = 'KGM', 'Kilogram'
    TONNE       = 'TNE', 'Tonne (metric ton)'
    POUND       = 'LBR', 'Pound'
    OUNCE       = 'ONZ', 'Ounce (avoirdupois)'
    TROY_OUNCE  = 'APZ', 'Troy ounce'
    STONE       = 'STI', 'Stone (UK)'

    # ── Volume / liquid ──────────────────────────────────────────────
    MILLILITRE        = 'MLT', 'Millilitre'
    CENTILITRE        = 'CLT', 'Centilitre'
    DECILITRE         = 'DLT', 'Decilitre'
    LITRE             = 'LTR', 'Litre'
    HECTOLITRE        = 'HLT', 'Hectolitre'
    CUBIC_METRE       = 'MTQ', 'Cubic metre'
    CUBIC_CENTIMETRE  = 'CMQ', 'Cubic centimetre'
    CUBIC_MILLIMETRE  = 'MMQ', 'Cubic millimetre'
    CUBIC_FOOT        = 'FTQ', 'Cubic foot'
    CUBIC_YARD        = 'YDQ', 'Cubic yard'
    GALLON_US         = 'GLL', 'Gallon (US)'
    PINT_US           = 'PTL', 'Liquid pint (US)'
    PINT_UK           = 'PTI', 'Pint (UK)'
    QUART_US          = 'QTL', 'Liquid quart (US)'
    QUART_UK          = 'QTI', 'Quart (UK)'
    FLUID_OUNCE_US    = 'OZA', 'Fluid ounce (US)'
    FLUID_OUNCE_UK    = 'OZI', 'Fluid ounce (UK)'

    # ── Length ────────────────────────────────────────────────────────
    MILLIMETRE = 'MMT', 'Millimetre'
    CENTIMETRE = 'CMT', 'Centimetre'
    METRE      = 'MTR', 'Metre'
    KILOMETRE  = 'KMT', 'Kilometre'
    INCH       = 'INH', 'Inch'
    FOOT       = 'FOT', 'Foot'
    YARD       = 'YRD', 'Yard'
    MILE       = 'SMI', 'Mile (statute mile)'

    # ── Area ──────────────────────────────────────────────────────────
    SQUARE_MILLIMETRE = 'MMK', 'Square millimetre'
    SQUARE_CENTIMETRE = 'CMK', 'Square centimetre'
    SQUARE_METRE      = 'MTK', 'Square metre'
    SQUARE_FOOT       = 'FTK', 'Square foot'
    SQUARE_YARD       = 'YDK', 'Square yard'
    ACRE              = 'ACR', 'Acre'

    # ── Time (rentals / time-based services) ────────────────────────
    SECOND = 'SEC', 'Second'
    MINUTE = 'MIN', 'Minute'
    HOUR   = 'HUR', 'Hour'
    DAY    = 'DAY', 'Day'
    WEEK   = 'WEE', 'Week'
    MONTH  = 'MON', 'Month'
    YEAR   = 'ANN', 'Year'

    # ── Packaging / trade units (retail, F&B, wholesale) ────────────
    BAG     = 'BG', 'Bag'
    BOX     = 'BX', 'Box'
    BOTTLE  = 'BO', 'Bottle'
    CARTON  = 'CT', 'Carton'
    CASE    = 'CS', 'Case'
    CRATE   = 'CR', 'Crate'
    CUP     = 'CU', 'Cup'
    DRUM    = 'DR', 'Drum'
    JAR     = 'JR', 'Jar'
    PACK    = 'PK', 'Pack'
    PACKET  = 'PA', 'Packet'
    ROLL    = 'RO', 'Roll'
    REEL    = 'RL', 'Reel'
    SACK    = 'SA', 'Sack'
    SPOOL   = 'SO', 'Spool'
    SHEET   = 'ST', 'Sheet'
    TUBE    = 'TU', 'Tube'
    VIAL    = 'VI', 'Vial'
    CAN     = 'CA', 'Can'
    TIN     = 'TN', 'Tin'
    PALLET  = 'PF', 'Pallet (lift)'
    BUCKET  = 'BJ', 'Bucket'
    BASKET  = 'BK', 'Basket'
    BALE    = 'BL', 'Bale'
    BOLT    = 'BT', 'Bolt'
    CAP     = '4B', 'Cap'
