# Tool close-out, calc check and programme spread

Inputs: `20261027 Asbestos Removal Programme Tool.xlsm` (upload of 11 Nov), the four ACM Volume Estimate calc PDFs (Casey, Davis, Macquarie, Mawson, all Rev 0), and the previous check `Tool_vs_registers_v7.md`. Row numbers are the current tool rows (Casey 4 to 27, Davis 4 to 29, Mawson 4 to 60, Macquarie 4 to 103).

## 1. Close-out of the previous check

Closed in this version: Casey Ferroli gasket row deleted; Mawson Biscoe entrance row deleted; Mawson fume cupboard and pump gasket rows struck through to match the register; Mawson Hamworthey gasket recoded Maintenance with the pasted formulas removed; Mawson 49 and 50 adjusters cleared; Mawson 18 and 33 "Manager" typos fixed; Macquarie 15 reinstatement cleared; Macquarie 69 moved to Winter 2034 with the Mess works; Mawson 59 Q cleared. Every row has a requirement and treatment.

Still open:

| Sheet | Row | Item | Suggested change |
|---|---|---|---|
| Reg_Casey | 13 | Item text still "Debris Old Carpenter's Workshop removed Jan 2023, now ITC comms site." | "Debris" to match register v7 |
| Reg_Casey | 17 | Red Shed crawlway still Removal - Full, 72 m2. Register v7: main subfloor sheets removed in 2025, sheets under medical remain | Reduce AA to the medical area (or Removal - Partial); U: "Main subfloor sheets removed 2025, remaining sheets under medical." |
| Reg_Davis | 4 | Brookes Hut, Manage per AMP, still carries reinstatement, complexity and access | Clear Y, AK, AL |
| Reg_Davis | 19 | Vinyl tiles back to Manage per AMP (covered by Regupol, fine) but AK and AL still filled | Clear AK, AL |
| Reg_Davis | 12 | U still starts "AIRP scope of works. Provided by AAD 18/06/2026. Assume full building demo rather than upgade." | Keep the two "Remove season prior..." sentences only |
| Reg_Davis | 22 | Named Refuelling Point Settling Tank; register v7 says Store Fuel Tank L1146 | Rename |
| Reg_Mawson | 32 | MPH generator gaskets Complete, "all gaskets inspected and removed". Register v7 says 2017 inspection found none but entry remains current, treat with caution | Maintenance / Manage per AMP with the register wording, or get AAD to close it in the register first |
| Reg_Mawson | 59 | Water Supply switchboard Complete on a photo caption; register v7 still presumed asbestos, condition Good, relabelled | No removal / Manage per AMP until the register closes it |
| Reg_Macquarie | 44 | Hass House laundry walls and ceilings coded Ceiling with access Challenging | Extreme (ceiling convention) or recode V as wall |
| Reg_Macquarie | 69 | Post Office vinyl tiles coded Floor Sheeting/Lining | Vinyl Linings, as row 57 |
| Reg_Macquarie | 9, 10 | "celing" in W | ceiling |
| Reg_Macquarie | 61 | "strucutre", "encapsultate" in U | structure, encapsulate |
| Casey 6, 8, 11, 20 to 27; Davis 9, 11, 14, 16; Macquarie 32 | | "Provided by AAD 18/06/2026" still in U | Your call; left as is so far |

## 2. Calc PDFs against the tool

Convention check first: for gaskets the tool uses AA = number of gaskets and AC = volume per gasket (0.0002 m3), for pipes and the SMQ coating AC = cross-section area per metre, for doors AC = volume per door. That is consistent with the calcs except where noted.

### 2a. Values that differ between calc and tool

