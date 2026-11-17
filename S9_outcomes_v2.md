# Section 9 outcomes, updated tool, with working

Source: `20261117 Asbestos Removal Programme Tool.xlsm` (latest upload). Changes since the last version are in Macquarie only: Balloon Building walls corrected (rows 45, 46 now 44.2 and 37.4 m2, blast panels 12.2 m2) and the Mechanical Workshop ceiling (row 55) moved back from 2033 to 2029. Casey, Davis and Mawson figures are unchanged.

Costs are the tool's inflation-adjusted cost (column AX) unless marked "present cost" (column AW). Years are the tool's Est. Year for Works, which is the season start year.

---

## 1. How the figures are built

### 1.1 One row, step by step (Mawson SMQ fire doors, row 44, 2032)

| Step | Column | Formula in tool | Working | Result |
|---|---|---|---|---|
| ACM volume | AE | measure x thickness, min 0.027 | 24 doors x 0.099 m3 | 2.376 m3 |
| Labour adjuster | AM | 1 + complexity + access | 1 + 0% (Low) + 0% (Simple) | 1.00 |
| Removal labour | AN | volume x 4.25 days/m3, min 1 day, x adjuster, round up to 0.5 | 2.376 x 4.25 = 10.10, round up | 10.5 days |
| Reinstatement labour | AO | count x tool hours per item / 4 tool hours per day x adjuster | 24 x 16 h / 4 h | 96 days |
| Total labour | AP | AN + AO | 10.5 + 96 | 106.5 days |
| Removal labour cost | AQ | days x 8 h x station rate | 10.5 x 8 x $727.79 | $61,134 |
| PPE and equipment | AR | volume x $750/m3 | 2.376 x 750 | $1,782 |
| Reinstatement labour cost | AS | days x 8 h x station rate | 96 x 8 x $727.79 | $558,943 |
| Reinstatement material | AT | count x material rate | 24 x $3,450 | $82,800 |
| Freight to station | AU | m3 x station rate | 3.251 x $6,191.74 | $20,129 |
| Freight from station | AV | m3 x station rate | 4.064 x $6,191.74 | $25,163 |
| Present cost | AW | AQ + AR + AS + AT + AU + AV | | $749,952 |
| Inflation factor | | 1.035 ^ full years from today to 1 Dec of works year | 1.035^6 | 1.2293 |
| Inflation-adjusted cost | AX | AW x factor | 749,952 x 1.2293 | $921,882 |

Labour days are counted on 4 productive tool hours a day, but each day is paid at 8 hours. Reinstatement drives this item: $642k of the $750k present cost is fitting and supplying the replacement doors.

### 1.2 Inflation factors applied (tool opened 17 Nov 2026)

| Works year | 2027 | 2028 | 2029 | 2030 | 2031 | 2032 | 2033 | 2034 | 2035 | 2036 | 2037 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Years counted | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 |
| Factor (3.5% a year) | 1.035 | 1.071 | 1.109 | 1.148 | 1.188 | 1.229 | 1.272 | 1.317 | 1.363 | 1.411 | 1.460 |

**Check before quoting figures.** The factor counts full years from `TODAY()` to 1 December of the works year. Opened after 1 December 2026, every count drops by one and all inflated costs fall by about 3.4%. For example, the program total drops from $11.48M to about $11.09M. Either quote figures as at a stated date, or change the formula to a fixed base date in the Variables sheet.

### 1.3 Station and year totals

Each total below is the sum of AX (or AP for labour) over the removal rows (Removal - Full and Removal - Partial) for that station and year. Manage per AMP and Complete rows carry no cost.

| Year | Casey | Davis | Macquarie | Mawson | All stations | Labour days |
|---|---|---|---|---|---|---|
| 2027 | $177k | $32k | – | – | $209k | 35.5 |
| 2028 | $43k | $271k | $504k | – | $818k | 156.0 |
| 2029 | $149k | $19k | $931k | $49k | $1,146k | 227.0 |
| 2030 | – | $734k | $678k | $54k | $1,466k | 255.0 |
| 2031 | $31k | $70k | $755k | – | $856k | 157.0 |
| 2032 | $264k | – | $781k | $937k | **$1,982k** | **292.0** |
| 2033 | – | – | $798k | $328k | $1,126k | 175.5 |
| 2034 | – | – | **$1,119k** | $45k | $1,164k | 196.0 |
| 2035 | – | – | $1,065k | – | $1,065k | 178.0 |
| 2036 | – | – | $1,022k | $365k | $1,387k | 202.5 |
| 2037 | $9k | – | – | $251k | $260k | 23.0 |
| **Total** | **$672k** | **$1,126k** | **$7,653k** | **$2,029k** | **$11,480k** | **1,897.5** |
| Present cost (AW) | $592k | $1,000k | $6,155k | $1,576k | $9,322k | |

