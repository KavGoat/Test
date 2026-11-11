# Tool check against the 2026 registers and the 11 Nov email

Inputs: `20261027 Asbestos Removal Programme Tool.xlsm`, the four station registers version 7 (Casey reviewed 25/06/2026, Davis 4/06/2026, Mawson 9/06/2026, Macquarie 9/06/2026), and the email thread Marcus Dowling / Hayden Clarke of 11 Nov 2026.

## 1. Entry counts

| Station | Register v7 entries | Tool rows | Result |
|---|---|---|---|
| Casey | 24 | 25 | One extra in tool: row 18 Red Shed plantroom Ferroli boiler gasket, no longer in the register |
| Davis | 26 | 26 | Match |
| Mawson | 57 | 58 | One extra in tool: row 9 Biscoe laundry entrance ceiling (Complete), no longer in the register |
| Macquarie | 100 (102 lines, two are continuation note rows) | 100 | Match |

Casey register v7 also dropped Reeve Hill, the Old Casey Ionosonde pipe and the earlier Ferroli entry; the tool no longer carries the first two. Mawson v7 added two entries that are now in the tool (rows 27 and 34).

## 2. Code and name differences

| Sheet | Row | Tool | Register v7 | Suggested change |
|---|---|---|---|---|
| Reg_Casey | 13 | "Debris Old Carpenter's Workshop removed Jan 2023, now ITC comms site." | Surrounding area adjacent to Old Carpenter's Workshop, "Debris" | Shorten item to "Debris" to match register |
| Reg_Casey | 12 | Main Power House (MPH) L1012, "Floor sheets" | Main Powerhouse L1012, "Floor." | Fine, same item |
| Reg_Casey | 18 | Red Shed – Plantroom, Ferroli boiler gasket | Not in register | Flag Complete, or remove at next update (see email note in section 5) |
| Reg_Davis | 22 | Refuelling Point Settling Tank L1146 | Store Fuel Tank L1146 | Rename to match register |
| Reg_Mawson | 9 | Biscoe (Heritage) L1238, entrance ceiling, Complete | Not in register (removed item dropped) | Remove row at next update |
| Reg_Mawson | 34 | Main Powerhouse / L1163, Electrical box between fuel tanks | Same, new v7 entry | Fine |
| Reg_Mawson | 27 | Living Quarters L1172, Hamworthey boiler gasket | Living Quarters (no Maximo number), new v7 entry | Fine |

All other codes match. Casey fuel tank codes updated to L1506 and L1934 match v7.

## 3. Email of 11 Nov 2026 (Macquarie demolitions)

Marcus Dowling: Transmitter Hut, Proton Processing Hut and Magnetic Variometer Building demolished this season, all ACM wrapped and packed for return to Australia. Hayden Clarke: leave completed items in the tool for now, flagged Complete; the report will recommend they are removed at the annual register update; registers are the single source of truth; new entries without quantities are for AAD to fill.

| Sheet | Rows | Status in tool | Suggested change |
|---|---|---|---|
| Reg_Macquarie | 99 to 103 Transmitter Hut, 70 Proton Hut, 51 Magnetic Variometer | Complete, "Noted as completed by AAD, 11/11/2026" | Correct. Add to U that the ACM is packed awaiting RTA so the return freight is known to be outstanding. Macquarie register v7 (Jan 2026 inspection) still lists them; they will drop out at the 2027 update. |
| All sheets | Complete rows (Casey 18 if flagged, Davis 15, 21, Mawson 9, 33, 46 to 48, 59, 60, Macquarie 49 to 51, 70, 81, 82, 99 to 103) | Complete | Keep per Hayden's note. Report text: flag Complete in the tool, remove when the register drops them. |

## 4. Removal thought process, rows that do not follow the agreed rules

