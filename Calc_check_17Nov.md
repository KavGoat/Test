# Calc check, 17 Nov tool against the calc packs

Inputs: `20261117 Asbestos Removal Programme Tool.xlsm` and the four ACM Volume Estimate packs (Casey 15 pages, Davis 18, Macquarie 23, Mawson 18). Compared every tool row that carries an area or thickness against its calc page. Rows whose only basis is a stated assumption (gasket counts, switchboard sizes, assumed footings and the like) are not listed; there is no calc to check. The Macquarie Biology ceiling rows 9 and 10 are confirmed as two items and not listed.

## 1. Closed since the last check

Gasket counts corrected on Casey 8, 20, 21 and Mawson 19. Davis workshop walls now 369.2 m2 on both the page and the tool. Macquarie EPH cable pipe now uses the cross-section (0.0023). Hass House cold porch 52 m2 and laundry 68.1 m2 now match the page. Mess pantry wall, ceiling and floor now on the Mess page and in the tool. SAD ceiling and walls now on the SAD page. Ham Shack floor and Fire Pump House ceiling now written on their pages. Mawson Transmitter Building areas now written on the page and the Wombat cold porch formula matches. Dovers, Brookes Hut, Bauer Bay, the tip, ramp pipe, hydrant pipe, Lusitania roof and the Transmitter Hut rows have had their unsupported quantities cleared. Casey page 3 thickness, the stray 44.82 on page 13 and the Upper Fuel Farm code are fixed. Casey Old Chippies page and Davis Brookes Hut page removed.

## 2. Values that still differ between calc and tool

| Station | Page | Item | Calc | Tool | Suggested change |
|---|---|---|---|---|---|
| Davis | 12 | SMQ plant room coating on steel | Cross-section written as 0.02 m2, volume 0.02 x 35 = 0.7 m3 | Row 10: 21.99 m2 x 0.003 m = 0.066 m3 | The tool is right (surface area x 3 mm). The page arithmetic is wrong: (pi x 0.103^2) minus (pi x 0.1^2) is 0.0019 m2, not 0.02. Rewrite the page as surface area 3.14 x 0.2 x 35 = 22 m2 x 0.003 m |
| Davis | 17 | Watts Hut interior linings | 28.8 m2 "for both interior areas of concern" | Rows 24 and 25: 28.8 m2 each | Page says one figure covers both items; tool counts it twice. Manage per AMP so no cost effect, but align (14.4 each, or say 28.8 is per room) |
| Macquarie | 13 | Workshop office vinyl tiles | Page now labels the 23 x 16 = 368 m2 line "ceiling lining/flooring" | Row 57: 368 m2, and AF still says "Assumed the whole building is considered as office? Not annotated on drawing" | Register item is the office floor only. Either measure the office or, if the whole floor is tiled, change the AF note so the tool and page say the same thing |
| Macquarie | 17 | Bunkhouse ceiling | 8 x 3.5 + 2.4 x 3 = 35.2 m2 | Row 80: 35.2 m2 | This is the Pump House ceiling formula (page 15) repeated on the Bunkhouse page, and the Bunkhouse wall formula is the one that was on the old Sauna page. Re-measure the Bunkhouse or note that it is the same footprint as the Pump House |
| Casey | 12 | Red Shed crawlway boards | 1.2 x 2.4 x 25 sheets = 72 m2 | Row 17: 72 m2, Removal - Full 2029 | Register v7 says the sheets under the main subfloor were removed in 2025 and only the sheets under medical remain. Reduce the page and the tool to the remaining area |

## 3. Tool rows with a quantity but no calc

| Sheet | Row | Item | Tool | Note |
|---|---|---|---|---|
| Reg_Davis | 8 | EPH external and roofing panels | 268 m2 x 0.02 | Page 2 names the item but has no area. Add the working |
| Reg_Casey | 7 | Jack's Donga insulation | 0.5 m2 x 0.01, material type Ceiling | New since last check. No page, no AF note, and insulation coded as Ceiling. Hut, Manage per AMP, so either clear it or record the basis |

## 4. Calc pages to delete, add or fix

| Station | Page | Action | Reason |
|---|---|---|---|
| Casey | 4 | Delete | Balloon Release floor sheeting 85.255 m2. No tool row and no register entry |
| Mawson | 6 | Delete | Exact duplicate of page 3 (ANARESAT) |
| Macquarie | 20 | Delete at next update | Transmitter Hut, now Complete and quantities cleared from the tool. Keep only if the 46 m2 and switchboard are wanted for this season's return freight |
| Davis | 9 | Delete or fill | Old Tip Site page is a placeholder reading "[sample text]" |
| Davis | 8, 14 | Optional delete | Old Garage and beach slab, both Complete with no quantity |
| Davis | 2 | Add working | EPH external and roofing panels 268 m2 |
| Davis | 12 | Fix | SMQ coating arithmetic, see section 2 |
| Davis | 15 | Rename | Page titled Refuelling Point Settling Tank; register v7 and the tool should both say Store Fuel Tank L1146 (tool row 22 still says Refuelling Point) |
| Macquarie | 21 | Fix typo | "Wall area = 6.2.*2.4 = 147" should read 61.2 x 2.4 |
| Macquarie | 17 | Re-measure or annotate | Bunkhouse, see section 2 |
| Casey | 12 | Reduce | Red Shed, see section 2 |

## 5. Everything else

All other rows with areas tie to their pages: Casey ANARESAT, Balloon dado, MPH walls and floor, Operations floor and subfloor, Receiver, Transmitter Building; Davis EPH walls and manifolds, MPH walls, Site Services formwork and stair formwork, Green Store, workshop; Mawson Aeronomy, ANARESAT, Biscoe, Cosray, Dog Hut, Green Store, MPH, PID Van, Wombat, SMQ floor, fire doors and splashback, Tankhouse, Water Supply formwork, Transmitter Building, Wilkins; Macquarie Biology, Comms, Electrical Distribution pipe, Ham Shack, EPH, Fire Hut, Fire Pump House, Garden Cove, Hass House, Balloon Building, Workshop walls, fascia and ceiling, Mess and pantry, Pump House, Sauna, Science, SAD, Post Office, Surgery.