| Station | Calc page | Item | Calc | Tool row and value | Suggested change |
|---|---|---|---|---|---|
| Casey | 3 | Balloon Release dado wall | 87.36 m2 x 0.012 m | Row 5: 87.4 m2 x 0.01 m | Align thickness (0.012 in calc, 0.01 in tool); 0.01 is the standard used elsewhere, so correct the calc |
| Casey | 6 | Lower Fuel Farm gaskets | 6 tanks x 2 = 12 | Row 8: AA = 6 | AA = 12 |
| Casey | 15 | Upper Fuel Farm gaskets | 5 tanks x 2 = 10 | Row 20: AA = 5 | AA = 10 |
| Casey | 16 | Vehicle Fuel Settling Tank gaskets | 1 tank x 2 = 2 | Row 21: AA = 1 | AA = 2 |
| Casey | 14 | Transmitter Building cold porch | 17.28 m2, but page also shows "44.82 m2 x 0.01 = 0.0.1728m3" | Row 19: 17.28 | Tool is right; delete the stray 44.82 line on the calc page |
| Davis | 2 | Brookes Hut exterior cladding | "lacking info, can't give a good estimate" | Row 4: 60 m2 x 0.025 | Either add the 25 m x 2.4 m assumption to the calc page or blank the tool value (Manage per AMP row, no cost effect) |
| Davis | 3 | EPH external and roofing panels | No area on page | Row 8: 268 m2 x 0.02 | Add the calc for 268 m2 |
| Davis | 19 | General Workshop internal wall sheets | Sum of wall areas 872.389 m2 | Row 18: 360 m2 | Resolve. 360 m2 does not appear on the page. If 872 is right, labour roughly doubles (now 106.5 days) |
| Davis | 19 | Trades office vinyl tiles | No floor area stated | Row 19: 20.6 m2 | Add the area to the page (Manage per AMP now, so no cost effect) |
| Davis | 18 | Watts Hut interior linings | 28.8 m2 "for both interior areas of concern" | Rows 24 and 25: 28.8 each | Double count; split 14.4 each or state the assumption (Manage per AMP, no cost effect) |
| Mawson | 7 | Dovers internal partitions | No Dovers page; 11.25 m2 is the Dog Hut floor area | Row 16: 11.25 m2 with Dog Hut assumption text | Add a Dovers calc; AF text is copied from Dog Hut |
| Mawson | 8 | EPH generator gaskets | 2 per tank x 3 tanks = 6 | Row 19: AA = 3 | AA = 6 |
| Mawson | 15 | Transmitter Building | Page has photos and dimensions only, no areas | Rows 52 to 54: 200.64, 76, 200.64 | Add the working (2 x (10 + 7.6) x 5.7 = 200.64; 10 x 7.6 = 76) to the page |
| Mawson | 13 | Wombat cold porch walls | "2 internal walls 1.2 L and 1.2 W" | Row 37: 17.28 m2 (= 1.2 x 6 x 2.4) | Page and tool do not derive the same number; write the calc out |
| Macquarie | 2 | Biology ceiling liner | One 155 m2 figure for "cement sheet ceiling liner in roof space" | Rows 9 and 10: 155 m2 each, both Removal - Full 2034, 77.5 days each | Likely double count of one sandwich ceiling (internal face and roof-space face). Either combine into one row or halve the thickness on each. This is 77.5 days and about $240k |
| Macquarie | 5 | EPH cable pipe, 65 m | "assumed 10 mm thick pipe, volume 0.18 m3" | Row 23: AC = 0.01 (gives 0.65 m3) | AC should be the cross-section area per metre, 0.0023 as on row 15 (same pipe size). Volume 0.15 m3, not 0.65 |
| Macquarie | 11 | Hass House east cold porch | 43 m2 wall + 9 m2 ceiling = 52 m2 | Row 42: 54 m2 | 52 |
| Macquarie | 11 | Hass House laundry and bathrooms | 45.6 m2 walls + 22.5 m2 ceiling | Row 44: 45.6 m2 coded Ceiling | Either 68.1 m2, or split into wall and ceiling rows |
| Macquarie | 13 | Workshop office vinyl tiles | No office area on page | Row 57: 368 m2 (whole building) | Measure the office; 368 m2 gives 65 days and $223k for an office floor |
| Macquarie | 13 | Workshop ceiling space debris | No calc | Row 56: 368 m2 x 0.012 (4.4 m3, 28.5 days) | Loose pieces are a fraction of a ceiling. Suggest an allowance, e.g. 10 percent of ceiling area |
| Macquarie | 16, 17 | Sauna and Bunkhouse | Both pages use the identical wall formula 10.7x2 + 4x3 + 3x2 + 2x4 = 47.4 m, and the Bunkhouse ceiling (8 x 3.5 + 2.4 x 3 = 35.2) is the Pump House ceiling formula | Rows 78, 80, 83 | Pages look copy-pasted; re-measure Bunkhouse walls and ceiling |
| Macquarie | 4 | Ham Shack floor | Not on page | Row 18: 31.3 m2 ("half the building") | Add to page |