| Sheet | Row | Item | Issue | Suggested change |
|---|---|---|---|---|
| Reg_Mawson | 27 | Hamworthey boiler gasket (new) | Q "No removal" on a gasket; Z, AK and AL contain pasted formula text; U blank | Q = Maintenance, R = Manage per AMP, U = "Gaskets to be removed during next maintenance.", clear Z, AK, AL |
| Reg_Mawson | 34 | Electrical box in dado wall (new) | V, AA, AC blank, U typo "Manager" | U: "Hole in dado wall sheet, sealed and labelled. Manage per AMP with the dado wall (row 32)." V = Wall Cladding/Lining |
| Reg_Mawson | 50, 51 | Behind tiles medical suite; formwork stair landings | Now Manage per AMP but AK and AL still filled; U typo "Manager" | Clear AK, AL; "Manage as per AMP, unable to quantify or access." |
| Reg_Mawson | 18 | East Arm tip | U typo "Manager" | "Manage as per AMP..." |
| Reg_Mawson | 60 | Water Supply switchboard | Q "No removal" with R Complete; register v7 still lists it as presumed asbestos, condition Good, relabelled | If the photo note (no asbestos) is relied on, Q blank and U cite the photo note; otherwise back to No removal / Manage per AMP |
| Reg_Macquarie | 15 | Electrical Distribution Hut cable pipe | End-of-life removal carries reinstatement "Pipe – Electrical Conduit" | Clear Y (no reinstatement on end-of-life removal) |
| Reg_Macquarie | 69 | Post Office vinyl tiles | Summer for an internal item, on its own in 2030; V Floor Sheeting/Lining | Winter; package with Mess works 2034 or Comms 2034; V = Vinyl Linings (as row 57) |
| Reg_Davis | 19 | Trades office vinyl tiles | Register v7: tiles now covered by Regupol flooring, intact. Covered floor rather than exposed tiles | Either keep Removal - Partial with "lift Regupol first" in U and complexity Medium (covering stripped first), or revert to Manage per AMP as a covered floor. V = Vinyl Linings |
| Reg_Casey | 17 | Red Shed crawlway boards | Register v7: "sheets removed under main sub floor in 25, sheets under medical in good condition". Part already done | Removal - Partial or reduce AA from 72 m2 to the medical area; U: "Main subfloor sheets removed 2025, remaining sheets under medical." |
| Reg_Casey | 9 | Mabel Hut floor | Changed from End-of-life 2035 to Manage per AMP with the no-quantity text | Hut rule applies (Mabel Hut); use the hut commentary rather than no-quantity. Register notes new floor sheet now covers the old floor. |
| Reg_Macquarie | 12, 42, 44 | Wall and ceiling combined rows | Access Challenging while ceilings elsewhere are Extreme | Acceptable because coded as wall items; note only |
| Reg_Davis | 12 | MPH wall sheets | U still starts with "AIRP scope of works. Provided by AAD 18/06/2026. Assume full building demo rather than upgade." | Keep only "Remove season prior to demolition. Remove later in the season to achieve maximum use." |
| Reg_Macquarie | 9 | Biology interior ceiling liner | Was Complete in the earlier tool, now Preference removal 2034 with 155 m2 | Fine if it was never removed (register v7 still lists it). Confirm the 155 m2 is this liner and not a copy of row 10. |

## 5. Register changes in v7 that affect decisions

| Station | Register note | Tool row | Effect |
|---|---|---|---|
| Casey | Red Shed crawlway: sheets removed under main subfloor in 2025 | 17 | Reduce scope (above) |
| Casey | Robinson's Ridge floor now covered by carpet | 19 | None, hut, Manage per AMP |
| Casey | Ferroli boiler gasket removed from register | 18 | Complete or remove |
| Davis | Old Garage site and beach slab confirmed removed (Jan 2026) | 15, 21 | Complete, correct |
| Davis | Workshop vinyl tiles under Regupol | 19 | See above |
| Davis | Brookes Hut interior lining: work order DW373655 to line with ply and seal | 5 | None, hut, Manage per AMP; could note the sealing work order in U |
| Mawson | Water Supply pump gaskets removed and replaced 4/26 | 59 | Complete, correct |
| Mawson | MPH generator gaskets inspected and removed | 33 | Complete, correct |
| Mawson | Stair landing formwork mostly removed and encapsulated | 51 | Manage per AMP, correct |
| Mawson | Fume cupboard items condition Removed | 46 to 48 | Complete, correct |
| Macquarie | January 2026 inspection, no item changes | all | None; demolitions in section 3 post-date it |

## 6. Housekeeping still open from earlier reviews

| Sheet | Rows | Item |
|---|---|---|
| Casey | 6, 8, 11, 18, 21 to 28 | "Provided by AAD 18/06/2026" still in U |
| Davis | 9, 11, 12, 14, 16 | Same |
| Macquarie | 32 | Same |
| Macquarie | 9, 10 | "celing" in W |
| Macquarie | 61 | "strucutre", "encapsultate" in U |
| Mawson | 18, 34, 50, 51 | "Manager" for "Manage" in U |

## 7. Rules checked and found consistent

Gaskets all Maintenance / Manage per AMP except the new Mawson 27 above. No year after 2037. No reinstatement on end-of-life rows except Macquarie 15. Huts and heritage all Manage per AMP. Floor sheeting Manage per AMP, end-of-life floors in the demolition season at High / Extreme. Covered internal linings removed with complexity stepped up. Ceilings Extreme on all ceiling-coded rows. Complete rows have Q blank except Mawson 60. Removal rows all carry trade, scope, adjusters and quantities.