| Station | Entries | Full | Partial | Manage per AMP | Complete | Labour days (removal + reinstatement) | ACM removed |
|---|---|---|---|---|---|---|---|
| Casey | 24 | 6 | 0 | 18 | 0 | 105.0 (22.0 + 83.0) | 3.8 m3 |
| Davis | 26 | 7 | 1 | 16 | 2 | 176.0 (69.0 + 107.0) | 12.5 m3 |
| Macquarie | 100 | 42 | 3 | 44 | 11 | 1,392.0 (241.5 + 1,150.5) | 40.0 m3 |
| Mawson | 57 | 9 | 4 | 38 | 6 | 224.5 (64.0 + 160.5) | 10.9 m3 |

Macquarie is 67% of program cost ($7.65M of $11.48M) and 73% of labour. Across the program, reinstatement is about 80% of labour days (1,500.5 of 1,897.5).

**Program peak.** 2032, $1.98M, made up of:

| Item | Cost |
|---|---|
| Mawson SMQ fire doors (row 44) | $922k |
| Macquarie Hasselborough House, five rows (39 to 42, 44) | $781k |
| Casey Main Power House dado wall (row 10) | $264k |
| Mawson SMQ laundry splashback (row 48) | $15k |
| **Total** | **$1,982k** |

---

## 2. Lead-in paragraph (Section 9, highlighted)

The highlighted cross-references (Section 4, Section 3.6, Appendix C, Sections 9.1 to 9.4) are correct. Suggested edits:

- Replace "as of 20 November 2026" with "the version 7 Asbestos Registers (2026) and AAD advice to 11 November 2026".
- Add after the gasket sentence: "Items with no quantity in the register, and items in huts and heritage buildings, are also not costed."
- Add: "Across the four stations the program totals $11.5M (inflation adjusted) and about 1,900 labour days, with the largest year in 2032 at $2.0M."

---

## 3. Casey (9.1)

**Fill-ins.** Four buildings can be made completely ACM free by the end of the 10-year window: ANARESAT Equipment Building, Balloon Release Building, Receiver Building and the Red Shed. The Transmitter Building is removed by demolition in 2037. The Main Power House and the Operations Building cannot be made completely ACM free without full demolition, because of their floor sheets and subfloor.

**Key findings:**

- Peak spend of $264k in 2032, driven by removal of the Main Power House dado wall lining (row 10, 39 labour days).
- Unquantified ACM not in the program: Jack's Donga insulation, Mabel Hut floor, Robinson's Ridge Hut floor and debris around the old Carpenter's Workshop.
- The Wilkes sites (six entries) are excluded from the program at AAD's request.
- Five fuel tank gasket entries are managed per AMP and will be replaced with tank maintenance.
- The program is small at $0.67M and 105 labour days, with no works in 2030 or from 2033 to 2036.
- The Red Shed crawlway is costed at the full 72 m2 ($149k in 2029) although the register notes the main subfloor sheets were removed in 2025, so the cost is likely overstated.

**Working:**

| Item | Calculation |
|---|---|
| Buildings made ACM free | Every entry for the building is Removal - Full within 2037: ANARESAT (row 4), Balloon Release (row 5), Receiver (row 16), Red Shed (row 17) |
| Peak | 2032 is the single row 10, $264,322 |
| Total | $176,756 + $43,108 + $148,673 + $30,676 + $264,322 + $8,800 = $672,334 |

## 4. Davis (9.2)

**Fill-ins.** Two buildings or sites can be made completely ACM free by the end of the 10-year window: the Sleeping and Medical Quarters plant room coating and the Site Services J1 stair base. The Emergency Power House (2028) and Main Power House (2032) are removed by demolition. The Green Store (mezzanine floor sheets) and the Site Services L1132 footings (formwork embedded in the foundations) cannot be made completely ACM free without full demolition.

**Key findings:**

- Peak spend of $734k in 2030, driven by the General Workshop internal wall sheets (369 m2, 116.5 labour days, of which 96 are reinstatement). The register suggests staged removal during a shutdown.
- A second peak of $271k in 2028 from the Emergency Power House demolition items and the friable plant room coating in the Sleeping and Medical Quarters.
- Unquantified ACM not in the program: the Old Tip Site (buried) and loose pieces around Watts Hut.
- The General Workshop trades office vinyl tiles are now covered with Regupol and are managed per AMP.
- Brookes Hut and Watts Hut are managed per AMP as huts. Seven gasket entries are managed per AMP; the Main Power House gaskets go with the building at demolition.
- Old Garage Site and the beach slab are recorded as Complete.

**Working:**

| Item | Calculation |
|---|---|
| Peak | 2030 is the single row 18, $734,089 |
| 2028 | EPH panels $184,320 + SMQ coating $71,070 + EPH manifolds $15,509 = $270,899 |
| Total | $32,447 + $270,899 + $18,522 + $734,089 + $69,922 = $1,125,879 |

## 5. Macquarie Island (9.3)