### 2b. Tool rows with quantities but no calc page

| Sheet | Rows | Item |
|---|---|---|
| Reg_Casey | 11 | MPH Fuel Settling Tank L1506 gaskets, AA = 2 |
| Reg_Davis | 8 | EPH external and roofing panels 268 m2 (page exists but has no numbers) |
| Reg_Mawson | 16 | Dovers partitions 11.25 m2 |
| Reg_Mawson | 20, 21, 22 | Fuel settling tank and GAAM pump gaskets |
| Reg_Mawson | 24, 25, 59 | Hangar, Incinerator and Water Supply switchboards 0.96 m2 |
| Reg_Mawson | 26, 27 | LQ boiler and plant room gaskets |
| Reg_Mawson | 28 | LQ fire doors to basement (SMQ page counts SMQ doors only) |
| Reg_Mawson | 29, 55 | Lower and Upper Fuel Farm gaskets, 12 each |
| Reg_Mawson | 32, 58 | MPH generator gaskets 8, Water Supply pump gaskets 6 |
| Reg_Mawson | 52 to 54 | Transmitter Building areas |
| Reg_Macquarie | 4, 5 | Bauer Bay Hut 50 and 160 m2 |
| Reg_Macquarie | 22 | EPH generator gaskets 4 |
| Reg_Macquarie | 30 | Fire Pump House ceiling 8.69 m2 (derivable from page 7, not written) |
| Reg_Macquarie | 48, 49, 68, 88 | Loading ramp pipe 4 m, Lusitania roof 12 m2, tip 200 m2, hydrant pipe 4.5 m (all "assumed") |
| Reg_Macquarie | 59, 60, 61 | Mess pantry wall 24, ceiling 5, floor 5 (page 14 shows breezeway only) |
| Reg_Macquarie | 90, 91 | SAD ceiling 158 and walls 147 (page 21 shows eaves only) |
| Reg_Macquarie | 100 | Transmitter Hut ceiling and wall liner 68.5 m2 (page 20 has the 46 m2 cladding only) |

### 2c. Calc pages no longer needed, duplicated or mislabelled

| Station | Page | Reason |
|---|---|---|
| Casey | 4 | Balloon Release floor sheeting 85.255 m2. The duplicate tool row was deleted and register v7 has no floor entry for this building |
| Casey | 9 | Old Chippies debris, no quantity, Manage per AMP. Informational only |
| Casey | 15 | Labelled Upper Fuel Farm L1935; register and tool use L1934 |
| Davis | 9, 10, 15 | Old Garage, Old Tip, beach slab. Complete or Manage per AMP with no quantity. Informational only |
| Davis | 16 | Labelled Refuelling Point Settling Tank; register says Store Fuel Tank L1146 |
| Mawson | 6 | Exact duplicate of page 3 (ANARESAT) |
| Mawson | 4 | Biscoe page covers the laundry ceiling only; the struck entrance item has been deleted from the tool, fine |
| Macquarie | 20 | Transmitter Hut, now Complete after demolition. Keep for the RTA freight volume this season, drop at the next update |
| Macquarie | 6 | Fire Hut, a hut and out of scope. Keep or drop, no cost effect |

### 2d. Rate check worth a look

Mawson row 44, SMQ fire doors: 29 doors give 128.5 labour days and $648k, of which removal is 12.5 days and reinstatement 116 days. That comes from the Reinstatement table rate of 16 tool-hours per fire door. If that rate is intended it stands, but it makes this one item a quarter of the Mawson programme. Confirm the rate with North Projects or apply a labour adjuster.

## 3. Programme spread

Current labour days and inflation-adjusted cost by year, all stations, removal rows only:

| Year | Labour days | Cost | Items | Main drivers |
|---|---|---|---|---|
| 2027 | 35.5 | $113k | 2 | Casey dado wall, Davis EPH walls |
| 2028 | 107.5 | $339k | 6 | Davis EPH demolition items, Davis plant room coating, Macquarie soffits |
| 2029 | 244.0 | $692k | 7 | Macquarie workshop ceiling 183.5 d |
| 2030 | 109.5 | $324k | 5 | Macquarie Biology walls |
| 2031 | 328.5 | $1,087k | 6 | Davis workshop 106.5 d, Macquarie workshop walls 139.5 d, office tiles 65 d |
| 2032 | 301.5 | $1,189k | 8 | Mawson fire doors 128.5 d, Macquarie Hass House 135 d, Casey MPH dado 36.5 d |
| 2033 | 168.0 | $575k | 5 | Macquarie Garden Cove and Bunkhouse, Mawson MPH dado |
| 2034 | 297.5 | $1,018k | 13 | Macquarie Biology ceilings 155 d, Mess 57.5 d, Comms 29 d, Ham Shack and EPH |
| 2035 | 158.5 | $539k | 9 | Macquarie SAD and Surgery, EPH demolition items |
| 2036 | 110.0 | $411k | 6 | Macquarie pump houses and Sauna, Mawson Transmitter internal |
| 2037 | 23.0 | $151k | 3 | Mawson Transmitter demolition, Casey Transmitter |

Peaks are 2029, 2031, 2032 and 2034, each driven by one or two Preference items that can move. End-of-life items stay where they are. Suggested moves, keeping each building's works in one season and keeping Winter for internal work:

| Sheet | Row | Item | Now | Move to | Reason |
|---|---|---|---|---|---|
| Reg_Macquarie | 12 | Comms sked room | Winter 2034 | Winter 2030 | 2030 is light; takes 29 d out of 2034 |
| Reg_Macquarie | 58, 59, 60 | Mess breezeway and pantry | Winter 2034 | Winter 2028 | 2028 has only soffits at Macquarie; takes 57.5 d out of 2034 |
| Reg_Macquarie | 57 | Workshop office vinyl tiles | Winter 2031 | Winter 2033 | Separates it from the workshop wall year; the 368 m2 also needs correcting first |
| Reg_Macquarie | 78, 80 | Bunkhouse walls and ceiling | Winter 2033 | Winter 2036 | 2036 is light; keeps Garden Cove alone in 2033 |
| Reg_Macquarie | 9, 10 | Biology ceilings | Winter 2034 | Keep 2034 but fix the double count | Halves 155 d to about 78 d |
| Reg_Davis | 18 | General Workshop walls | Summer 2031 | Summer 2030 | Davis has nothing in 2030; MPH end-of-life stays 2031. Fix the 360 vs 872 m2 first |
| Reg_Mawson | 44 | SMQ fire doors | Winter 2032 | Ground floor 2032, first floor 2033 | Splits 128.5 d across two winters; or resolve the reinstatement rate, which may remove the problem |
| Reg_Mawson | 7 | ANARESAT cold porch walls | Winter 2034 | Winter 2035 | Mawson has nothing in 2035; balances 2034 |

Resulting labour by year if all moves are made and the Biology double count is fixed (office tiles left at current area):

| Year | Labour days | Change |
|---|---|---|
| 2027 | 35.5 | none |
| 2028 | 165.0 | +57.5 |
| 2029 | 244.0 | none, workshop ceiling is poor condition and should stay early |
| 2030 | 245.0 | +135.5 |
| 2031 | 157.0 | −171.5 |
| 2032 | 237.0 | −64.5 |
| 2033 | 238.5 | +70.5 |
| 2034 | 110.0 | −187.5 |
| 2035 | 182.0 | +23.5 |
| 2036 | 168.5 | +58.5 |
| 2037 | 23.0 | none |

Range falls from 23 to 328 days a year to 23 to 245, with 2029 and 2030 the remaining peaks. If the Macquarie workshop ceiling can wait one year, moving rows 55 and 56 to 2028 instead of the Mess items would level 2028 to 2030 at roughly 200 days each.

Cost follows labour closely, so the same moves flatten the money. Freight is small on every year except 2029, 2031 and 2034 at Macquarie, and the same moves spread it.