**Fill-ins.** No retained building at Macquarie can be made completely ACM free within the 10-year window. The Emergency Radio Hut, the Emergency Power House and the Electrical Distribution Hut cable pipe are removed with decommissioning in 2034 and 2035. The Transmitter Hut, Proton Processing Hut and Magnetic Variometer Building were demolished in the 2026 season. Internal linings, ceilings and soffits are removed from all main station buildings over the program, but most buildings retain cement sheet behind external timber cladding or under floor coverings that can only be removed with demolition.

The full list of buildings that cannot be made ACM free without demolition, with the reason:

| Reason | Buildings |
|---|---|
| Sheet behind external timber cladding | Biology Laboratory, Fire Pump House, Garden Cove Donga, Hasselborough House, Balloon Building, Mechanical Workshop, Pump House, Bunkhouse, Sauna, Surgery |
| Sheet under floors | Comms Building, Garden Cove Donga, Mess, Surgery |
| Partial removal only | Southern Aurora Donga (ceiling under copper sheeting), Post Office and Mechanical Workshop (tiles under partitions) |

**Key findings:**

- Peak spend of $1.12M in 2034, driven by the two Biology Laboratory ceiling liners ($932k together, 164 labour days).
- Spend is above $1M a year from 2034 to 2036 and between $0.5M and $0.93M in every other year from 2028. Macquarie is about two thirds of the total program cost.
- The Mechanical Workshop ceiling ($931k, 194.5 labour days) is now in 2029 because of its poor condition, which makes 2029 the second largest Macquarie year.
- The Mechanical Workshop office vinyl tiles ($403k in 2033) are costed on 368 m2, the whole building. The office area needs measuring.
- Unquantified ACM not in the program: Meteorology Office and Meteorology Technician's Workshop (all items), Pump House brewery linings, Sauna cold porch, SAD bathroom walls, Mechanical Workshop external sheeting and ceiling space debris, Green Store debris, Flammable Liquid Hut soffit, tip site, loading ramp pipe and fire hydrant pipe.
- Huts (Bauer Bay, Fire Hut, Green Gorge, Flammable Liquid Hut, the seal hide) are managed per AMP.
- End-of-life dates were not available for most buildings, so removal years for Preference items are a planning assumption spread across the program.
- The three buildings demolished this season are shown as Complete, with their ACM packed awaiting return to Australia.

**Working:**

| Item | Calculation |
|---|---|
| Peak, 2034 | Biology ceilings $465,942 + $465,942, EPH ceiling $54,051, Ham Shack walls $48,184, Ham Shack ceiling $33,620, EPH walls $33,233, Post Office tiles $17,703 = $1,118,674 |
| 2029 | Mechanical Workshop ceiling, single row 55, $930,614 |
| 2035 | SAD ceiling $499,987 + SAD walls $315,306 + Surgery four rows $182,797 + EPH and Ham Shack decommissioning items $67,164 = $1,065,254 |
| 2036 | Sauna $322,028 + Bunkhouse $375,660 + Pump House $233,836 + Fire Pump House $90,538 = $1,022,062 |
| Share of program | $7,652,974 / $11,479,812 = 67% |

## 6. Mawson (9.4)

**Fill-ins.** No retained building at Mawson can be made completely ACM free within the 10-year window. The Transmitter Building is removed by demolition in 2036 and 2037. Aeronomy, ANARESAT Equipment Building, Green Store, Main Power House and the Sleeping and Medical Quarters cannot be made completely ACM free without full demolition, because of floor sheets and underfloor sheeting. The Tankhouse and Water Supply Building retain formwork embedded in their foundations.

**Key findings:**

- Peak spend of $937k in 2032, almost all from the Sleeping and Medical Quarters fire doors (24 doors, $922k, 106.5 labour days). Section 3.3 explains how this would be staged over two seasons.
- Ten heritage buildings (Biscoe, Cosray, Dog Hut, Dovers, Electricians Workshop, Hangar, PID Van, Science Building (Wombat), Shackleton, Wilkins) are excluded from removal and managed per AMP.
- Unquantified ACM not in the program: Dovers partitions, East Arm tip, Shackleton walls and switchboard, the Main Power House electrical box, and the tiled areas and stair landing formwork in the Sleeping and Medical Quarters.
- The Incinerator Building switchboard is tied to the end of life of that building, which is not yet confirmed.
- Ten gasket entries are managed per AMP. The Main Power House generator gaskets and Water Supply pump gaskets are recorded as Complete.
- No works are programmed in 2027, 2028, 2031 or 2035.

**Working:**

| Item | Calculation |
|---|---|
| Peak, 2032 | Fire doors $921,882 + laundry splashback $15,061 = $936,943 |
| Fire door share of station | $921,882 / $2,028,625 = 45% |
| Total | $48,523 + $53,527 + $936,943 + $328,412 + $45,470 + $364,992 + $250,758 = $2,028,625 |
